"""
dashgen_service — dashgen 計算結果の DB 保存・取得サービス

dashgen_results テーブルへの CRUD 操作を提供する。
テーブルが存在しない場合はエラーをログに記録して None を返す（フォールバック可能）。
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.config import get_supabase
from backend.app.prediction.dashgen_adapter import build_dashgen_input
from backend.app.prediction.dashgen import generate_dashboard

logger = logging.getLogger(__name__)


# ── DB 操作 ──────────────────────────────────────────────


def get_cached_dashgen(race_id: int) -> Optional[Dict[str, Any]]:
    """dashgen_results テーブルから計算済み結果を取得する。

    Returns:
        計算済み結果 dict、またはキャッシュなし/テーブル未作成時 None
    """
    try:
        sb = get_supabase()
        resp = (
            sb.table("dashgen_results")
            .select("result, calculated_at")
            .eq("race_id", race_id)
            .maybe_single()
            .execute()
        )
        if resp.data and resp.data.get("result"):
            result = resp.data["result"]
            # result が文字列の場合は JSON パース
            if isinstance(result, str):
                result = json.loads(result)
            result["race_id"] = race_id
            result["cached"] = True
            result["calculated_at"] = resp.data.get("calculated_at")
            return result
        return None
    except Exception as e:
        # テーブル未作成 (PGRST205) やその他エラーは警告のみ
        logger.warning("dashgen cache lookup failed (race_id=%s): %s", race_id, e)
        return None


def save_dashgen_result(race_id: int, result: Dict[str, Any]) -> bool:
    """dashgen 計算結果を dashgen_results テーブルに保存（upsert）する。

    Returns:
        保存成功時 True、失敗時 False
    """
    try:
        sb = get_supabase()
        # cached フラグや race_id は保存対象から除外
        save_data = {k: v for k, v in result.items() if k not in ("race_id", "cached", "calculated_at")}
        sb.table("dashgen_results").upsert(
            {
                "race_id": race_id,
                "result": json.dumps(save_data, ensure_ascii=False, default=str),
                "calculated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="race_id",
        ).execute()
        return True
    except Exception as e:
        logger.warning("dashgen cache save failed (race_id=%s): %s", race_id, e)
        return False


def compute_and_save_dashgen(race_id: int) -> Optional[Dict[str, Any]]:
    """dashgen を計算して DB に保存し、結果を返す。

    Returns:
        計算結果 dict、またはエラー時 None
    """
    try:
        entries, environment = build_dashgen_input(race_id)
        result = generate_dashboard(entries, environment)
        result["race_id"] = race_id
        save_dashgen_result(race_id, result)
        return result
    except Exception as e:
        logger.error(
            "dashgen compute_and_save failed (race_id=%s): %s\n%s",
            race_id, e, traceback.format_exc(),
        )
        return None


def compute_dashgen_for_races(date: str, venue: str) -> Dict[str, Any]:
    """指定日・会場の全レースに対して dashgen を計算して DB に保存する。

    Args:
        date: 日付 (YYYY-MM-DD 形式)
        venue: 会場名

    Returns:
        {"computed": int, "failed": int, "race_ids": [...], "errors": [...]}
    """
    sb = get_supabase()

    # 該当日・会場のレース一覧を取得
    resp = (
        sb.table("races")
        .select("id, race_no")
        .eq("date", date)
        .eq("venue", venue)
        .order("race_no")
        .execute()
    )
    races = resp.data or []
    if not races:
        return {"computed": 0, "failed": 0, "race_ids": [], "errors": ["No races found"]}

    computed = 0
    failed = 0
    race_ids: List[int] = []
    errors: List[str] = []

    for race in races:
        race_id = race["id"]
        race_no = race.get("race_no", "?")
        try:
            result = compute_and_save_dashgen(race_id)
            if result:
                computed += 1
                race_ids.append(race_id)
                logger.info("dashgen computed: %s R%s (race_id=%s)", venue, race_no, race_id)
            else:
                failed += 1
                errors.append(f"R{race_no}: computation returned None")
        except Exception as e:
            failed += 1
            errors.append(f"R{race_no}: {e}")
            logger.error("dashgen failed: %s R%s: %s", venue, race_no, e)

    return {
        "computed": computed,
        "failed": failed,
        "race_ids": race_ids,
        "errors": errors,
    }
