from typing import Optional
from fastapi import APIRouter, UploadFile, File
from backend.app.config import get_supabase
from backend.app.importers.chat_importer import import_claude_chat, import_gemini_chat

router = APIRouter()


def _safe_rate(correct: int, total: int) -> float:
    return round(correct / total * 100, 1) if total > 0 else 0.0


@router.get("/accuracy")
async def get_accuracy(from_date: Optional[str] = None, to_date: Optional[str] = None):
    """3連単・2連単の的中率サマリー（日付フィルタ対応）"""
    sb = get_supabase()

    # predictions + races join 相当
    q = sb.table("predictions").select(
        "source, is_correct_trifecta, is_correct_exacta, payout_grade, race_id"
    )
    preds = q.execute().data or []

    # 日付フィルタが指定された場合は races テーブルで絞る
    race_date_filter: Optional[set] = None
    if from_date or to_date:
        rq = sb.table("races").select("id, date")
        if from_date:
            rq = rq.gte("date", from_date)
        if to_date:
            rq = rq.lte("date", to_date)
        race_date_filter = {r["id"] for r in (rq.execute().data or [])}

    if race_date_filter is not None:
        preds = [p for p in preds if p.get("race_id") in race_date_filter]

    total = len(preds)
    if total == 0:
        return {
            "total_predictions": 0,
            "trifecta_rate": 0.0,
            "exacta_rate": 0.0,
            "by_source": [],
            "by_grade": [],
        }

    # サマリー集計
    tri_correct  = sum(1 for p in preds if p.get("is_correct_trifecta") is True)
    ex_correct   = sum(1 for p in preds if p.get("is_correct_exacta") is True)
    evaluated    = sum(1 for p in preds if p.get("is_correct_trifecta") is not None)

    # ソース別
    by_source: dict = {}
    for p in preds:
        src = p.get("source", "system")
        if src not in by_source:
            by_source[src] = {"total": 0, "tri": 0, "ex": 0}
        by_source[src]["total"] += 1
        if p.get("is_correct_trifecta") is True:
            by_source[src]["tri"] += 1
        if p.get("is_correct_exacta") is True:
            by_source[src]["ex"] += 1

    by_source_list = [
        {
            "source": s,
            "total": d["total"],
            "trifecta_rate": _safe_rate(d["tri"], d["total"]),
            "exacta_rate": _safe_rate(d["ex"], d["total"]),
        }
        for s, d in by_source.items()
    ]

    # 判定グレード別（見送り/通常/勝負）
    by_grade: dict = {}
    for p in preds:
        g = p.get("payout_grade") or "未評価"
        if g not in by_grade:
            by_grade[g] = {"total": 0, "tri": 0, "ex": 0}
        by_grade[g]["total"] += 1
        if p.get("is_correct_trifecta") is True:
            by_grade[g]["tri"] += 1
        if p.get("is_correct_exacta") is True:
            by_grade[g]["ex"] += 1

    grade_order = ["勝負", "通常", "見送り", "未評価"]
    by_grade_list = sorted(
        [
            {
                "grade": g,
                "total": d["total"],
                "trifecta_rate": _safe_rate(d["tri"], d["total"]),
                "exacta_rate": _safe_rate(d["ex"], d["total"]),
            }
            for g, d in by_grade.items()
        ],
        key=lambda x: grade_order.index(x["grade"]) if x["grade"] in grade_order else 99,
    )

    return {
        "total_predictions": total,
        "evaluated": evaluated,
        "trifecta_rate": _safe_rate(tri_correct, evaluated) if evaluated else 0.0,
        "exacta_rate": _safe_rate(ex_correct, evaluated) if evaluated else 0.0,
        "by_source": by_source_list,
        "by_grade": by_grade_list,
    }


@router.get("/accuracy/by_venue")
async def get_accuracy_by_venue(from_date: Optional[str] = None, to_date: Optional[str] = None):
    """会場別の的中率"""
    sb = get_supabase()

    rq = sb.table("races").select("id, venue, date")
    if from_date:
        rq = rq.gte("date", from_date)
    if to_date:
        rq = rq.lte("date", to_date)
    races = {r["id"]: r for r in (rq.execute().data or [])}

    preds = sb.table("predictions").select(
        "race_id, is_correct_trifecta, is_correct_exacta, payout_grade"
    ).execute().data or []

    by_venue: dict = {}
    for p in preds:
        race = races.get(p.get("race_id"))
        if not race:
            continue
        v = race.get("venue", "不明")
        if v not in by_venue:
            by_venue[v] = {"total": 0, "tri": 0, "ex": 0, "evaluated": 0}
        by_venue[v]["total"] += 1
        if p.get("is_correct_trifecta") is not None:
            by_venue[v]["evaluated"] += 1
        if p.get("is_correct_trifecta") is True:
            by_venue[v]["tri"] += 1
        if p.get("is_correct_exacta") is True:
            by_venue[v]["ex"] += 1

    result = sorted(
        [
            {
                "venue": v,
                "total": d["total"],
                "evaluated": d["evaluated"],
                "trifecta_rate": _safe_rate(d["tri"], d["evaluated"]),
                "exacta_rate": _safe_rate(d["ex"], d["evaluated"]),
            }
            for v, d in by_venue.items()
        ],
        key=lambda x: -x["trifecta_rate"],
    )
    return result


@router.get("/accuracy/timeline")
async def get_accuracy_timeline(days: int = 30):
    """直近N日の日別的中率推移"""
    sb = get_supabase()
    from datetime import date, timedelta

    today = date.today()
    from_d = (today - timedelta(days=days)).isoformat()

    races_by_date: dict = {}
    rsp = sb.table("races").select("id, date").gte("date", from_d).execute()
    for r in (rsp.data or []):
        races_by_date.setdefault(r["date"], set()).add(r["id"])

    preds = sb.table("predictions").select(
        "race_id, is_correct_trifecta, is_correct_exacta"
    ).execute().data or []

    by_day: dict = {}
    for p in preds:
        for dt, ids in races_by_date.items():
            if p.get("race_id") in ids:
                if dt not in by_day:
                    by_day[dt] = {"total": 0, "tri": 0, "evaluated": 0}
                by_day[dt]["total"] += 1
                if p.get("is_correct_trifecta") is not None:
                    by_day[dt]["evaluated"] += 1
                if p.get("is_correct_trifecta") is True:
                    by_day[dt]["tri"] += 1
                break

    result = sorted(
        [
            {
                "date": dt,
                "total": d["total"],
                "trifecta_rate": _safe_rate(d["tri"], d["evaluated"]) if d["evaluated"] else None,
            }
            for dt, d in by_day.items()
        ],
        key=lambda x: x["date"],
    )
    return result


@router.get("/recent")
async def get_recent_predictions(limit: int = 30):
    sb = get_supabase()

    preds_resp = sb.table("predictions").select(
        "id, source, predicted_trifecta, trifecta, confidence, is_correct_trifecta, "
        "is_correct_exacta, actual_trifecta, payout_grade, created_at, race_id"
    ).order("created_at", desc=True).limit(limit).execute()

    predictions = preds_resp.data or []

    result = []
    for p in predictions:
        race_resp = sb.table("races").select("date, race_no, venue").eq("id", p["race_id"]).maybe_single().execute()
        race = race_resp.data or {}
        trifecta = p.get("trifecta") or p.get("predicted_trifecta") or ""
        result.append({
            "id": p["id"],
            "date": race.get("date", ""),
            "race": f"{race.get('venue', '')} {race.get('race_no', '')}R",
            "venue": race.get("venue", ""),
            "race_no": race.get("race_no"),
            "source": p.get("source", "system"),
            "trifecta": trifecta,
            "confidence": p.get("confidence"),
            "is_correct": p.get("is_correct_trifecta"),
            "is_correct_exacta": p.get("is_correct_exacta"),
            "actual_trifecta": p.get("actual_trifecta"),
            "payout_grade": p.get("payout_grade"),
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
