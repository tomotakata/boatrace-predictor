from typing import Optional, List
from datetime import date, datetime
from fastapi import APIRouter, Query, HTTPException
from backend.app.config import get_supabase
from backend.app.llm.predictor import run_prediction

router = APIRouter()


@router.get("/")
async def get_races(target_date: Optional[str] = Query(None)):
    sb = get_supabase()
    query_date = target_date or date.today().isoformat()

    resp = sb.table("races").select("*").eq("date", query_date).order("venue").order("race_no").execute()
    races = resp.data or []

    # Attach prediction counts
    for race in races:
        pred_resp = sb.table("predictions").select("id").eq("race_id", race["id"]).execute()
        race["predictions_count"] = len(pred_resp.data or [])
        race["predictions"] = []
        race["boats"] = []

    return races


@router.get("/{race_id}")
async def get_race(race_id: int):
    sb = get_supabase()

    race_resp = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race_resp.data:
        raise HTTPException(status_code=404, detail="Race not found")

    race = race_resp.data

    boats_resp = sb.table("boats").select("*").eq("race_id", race_id).order("lane").execute()
    race["boats"] = boats_resp.data or []

    preds_resp = sb.table("predictions").select("*").eq("race_id", race_id).order("created_at", desc=True).execute()
    race["predictions"] = preds_resp.data or []
    race["predictions_count"] = len(race["predictions"])

    return race


@router.post("/{race_id}/predict")
async def predict_race(race_id: int, source: str = Query("ensemble")):
    sb = get_supabase()

    race_resp = sb.table("races").select("*").eq("id", race_id).single().execute()
    if not race_resp.data:
        raise HTTPException(status_code=404, detail="Race not found")

    race = race_resp.data
    boats_resp = sb.table("boats").select("*").eq("race_id", race_id).order("lane").execute()
    race["boats"] = boats_resp.data or []

    prediction = await run_prediction(race, source)

    pred_resp = sb.table("predictions").insert({
        "race_id": race_id,
        "source": source,
        **prediction
    }).execute()

    # Return updated race
    return await get_race(race_id)


@router.post("/scrape")
async def scrape_races(target_date: Optional[str] = Query(None)):
    from backend.app.scrapers.boaters import scrape_race_list
    query_date = target_date or date.today().isoformat()
    result = await scrape_race_list(query_date)
    return result
