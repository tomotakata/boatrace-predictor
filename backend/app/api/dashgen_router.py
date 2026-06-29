"""
dashgen_router — ダッシュボード生成 API エンドポイント

GET  /api/dashgen/{race_id}       — DB キャッシュ優先、なければ計算
POST /api/dashgen/generate        — race_id を受け取り dashgen 実行 → JSON 返却
POST /api/dashgen/compute_batch   — 日付+会場の全レースを一括計算して DB 保存
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.prediction.dashgen_adapter import build_dashgen_input
from backend.app.prediction.dashgen import generate_dashboard
from backend.app.prediction.dashgen_service import (
    get_cached_dashgen,
    save_dashgen_result,
    compute_dashgen_for_races,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── リクエストモデル ──────────────────────────────────────

class DashgenRequest(BaseModel):
    race_id: int


class DashgenBatchRequest(BaseModel):
    date: str
    venue: str


# ── 共通実行ロジック ──────────────────────────────────────

def _run_dashgen(race_id: int, force: bool = False) -> Dict[str, Any]:
    """race_id から DB キャッシュ取得 → なければ計算 → 結果 dict を返す。"""

    # DB キャッシュを確認（force=True の場合はスキップ）
    if not force:
        cached = get_cached_dashgen(race_id)
        if cached is not None:
            return cached

    # キャッシュなし → 計算実行
    try:
        entries, environment = build_dashgen_input(race_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("dashgen input build failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build dashgen input: {e}",
        )

    try:
        result = generate_dashboard(entries, environment)
    except Exception as e:
        logger.error("dashgen execution failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Dashgen execution failed: {e}",
        )

    result["race_id"] = race_id

    # 計算結果を DB に保存（失敗しても結果は返す）
    save_dashgen_result(race_id, result)

    return result


# ── エンドポイント ────────────────────────────────────────

@router.post("/generate")
async def generate_dashgen(body: DashgenRequest):
    """POST: race_id を受け取り dashgen を実行して結果を返す。"""
    return _run_dashgen(body.race_id)


@router.get("/{race_id}")
async def get_dashgen(race_id: int, force: bool = False):
    """GET: race_id を指定して dashgen 結果を返す。
    DB キャッシュがあればそれを返し、なければ計算して保存する。
    force=true で再計算を強制。
    """
    return _run_dashgen(race_id, force=force)


@router.post("/compute_batch")
async def compute_batch(body: DashgenBatchRequest):
    """POST: 日付+会場の全レースを一括計算して DB に保存する。
    スクレイピング完了後に自動呼び出しされる。
    """
    try:
        result = compute_dashgen_for_races(body.date, body.venue)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error("dashgen batch compute failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Batch compute failed: {e}",
        )
