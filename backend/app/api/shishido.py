"""
宍戸予想 v58.7 API ルーター

POST /predict  — 日付+会場を受け取り、predict.py を実行して結果を返す
GET  /venues   — 指定日の開催会場一覧を返す
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ---------------------------------------------------------------------------
# プロジェクトルート解決
# ---------------------------------------------------------------------------
# Vercel 環境: /var/task がルート
# ローカル環境: backend/app/api/shishido.py → 4つ上がプロジェクトルート
_this_dir = Path(__file__).resolve().parent
_project_root = Path("/var/task") if Path("/var/task/scripts").exists() else _this_dir.parents[3]

# scripts/shishido を import パスに追加
_shishido_dir = _project_root / "scripts" / "shishido"
if str(_shishido_dir) not in sys.path:
    sys.path.insert(0, str(_shishido_dir))

# ---------------------------------------------------------------------------
# Supabase 接続（遅延初期化）
# ---------------------------------------------------------------------------
_supabase_client = None


def _get_sb():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY が未設定です")
        _supabase_client = create_client(url, key)
    return _supabase_client


# ---------------------------------------------------------------------------
# リクエスト / レスポンスモデル
# ---------------------------------------------------------------------------

class PredictRequest(BaseModel):
    date: str
    venue: str
    race_no: Optional[int] = None  # None = 全レース


# ---------------------------------------------------------------------------
# GET /venues?date=YYYY-MM-DD
# ---------------------------------------------------------------------------

@router.get("/venues")
async def get_venues(date: str):
    """指定日の開催会場一覧を返す"""
    try:
        sb = _get_sb()
        res = (
            sb.table("races")
            .select("venue")
            .eq("date", date)
            .execute()
        )
        if not res.data:
            return {"date": date, "venues": []}

        # ユニークな会場名を抽出
        venues = sorted(set(r["venue"] for r in res.data if r.get("venue")))
        return {"date": date, "venues": venues}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------

@router.post("/predict")
async def predict(req: PredictRequest):
    """宍戸予想を実行して結果を返す"""
    try:
        # predict.py の関数を動的 import
        from fetch_race_data import fetch_race_v4, _get_supabase as _get_sb_script
        from predict import _load_system_prompt, _call_claude, _extract_json, MODEL

        sb = _get_sb()
        system_prompt = _load_system_prompt()

        if req.race_no is not None:
            # 単一レース
            from predict import predict_race
            result = predict_race(sb, req.date, req.venue, req.race_no, system_prompt)
            return {"date": req.date, "venue": req.venue, "results": [result]}
        else:
            # 全レース (1-12)
            results = []
            for rno in range(1, 13):
                from predict import predict_race
                result = predict_race(sb, req.date, req.venue, rno, system_prompt)
                results.append(result)
            return {"date": req.date, "venue": req.venue, "results": results}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
