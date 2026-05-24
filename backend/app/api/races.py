from typing import Optional, List
from datetime import date
from fastapi import APIRouter, Query, HTTPException
from backend.app.config import get_supabase
from backend.app.llm.predictor import run_prediction

router = APIRouter()


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


@router.get("/")
async def get_races(target_date: Optional[str] = Query(None)):
    sb = get_supabase()
    query_date = target_date or date.today().isoformat()

    resp = sb.table("races").select("*").eq("date", query_date).order("venue").order("race_no").execute()
    races = resp.data or []

    # Lightweight: only attach prediction count and latest trifecta
    for race in races:
        pred_resp = sb.table("predictions").select("id, predicted_trifecta, trifecta, created_at").eq("race_id", race["id"]).order("created_at", desc=True).limit(1).execute()
        preds = pred_resp.data or []
        race["predictions_count"] = len(preds)
        race["boats"] = []
        if preds:
            p = preds[0]
            trifecta = p.get("trifecta") or p.get("predicted_trifecta") or ""
            race["predictions"] = [{"trifecta": trifecta}]
        else:
            race["predictions"] = []

    return races


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


@router.post("/scrape")
async def scrape_races(target_date: Optional[str] = Query(None)):
    from backend.app.scrapers.boaters import scrape_race_list
    query_date = target_date or date.today().isoformat()
    result = await scrape_race_list(query_date)
    return result
