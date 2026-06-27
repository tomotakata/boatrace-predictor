"""
dashgen_router — ダッシュボード生成 API エンドポイント

POST /api/dashgen/generate  — race_id を受け取り dashgen 実行 → JSON 返却
GET  /api/dashgen/{race_id} — 同上（GET 版）
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.prediction.dashgen_adapter import build_dashgen_input
from backend.app.prediction.dashgen import generate_dashboard

router = APIRouter()
logger = logging.getLogger(__name__)


# ── リクエストモデル ──────────────────────────────────────

class DashgenRequest(BaseModel):
    race_id: int


# ── 共通実行ロジック ──────────────────────────────────────

def _run_dashgen(race_id: int) -> Dict[str, Any]:
    """race_id から DB データ取得 → dashgen 実行 → 結果 dict を返す。"""
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
    return result


# ── エンドポイント ────────────────────────────────────────

@router.post("/generate")
async def generate_dashgen(body: DashgenRequest):
    """POST: race_id を受け取り dashgen を実行して結果を返す。"""
    return _run_dashgen(body.race_id)


@router.get("/{race_id}")
async def get_dashgen(race_id: int):
    """GET: race_id を指定して dashgen を実行して結果を返す。"""
    return _run_dashgen(race_id)
