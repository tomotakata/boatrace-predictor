from typing import Optional
from fastapi import APIRouter, UploadFile, File
from backend.app.config import get_supabase
from backend.app.importers.chat_importer import import_claude_chat, import_gemini_chat

router = APIRouter()


def _safe_rate(correct: int, total: int) -> float:
    return round(correct / total * 100, 1) if total > 0 else 0.0


def _fetch_races_by_ids(sb, race_ids: list) -> dict:
    """race_id リストを1回のクエリで一括取得してdict返却"""
    if not race_ids:
        return {}
    result = {}
    chunk = 500
    for i in range(0, len(race_ids), chunk):
        rows = sb.table("races").select("id, date, venue, race_no") \
            .in_("id", race_ids[i:i+chunk]).execute().data or []
        for r in rows:
            result[r["id"]] = r
    return result


@router.get("/accuracy")
async def get_accuracy(from_date: Optional[str] = None, to_date: Optional[str] = None):
    """3連単・2連単の的中率サマリー（日付フィルタ対応・高速版）"""
    sb = get_supabase()

    # ① 日付フィルタがある場合は races 側で race_id セットを取得
    race_id_filter: Optional[set] = None
    if from_date or to_date:
        rq = sb.table("races").select("id")
        if from_date:
            rq = rq.gte("date", from_date)
        if to_date:
            rq = rq.lte("date", to_date)
        race_id_filter = {r["id"] for r in (rq.execute().data or [])}

    # ② predictions を1回で取得（最大2000件）
    q = sb.table("predictions").select(
        "source, is_correct_trifecta, is_correct_exacta, payout_grade, race_id"
    ).limit(2000)
    preds = q.execute().data or []

    if race_id_filter is not None:
        preds = [p for p in preds if p.get("race_id") in race_id_filter]

    total = len(preds)
    if total == 0:
        return {
            "total_predictions": 0, "evaluated": 0,
            "trifecta_rate": 0.0, "exacta_rate": 0.0,
            "by_source": [], "by_grade": [],
        }

    tri_correct = sum(1 for p in preds if p.get("is_correct_trifecta") is True)
    ex_correct  = sum(1 for p in preds if p.get("is_correct_exacta") is True)
    evaluated   = sum(1 for p in preds if p.get("is_correct_trifecta") is not None)

    # ソース別
    by_source: dict = {}
    for p in preds:
        s = p.get("source", "system")
        d = by_source.setdefault(s, {"total": 0, "tri": 0, "ex": 0})
        d["total"] += 1
        if p.get("is_correct_trifecta") is True: d["tri"] += 1
        if p.get("is_correct_exacta")   is True: d["ex"]  += 1

    # 判定グレード別
    by_grade: dict = {}
    for p in preds:
        g = p.get("payout_grade") or "未評価"
        d = by_grade.setdefault(g, {"total": 0, "tri": 0, "ex": 0})
        d["total"] += 1
        if p.get("is_correct_trifecta") is True: d["tri"] += 1
        if p.get("is_correct_exacta")   is True: d["ex"]  += 1

    grade_order = ["勝負", "通常", "見送り", "未評価"]
    return {
        "total_predictions": total,
        "evaluated": evaluated,
        "trifecta_rate": _safe_rate(tri_correct, evaluated) if evaluated else 0.0,
        "exacta_rate":   _safe_rate(ex_correct,  evaluated) if evaluated else 0.0,
        "by_source": [
            {"source": s, "total": d["total"],
             "trifecta_rate": _safe_rate(d["tri"], d["total"]),
             "exacta_rate":   _safe_rate(d["ex"],  d["total"])}
            for s, d in by_source.items()
        ],
        "by_grade": sorted(
            [{"grade": g, "total": d["total"],
              "trifecta_rate": _safe_rate(d["tri"], d["total"]),
              "exacta_rate":   _safe_rate(d["ex"],  d["total"])}
             for g, d in by_grade.items()],
            key=lambda x: grade_order.index(x["grade"]) if x["grade"] in grade_order else 99,
        ),
    }


@router.get("/accuracy/by_venue")
async def get_accuracy_by_venue(from_date: Optional[str] = None, to_date: Optional[str] = None):
    """会場別の的中率（一括クエリ版）"""
    sb = get_supabase()

    # races を1回取得
    rq = sb.table("races").select("id, venue, date")
    if from_date: rq = rq.gte("date", from_date)
    if to_date:   rq = rq.lte("date", to_date)
    races = {r["id"]: r for r in (rq.execute().data or [])}

    if not races:
        return []

    # races.id セットに絞った predictions を1回取得
    race_ids = list(races.keys())
    preds: list = []
    chunk = 500
    for i in range(0, len(race_ids), chunk):
        rows = sb.table("predictions").select(
            "race_id, is_correct_trifecta, is_correct_exacta"
        ).in_("race_id", race_ids[i:i+chunk]).execute().data or []
        preds.extend(rows)

    by_venue: dict = {}
    for p in preds:
        race = races.get(p.get("race_id"))
        if not race:
            continue
        v = race.get("venue", "不明")
        d = by_venue.setdefault(v, {"total": 0, "tri": 0, "ex": 0, "evaluated": 0})
        d["total"] += 1
        if p.get("is_correct_trifecta") is not None: d["evaluated"] += 1
        if p.get("is_correct_trifecta") is True:     d["tri"] += 1
        if p.get("is_correct_exacta")   is True:     d["ex"]  += 1

    return sorted(
        [{"venue": v, "total": d["total"], "evaluated": d["evaluated"],
          "trifecta_rate": _safe_rate(d["tri"], d["evaluated"]),
          "exacta_rate":   _safe_rate(d["ex"],  d["evaluated"])}
         for v, d in by_venue.items()],
        key=lambda x: -x["trifecta_rate"],
    )


@router.get("/accuracy/timeline")
async def get_accuracy_timeline(days: int = 30):
    """直近N日の日別的中率推移（一括クエリ版）"""
    sb = get_supabase()
    from datetime import date, timedelta

    from_d = (date.today() - timedelta(days=days)).isoformat()

    # races を1回取得して race_id→date マップを作成
    race_id_to_date: dict = {}
    rsp = sb.table("races").select("id, date").gte("date", from_d).execute()
    for r in (rsp.data or []):
        race_id_to_date[r["id"]] = r["date"]

    if not race_id_to_date:
        return []

    # predictions を1回取得
    race_ids = list(race_id_to_date.keys())
    preds: list = []
    chunk = 500
    for i in range(0, len(race_ids), chunk):
        rows = sb.table("predictions").select(
            "race_id, is_correct_trifecta"
        ).in_("race_id", race_ids[i:i+chunk]).execute().data or []
        preds.extend(rows)

    by_day: dict = {}
    for p in preds:
        dt = race_id_to_date.get(p.get("race_id"))
        if not dt:
            continue
        d = by_day.setdefault(dt, {"total": 0, "tri": 0, "evaluated": 0})
        d["total"] += 1
        if p.get("is_correct_trifecta") is not None: d["evaluated"] += 1
        if p.get("is_correct_trifecta") is True:     d["tri"] += 1

    return sorted(
        [{"date": dt, "total": d["total"],
          "trifecta_rate": _safe_rate(d["tri"], d["evaluated"]) if d["evaluated"] else None}
         for dt, d in by_day.items()],
        key=lambda x: x["date"],
    )


@router.get("/recent")
async def get_recent_predictions(limit: int = 30):
    """直近の予想一覧（N+1クエリ廃止・2クエリで完結）"""
    sb = get_supabase()

    # ① predictions を limit 件取得
    preds = sb.table("predictions").select(
        "id, source, predicted_trifecta, trifecta, confidence, "
        "is_correct_trifecta, is_correct_exacta, actual_trifecta, payout_grade, created_at, race_id"
    ).order("created_at", desc=True).limit(limit).execute().data or []

    if not preds:
        return []

    # ② race_id を一括フェッチ（1クエリ）
    race_ids = list({p["race_id"] for p in preds if p.get("race_id")})
    races = _fetch_races_by_ids(sb, race_ids)

    result = []
    for p in preds:
        race = races.get(p.get("race_id"), {})
        trifecta = p.get("trifecta") or p.get("predicted_trifecta") or ""
        result.append({
            "id": p["id"],
            "date": race.get("date", ""),
            "race": f"{race.get('venue','')} {race.get('race_no','')}R",
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
    return await import_claude_chat(content)


@router.post("/import/gemini")
async def import_gemini(file: UploadFile = File(...)):
    content = await file.read()
    return await import_gemini_chat(content)
