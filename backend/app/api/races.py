import logging
import re
from typing import Optional, List, Dict
from datetime import date
from fastapi import APIRouter, Query, HTTPException
import httpx
from backend.app.config import get_supabase
from backend.app.llm.predictor import run_prediction
from backend.app.prediction.engine import run_system_prediction

router = APIRouter()
logger = logging.getLogger(__name__)

VENUE_CODE_TO_NAME = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川", "06": "浜名湖",
    "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島", "17": "宮島", "18": "徳山",
    "19": "下関", "20": "若松", "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}


def _compute_escape_calibration(race: dict, sb) -> dict:
    """逃げ成立度の当節較正データ（改正46/48）を算出。
    同場直近の確定レースの実1号頭率Rと標本数Nを返す。
    race_winner_logテーブルが空/未整備ならN=0（priorを据え置く＝改正48）。
    """
    venue = race.get("venue")
    if not venue:
        return {"r": None, "n": 0}
    try:
        # 同場の着順確定レースを最大60件（直近2節＋当節相当）取得
        resp = (sb.table("race_winner_log")
                .select("winner_course")
                .eq("venue", venue)
                .order("date", desc=True)
                .limit(60)
                .execute())
        rows = resp.data or []
    except Exception:
        return {"r": None, "n": 0}
    n = len(rows)
    if n == 0:
        return {"r": None, "n": 0}
    in_head = sum(1 for r in rows if int(r.get("winner_course") or 0) == 1)
    return {"r": in_head / n, "n": n}


def _build_race_response(race: dict, sb) -> dict:
    """Attach boats (with player info) and predictions to a race dict."""
    race_id = race["id"]

    # Boats with player join
    boats_resp = sb.table("boats").select(
        "*, players(name, rank, registration_no, branch)"
    ).eq("race_id", race_id).order("lane").execute()
    boats = boats_resp.data or []

    # Flatten player info into boat
    for boat in boats:
        player = boat.pop("players", None) or {}
        boat["name"] = player.get("name", "")
        boat["rank"] = player.get("rank", "")
        boat["registration_no"] = player.get("registration_no", "")

    # Predictions
    preds_resp = sb.table("predictions").select("*").eq("race_id", race_id).order("created_at", desc=True).execute()
    predictions = preds_resp.data or []

    # Normalize prediction field names for frontend compatibility
    for pred in predictions:
        # Map predicted_trifecta -> trifecta for frontend
        if "predicted_trifecta" in pred and "trifecta" not in pred:
            pred["trifecta"] = pred["predicted_trifecta"]
        if "predicted_exacta" in pred and "exacta" not in pred:
            pred["exacta"] = pred["predicted_exacta"]
        if "is_correct_trifecta" in pred and "is_correct" not in pred:
            pred["is_correct"] = pred["is_correct_trifecta"]

    race["boats"] = boats
    race["predictions"] = predictions
    race["predictions_count"] = len(predictions)
    return race


@router.get("/latest-date")
async def get_latest_date():
    """Return the latest date that has race data."""
    sb = get_supabase()
    resp = sb.table("races").select("date").order("date", desc=True).limit(1).execute()
    if resp.data:
        return {"date": resp.data[0]["date"]}
    return {"date": date.today().isoformat()}


@router.get("/")
async def get_races(target_date: Optional[str] = Query(None)):
    sb = get_supabase()
    query_date = target_date or date.today().isoformat()

    resp = sb.table("races").select("*").eq("date", query_date).order("venue").order("race_no").execute()
    races = resp.data or []

    if not races:
        return races

    # 全race_idをまとめて1回のクエリでpredictionsを取得（N+1問題解消）
    race_ids = [r["id"] for r in races]
    pred_resp = sb.table("predictions").select("race_id, predicted_trifecta, trifecta, created_at") \
        .in_("race_id", race_ids).order("created_at", desc=True).execute()
    preds_all = pred_resp.data or []

    # race_idでグループ化（最新の1件のみ使用）
    preds_by_race: dict = {}
    for p in preds_all:
        rid = p["race_id"]
        if rid not in preds_by_race:
            preds_by_race[rid] = p

    for race in races:
        race["boats"] = []
        p = preds_by_race.get(race["id"])
        if p:
            trifecta = p.get("trifecta") or p.get("predicted_trifecta") or ""
            race["predictions"] = [{"trifecta": trifecta}]
            race["predictions_count"] = 1
        else:
            race["predictions"] = []
            race["predictions_count"] = 0

    return races


@router.get("/events/today")
async def get_today_events(target_date: Optional[str] = Query(None)):
    """boatrace.jp公式トップからその日の開催イベント名・日次を取得"""
    query_date = target_date or date.today().isoformat()
    date_str = query_date.replace("-", "")
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    events: Dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.raise_for_status()
            html = resp.text

        # Extract event title, period, and day for each venue
        # HTML structure: <a href="...raceindex?jcd=XX&amp;hd=...">TITLE</a></td><td>PERIOD<br>DAY</td>
        rows = re.findall(
            r'raceindex\?jcd=(\d{2})&amp;hd=\d+["\']>([^<]+)</a>\s*</td>\s*<td[^>]*>'
            r'(\d{1,2}/\d{1,2}-\d{1,2}/\d{1,2})\s*<br\s*/?>([^<]+)</td>',
            html, re.DOTALL
        )
        # Extract grade classes (SG/G1/G2/G3) per venue code
        grade_map: Dict[str, str] = {}
        for m in re.finditer(r'class="is-(SG|G1|G2|G3)[a-z]*\s*".*?raceindex\?jcd=(\d{2})', html, re.DOTALL):
            grade_map[m.group(2)] = m.group(1)

        for jcd, title, period, day_info in rows:
            venue_name = VENUE_CODE_TO_NAME.get(jcd, jcd)
            grade = grade_map.get(jcd)
            event_name = title.strip()
            if grade:
                event_name = f"[{grade}] {event_name}"
            events[venue_name] = {
                "event_name": event_name,
                "grade": grade,
                "period": period.strip(),
                "day": day_info.strip(),
            }
    except Exception as e:
        logger.warning(f"Failed to fetch event info from boatrace.jp: {e}")

    return {"date": query_date, "events": events}


@router.get("/{race_id}")
async def get_race(race_id: int):
    sb = get_supabase()

    race_resp = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race_resp.data:
        raise HTTPException(status_code=404, detail="Race not found")

    return _build_race_response(race_resp.data, sb)


@router.post("/{race_id}/predict")
async def predict_race(race_id: int, source: str = Query("ensemble")):
    sb = get_supabase()

    race_resp = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race_resp.data:
        raise HTTPException(status_code=404, detail="Race not found")

    race = _build_race_response(race_resp.data, sb)
    prediction = await run_prediction(race, source)

    # Map to actual DB columns
    db_pred = {
        "race_id": race_id,
        "source": source,
        "predicted_trifecta": prediction.get("trifecta"),
        "predicted_exacta": prediction.get("exacta"),
        "confidence": prediction.get("confidence"),
        "reasoning": prediction.get("pattern", ""),
        "ei": prediction.get("ei"),
        "ti": prediction.get("ti"),
        "judgement": prediction.get("judgement"),
        "pattern": prediction.get("pattern"),
        "main_attack": prediction.get("main_attack"),
        "sink_candidate": prediction.get("sink_candidate"),
        "suji": prediction.get("suji"),
        "trifecta": prediction.get("trifecta"),
        "exacta": prediction.get("exacta"),
        "classification": prediction.get("classification", ""),
    }

    sb.table("predictions").insert(db_pred).execute()

    # Return updated race
    return await get_race(race_id)


@router.post("/{race_id}/predict-system")
async def predict_race_system(race_id: int):
    """
    競艇予想AI v58.7 完全版 システム予測
    戻り額ゲート（合成オッズ反比例配分）/発動艇認定・D-KAN5項目/受益マップ・
    テンプレ優先・捲り屋降格則/被弾率A型禁止 をPythonの計算式として実装。
    """
    sb = get_supabase()

    race_resp = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race_resp.data:
        raise HTTPException(status_code=404, detail="Race not found")

    race = _build_race_response(race_resp.data, sb)

    # 逃げ成立度の当節較正（改正46/48）：同場の実1号頭率Rと標本数Nを供給。
    # race_winner_logが空/未整備の場合はN=0となりpriorを据え置く（改正48に合致）。
    race["escape_calibration"] = _compute_escape_calibration(race, sb)

    # v58.7 システム予測実行
    prediction = run_system_prediction(race)

    # DB保存（predicted_trifecta/exacta カラムは varchar(20) のため主要1点のみ保存。
    # 全フォーメーションは detail で返却しフロントに表示する）
    def _primary(v):
        if not v:
            return v
        return str(v).split(",")[0].strip()

    db_pred = {
        "race_id": race_id,
        "source": "system_v58",
        "predicted_trifecta": _primary(prediction.get("predicted_trifecta")),
        "predicted_exacta": _primary(prediction.get("predicted_exacta")),
        "confidence": prediction.get("confidence"),
        "reasoning": prediction.get("reasoning", ""),
        "pattern": prediction.get("pattern"),
        "main_attack": prediction.get("main_attack"),
        "classification": prediction.get("classification", ""),
    }
    sb.table("predictions").insert(db_pred).execute()

    # 詳細レスポンス（予測詳細 + レース情報）
    updated = await get_race(race_id)
    updated["system_prediction_detail"] = prediction.get("detail", {})
    return updated


@router.post("/scrape")
async def scrape_races(target_date: Optional[str] = Query(None)):
    from backend.app.scrapers.boaters import scrape_race_list
    query_date = target_date or date.today().isoformat()
    result = await scrape_race_list(query_date)
    return result


@router.get("/{race_id}/result")
async def get_race_result(race_id: int):
    """race_winner_log から実結果（1〜3着・3連単・2連単・払戻）を取得"""
    sb = get_supabase()
    try:
        race_resp = sb.table("races").select("date, venue, race_no").eq("id", race_id).single().execute()
    except Exception:
        logger.exception("Failed to fetch race for result lookup", extra={"race_id": race_id})
        raise HTTPException(status_code=502, detail="Failed to fetch race")

    if not race_resp.data:
        raise HTTPException(status_code=404, detail="Race not found")

    race = race_resp.data
    if race.get("race_no") is None:
        logger.warning("Race result lookup skipped because race_no is missing", extra={"race_id": race_id, "race": race})
        return {}

    try:
        result_resp = sb.table("race_winner_log").select(
            "race_key, winner_lane, winner_course, place2_lane, place3_lane, "
            "trifecta_result, exacta_result, trifecta_payout, exacta_payout, "
            "trifecta_place_payout, result_all"
        ).eq("date", race["date"]).eq("venue", race["venue"]).eq("race_no", race["race_no"]).maybe_single().execute()
    except Exception:
        logger.exception(
            "Failed to fetch race result from race_winner_log",
            extra={"race_id": race_id, "date": race.get("date"), "venue": race.get("venue"), "race_no": race.get("race_no")},
        )
        return {}

    return result_resp.data or {}


@router.patch("/{race_id}/prediction/memo")
async def save_prediction_memo(race_id: int, body: dict):
    """直近のシステム予想に改善コメント(memo)を保存"""
    sb = get_supabase()
    memo = body.get("memo", "")
    pred = sb.table("predictions").select("id").eq("race_id", race_id).eq("source", "system_v58") \
        .order("created_at", desc=True).limit(1).maybe_single().execute()
    if pred.data:
        try:
            sb.table("predictions").update({"memo": memo}).eq("id", pred.data["id"]).execute()
        except Exception:
            # memo列未追加の場合は無視
            pass
    return {"status": "ok"}
