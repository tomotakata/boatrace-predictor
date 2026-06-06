from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.app.config import get_supabase
import json

router = APIRouter()


class VenueConfigIn(BaseModel):
    venue_name: str
    prompt_version: Optional[str] = None
    water_type: Optional[str] = None
    has_tide_correction: Optional[bool] = False
    tide_max_m: Optional[float] = None
    altitude_m: Optional[float] = None
    back_width_m: Optional[float] = None
    home_width_m: Optional[float] = None

    c1_rate_default: Optional[float] = None
    c2_rate: Optional[float] = None
    c3_rate: Optional[float] = None
    c4_rate: Optional[float] = None
    c5_rate: Optional[float] = None
    c6_rate: Optional[float] = None
    c1_rate_spring: Optional[float] = None
    c1_rate_summer: Optional[float] = None
    c1_rate_autumn: Optional[float] = None
    c1_rate_winter: Optional[float] = None

    surface_type: Optional[str] = None
    pattern_a_threshold: Optional[float] = 0.45
    main_attack_description: Optional[str] = None
    main_attack_patterns: Optional[list] = None

    kad_c2: Optional[float] = 1.00
    kad_c3: Optional[float] = 1.10
    kad_c4: Optional[float] = 1.20
    kad_c5: Optional[float] = 1.05
    kad_c6: Optional[float] = 1.00

    home_branch: Optional[str] = None
    home_n_upper: Optional[float] = 1.30
    home_n_lower: Optional[float] = 0.75
    home_min_races: Optional[int] = 10

    motor_exchange_months: Optional[list] = None
    motor_exchange_f_weight: Optional[float] = 0.85
    motor_exchange_n_upper: Optional[float] = 1.20

    scheduled_races: Optional[list] = None
    body_weight_correction: Optional[bool] = False
    exhibit_public: Optional[bool] = True
    is_nighter: Optional[bool] = False
    is_morning: Optional[bool] = False
    is_midnight: Optional[bool] = False

    tide_effects: Optional[dict] = None
    wind_effects: Optional[dict] = None
    seasonal_notes: Optional[dict] = None
    race_no_corrections: Optional[list] = None

    notes: Optional[str] = None
    raw_prompt_text: Optional[str] = None


@router.get("/")
async def list_venues():
    """全会場設定一覧"""
    sb = get_supabase()
    resp = sb.table("venue_configs").select(
        "id, venue_name, prompt_version, water_type, surface_type, "
        "has_tide_correction, c1_rate_default, c1_rate_spring, c1_rate_summer, "
        "c1_rate_autumn, c1_rate_winter, main_attack_description, home_branch, "
        "is_nighter, is_morning, updated_at"
    ).order("venue_name").execute()
    return resp.data


@router.get("/{venue_name}")
async def get_venue(venue_name: str):
    """会場設定詳細取得"""
    sb = get_supabase()
    resp = sb.table("venue_configs").select("*").eq("venue_name", venue_name).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail=f"会場 '{venue_name}' の設定が見つかりません")
    return resp.data[0]


@router.post("/")
async def create_venue(body: VenueConfigIn):
    """新規会場設定登録"""
    sb = get_supabase()
    data = body.dict(exclude_none=False)
    # None除外
    data = {k: v for k, v in data.items() if v is not None}
    try:
        resp = sb.table("venue_configs").insert(data).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{venue_name}")
async def update_venue(venue_name: str, body: VenueConfigIn):
    """会場設定更新"""
    sb = get_supabase()
    # 存在確認
    existing = sb.table("venue_configs").select("id").eq("venue_name", venue_name).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"会場 '{venue_name}' の設定が見つかりません")

    data = body.dict(exclude_none=False)
    data = {k: v for k, v in data.items() if v is not None}
    data.pop("venue_name", None)  # 主キーは更新しない

    resp = sb.table("venue_configs").update(data).eq("venue_name", venue_name).execute()
    return resp.data[0]


@router.delete("/{venue_name}")
async def delete_venue(venue_name: str):
    """会場設定削除"""
    sb = get_supabase()
    sb.table("venue_configs").delete().eq("venue_name", venue_name).execute()
    return {"message": f"会場 '{venue_name}' の設定を削除しました"}


@router.post("/migrate")
async def run_migration():
    """venue_configsテーブルを作成（初回のみ）"""
    sb = get_supabase()
    # テスト挿入で存在確認
    try:
        sb.table("venue_configs").select("id").limit(1).execute()
        return {"message": "テーブルは既に存在します"}
    except Exception:
        pass

    # psycopg2で直接作成
    import os
    try:
        import psycopg2
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL not set")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        migration_path = os.path.join(os.path.dirname(__file__), "../../../supabase/migrations/002_venue_configs.sql")
        with open(migration_path) as f:
            cur.execute(f.read())
        conn.commit()
        conn.close()
        return {"message": "Migration completed"}
    except ImportError:
        raise HTTPException(status_code=500, detail="psycopg2 not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
