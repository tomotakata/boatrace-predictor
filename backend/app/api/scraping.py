"""
スクレイピングAPI - 全処理をさくらサーバー経由で実行
さくらサーバー: http://153.121.51.74:8080
"""
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
import httpx
import os

router = APIRouter()

SAKURA_SCRAPER_URL    = os.getenv("SAKURA_SCRAPER_URL", "http://153.121.51.74:8080")
SAKURA_SCRAPER_SECRET = os.getenv("SAKURA_SCRAPER_SECRET", "boatrace-sakura-secret-2024")

VENUE_LIST = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
    "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
    "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
    "下関", "若松", "芦屋", "福岡", "唐津", "大村"
]


class ScrapeRequest(BaseModel):
    date: str
    venues: List[str]
    items: List[str]  # "entry", "motor", "exhibition", "profile", "raceinfo_time"


class CookieSetRequest(BaseModel):
    cookies: str  # "name=value; name2=value2" 形式


@router.get("/venues")
async def get_venues():
    return {"venues": VENUE_LIST}


@router.post("/run")
async def run_scraping(req: ScrapeRequest):
    """全スクレイピングをさくらサーバー経由で実行"""
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
            # Vercel側のレスポンス形式に変換
            results = []
            for r in data.get("results", []):
                results.append({
                    "venue": r.get("venue"),
                    "item": r.get("item"),
                    "status": "ok" if r.get("status") == "ok" else "error",
                    "message": r.get("message", ""),
                })
            return {"results": results}
    except Exception as e:
        return {"results": [{"venue": "全体", "item": "all", "status": "error", "message": str(e)}]}


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
