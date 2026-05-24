from typing import Optional
from fastapi import APIRouter, UploadFile, File
from backend.app.config import get_supabase
from backend.app.importers.chat_importer import import_claude_chat, import_gemini_chat

router = APIRouter()


@router.get("/accuracy")
async def get_accuracy():
    sb = get_supabase()

    preds_resp = sb.table("predictions").select("source, is_correct").execute()
    predictions = preds_resp.data or []

    total = len(predictions)
    if total == 0:
        return {
            "total_predictions": 0,
            "trifecta_rate": 0.0,
            "exacta_rate": 0.0,
            "by_source": []
        }

    correct = sum(1 for p in predictions if p.get("is_correct") is True)
    trifecta_rate = (correct / total * 100) if total > 0 else 0.0

    by_source = {}
    for p in predictions:
        src = p.get("source", "unknown")
        if src not in by_source:
            by_source[src] = {"total": 0, "correct": 0}
        by_source[src]["total"] += 1
        if p.get("is_correct") is True:
            by_source[src]["correct"] += 1

    by_source_list = [
        {
            "source": src,
            "rate": (data["correct"] / data["total"] * 100) if data["total"] > 0 else 0.0,
            "total": data["total"]
        }
        for src, data in by_source.items()
    ]

    return {
        "total_predictions": total,
        "trifecta_rate": round(trifecta_rate, 1),
        "exacta_rate": round(trifecta_rate * 1.4, 1),  # approximate
        "by_source": by_source_list
    }


@router.get("/recent")
async def get_recent_predictions(limit: int = 20):
    sb = get_supabase()

    preds_resp = sb.table("predictions").select(
        "id, source, trifecta, confidence, is_correct, created_at, race_id"
    ).order("created_at", desc=True).limit(limit).execute()

    predictions = preds_resp.data or []

    result = []
    for p in predictions:
        race_resp = sb.table("races").select("date, race_no, venue").eq("id", p["race_id"]).single().execute()
        race = race_resp.data or {}
        result.append({
            "id": p["id"],
            "date": race.get("date", ""),
            "race": f"{race.get('venue', '')} {race.get('race_no', '')}R",
            "source": p["source"],
            "trifecta": p.get("trifecta", ""),
            "confidence": p.get("confidence"),
            "is_correct": p.get("is_correct")
        })

    return result


@router.post("/import/claude")
async def import_claude(file: UploadFile = File(...)):
    content = await file.read()
    result = await import_claude_chat(content)
    return result


@router.post("/import/gemini")
async def import_gemini(file: UploadFile = File(...)):
    content = await file.read()
    result = await import_gemini_chat(content)
    return result
