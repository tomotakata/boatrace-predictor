"""
スクレイピングAPI - 全処理をさくらサーバー経由で実行
さくらサーバー: http://153.121.51.74:8080

スクレイピング完了後、dashgen 計算を自動実行して DB に保存する。
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)

SAKURA_SCRAPER_URL    = os.getenv("SAKURA_SCRAPER_URL", "http://153.121.51.74:8080")
SAKURA_SCRAPER_SECRET = os.getenv("SAKURA_SCRAPER_SECRET", "boatrace-sakura-secret-2024")

VENUE_LIST = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
    "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
    "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
    "下関", "若松", "芦屋", "福岡", "唐津", "大村"
]

# dashgen 自動計算をトリガーするスクレイピング項目
# これらの項目が完了した場合、dashgen を再計算する
DASHGEN_TRIGGER_ITEMS = {"entry", "motor", "exhibition", "profile", "raceinfo_time"}


class ScrapeRequest(BaseModel):
    date: str
    venues: List[str]
    items: List[str]  # "entry", "motor", "exhibition", "profile", "raceinfo_time"


class CookieSetRequest(BaseModel):
    cookies: str  # "name=value; name2=value2" 形式


class EvaluateRequest(BaseModel):
    from_date: str = ""
    to_date: str = ""


class HistoryRequest(BaseModel):
    from_date: str = ""
    to_date: str = ""
    venues: List[str] = []


class ResultScrapeRequest(BaseModel):
    date: str
    venue: str


def _normalize_date(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD に変換。すでにハイフン付きならそのまま返す。"""
    d = date_str.strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def _auto_compute_dashgen(date: str, venues: List[str], items: List[str]) -> List[dict]:
    """スクレイピング完了後に dashgen を自動計算する。

    dashgen 計算に必要なデータ（entry, motor, exhibition 等）が
    スクレイピングされた場合のみ実行する。
    """
    # dashgen トリガー対象の項目が含まれているか確認
    if not DASHGEN_TRIGGER_ITEMS.intersection(items):
        return []

    dashgen_results = []
    normalized_date = _normalize_date(date)

    try:
        from backend.app.prediction.dashgen_service import compute_dashgen_for_races
    except ImportError as e:
        logger.warning("dashgen_service import failed: %s", e)
        return [{"venue": "all", "status": "error", "message": f"import error: {e}"}]

    for venue in venues:
        try:
            result = compute_dashgen_for_races(normalized_date, venue)
            dashgen_results.append({
                "venue": venue,
                "status": "ok",
                "computed": result["computed"],
                "failed": result["failed"],
                "errors": result.get("errors", []),
            })
            logger.info(
                "dashgen auto-compute: %s %s → computed=%d, failed=%d",
                normalized_date, venue, result["computed"], result["failed"],
            )
        except Exception as e:
            dashgen_results.append({
                "venue": venue,
                "status": "error",
                "message": str(e),
            })
            logger.error("dashgen auto-compute failed: %s %s: %s", normalized_date, venue, e)

    return dashgen_results


@router.get("/venues")
async def get_venues():
    return {"venues": VENUE_LIST}


@router.post("/run")
async def run_scraping(req: ScrapeRequest):
    """全スクレイピングをさくらサーバー経由で実行。
    完了後に dashgen 計算を自動実行する。
    """
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{SAKURA_SCRAPER_URL}/scrape",
                json={
                    "date": req.date,
                    "venues": req.venues,
                    "items": req.items,
                    "secret": SAKURA_SCRAPER_SECRET,
                }
            )
            data = resp.json()
            results = []
            for r in data.get("results", []):
                results.append({
                    "venue": r.get("venue"),
                    "item": r.get("item"),
                    "status": "ok" if r.get("status") == "ok" else "error",
                    "message": r.get("message", ""),
                })

        # スクレイピング成功後に dashgen 自動計算
        dashgen_results = _auto_compute_dashgen(req.date, req.venues, req.items)

        return {
            "results": results,
            "dashgen": dashgen_results,
        }
    except Exception as e:
        return {"results": [{"venue": "全体", "item": "all", "status": "error", "message": str(e)}]}


@router.post("/results")
async def scrape_result(req: ResultScrapeRequest):
    try:
        payload = {
            "date": req.date.replace("-", ""),
            "items": ["results"],
            "secret": SAKURA_SCRAPER_SECRET,
        }
        if req.venue:
            payload["venues"] = [req.venue]

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{SAKURA_SCRAPER_URL}/scrape", json=payload)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                raise HTTPException(status_code=502, detail="スクレイピング結果が返されませんでした")
            first = results[0]
            if first.get("status") != "ok":
                raise HTTPException(status_code=502, detail=first.get("message") or data.get("summary") or "結果取得に失敗しました")
            return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"結果取得API呼び出しに失敗しました: {e}")


@router.post("/evaluate")
async def evaluate_predictions(req: EvaluateRequest):
    """予測 vs 実結果を突合してis_correct_trifecta/exactaを自動更新"""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{SAKURA_SCRAPER_URL}/evaluate",
                json={
                    "secret": SAKURA_SCRAPER_SECRET,
                    "from_date": req.from_date,
                    "to_date": req.to_date,
                }
            )
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/scrape_history")
async def scrape_history(req: HistoryRequest):
    """過去日付の確定着順を一括取得"""
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{SAKURA_SCRAPER_URL}/scrape_history",
                json={
                    "secret": SAKURA_SCRAPER_SECRET,
                    "from_date": req.from_date,
                    "to_date": req.to_date,
                    "venues": req.venues or list(range(1, 25)),
                }
            )
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/set_teleboat_cookies")
async def set_teleboat_cookies(req: CookieSetRequest):
    """boatrace.jpのセッションCookieをさくらサーバーに保存する"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{SAKURA_SCRAPER_URL}/set_teleboat_cookies",
                json={"secret": SAKURA_SCRAPER_SECRET, "cookies": req.cookies}
            )
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/check_teleboat_cookies")
async def check_teleboat_cookies():
    """保存済みCookieの状態を確認"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SAKURA_SCRAPER_URL}/check_teleboat_cookies")
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}
