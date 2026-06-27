"""
dashgen_adapter — Supabase DB → dashgen.generate_dashboard() 入力変換

boats テーブル（1行=1艇）と races テーブルから
generate_dashboard(entries, environment) に渡す dict を構築する。
足りないカラムはデフォルト値でフォールバックし、計算が止まらないようにする。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import get_supabase

logger = logging.getLogger(__name__)

# ── 会場コード → 会場名 ──────────────────────────────────
VENUE_CODE_TO_NAME: Dict[str, str] = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

# 愛知支部の会場（is_local_aichi 判定用）
AICHI_VENUES = {"蒲郡", "常滑"}

# 季節モーター交換月（各場で異なるが、一般的に4月・10月が多い）
# 交換月の初日〜翌月末を is_seasonal_motor=True とする簡易判定
SEASONAL_MOTOR_MONTHS = {4, 10}


# ═══════════════════════════════════════════════════════════
# ヘルパー
# ═══════════════════════════════════════════════════════════

def _safe_float(v: Any, default: float = 0.0) -> float:
    """None / 空文字 / 非数値を安全に float 変換。"""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _rank_to_class(rank: Optional[str]) -> str:
    """DB の rank (A1/A2/B1/B2 等) を class_label に変換。"""
    if not rank:
        return "B1"
    s = str(rank).upper().strip()
    if s in ("A1", "A2", "B1", "B2"):
        return s
    return "B1"


def _parse_day_no(day_str: Optional[str]) -> int:
    """venue_events.day カラム（例: '初日', '2日目', '最終日'）から日目数値を抽出。"""
    if not day_str:
        return 1
    s = str(day_str).strip()
    if "初日" in s:
        return 1
    if "最終" in s:
        return 6  # 最終日は通常5-7日目だが安全に6
    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))
    return 1


def _compute_sashi_rate(boat: dict, lane: int) -> float:
    """コース別差し率(%) = c{lane}_sashi / c{lane}_races * 100。"""
    sashi = _safe_int(boat.get(f"c{lane}_sashi"))
    races = _safe_int(boat.get(f"c{lane}_races"))
    if races > 0:
        return sashi / races * 100.0
    return 0.0


# ═══════════════════════════════════════════════════════════
# メイン変換: boat 行 → entry dict
# ═══════════════════════════════════════════════════════════

def _boat_to_entry(boat: dict, lane: int, venue_name: str) -> Dict[str, Any]:
    """boats テーブルの1行を dashgen entry dict に変換する。

    Args:
        boat: Supabase boats テーブルの行 dict
        lane: コース番号 (1-6)
        venue_name: 会場名（is_local_aichi 判定用）
    """
    # ── 基本情報 ──
    racer_name = boat.get("name") or ""
    rank = boat.get("rank") or ""
    age = _safe_int(boat.get("age"), 30)
    branch = boat.get("branch") or ""

    # ── class_label ──
    class_label = _rank_to_class(rank)

    # ── ST 関連 ──
    avg_st = _safe_float(boat.get("avg_st"), 0.15)
    course_avg_st = _safe_float(boat.get(f"c{lane}_avg_st"), avg_st)
    # current_st: 今節ST → today_st > exhibition_st > avg_st の優先順
    current_st = _safe_float(
        boat.get("today_st") or boat.get("exhibition_st"),
        avg_st,
    )

    # ── 今節着順 (current_result) ──
    # today_st_rank があればそれを使う。なければ 3.5（中間値）
    current_result = _safe_float(boat.get("today_st_rank"), 3.5)

    # ── F ステータス ──
    f_count = _safe_int(boat.get("f_count"))
    f_status: Optional[str] = None
    if f_count >= 2:
        f_status = "F2"
    elif f_count == 1:
        f_status = "F1未"

    # ── モーター ──
    deashi = _safe_float(boat.get("motor_dashfoot"), 50.0)
    nobi = _safe_float(boat.get("motor_extfoot"), 50.0)

    # ── コース別成績 ──
    course_win_rate = _safe_float(boat.get(f"c{lane}_win_rate"), 10.0)
    course_top3_rate = _safe_float(boat.get(f"c{lane}_tricast_rate"), 30.0)
    course_race_count = _safe_int(boat.get(f"c{lane}_races"))
    course_top2_rate = _safe_float(boat.get(f"c{lane}_place2_rate"), 20.0)

    # ── 当地成績 ──
    local_win_rate = _safe_float(boat.get("local_win_rate"), 10.0)
    local_top3_rate = _safe_float(boat.get("local_place2_rate"), 30.0)
    # local_place2_rate は DB 上 2連率だが、dashgen では local_top3_rate として
    # 3連率を期待。local5y_tricast_rate があればそちらを優先。
    local_top3_rate = _safe_float(
        boat.get("local5y_tricast_rate") or boat.get("local_place2_rate"),
        30.0,
    )
    local_race_count = _safe_int(
        boat.get("local5y_races") or boat.get("local_win_rate") and 10,
        0,
    )

    # ── 一般戦成績 ──
    general_top3_rate: Optional[float] = None
    general_race_count: Optional[int] = None
    ippan_top3 = boat.get("ippan_top3_rate")
    ippan_starts = boat.get("ippan_starts")
    if ippan_top3 is not None:
        general_top3_rate = _safe_float(ippan_top3)
        general_race_count = _safe_int(ippan_starts)

    # ── 決まり手 ──
    makuri = _safe_int(boat.get(f"c{lane}_makuri"))
    makurizashi = _safe_int(boat.get(f"c{lane}_makurizashi"))
    race_count = _safe_int(boat.get(f"c{lane}_races"))

    # ── 差し率 ──
    sashi_rate = _compute_sashi_rate(boat, lane)

    # ── 地元判定 ──
    is_local = bool(boat.get("is_local", False))
    is_local_aichi = is_local and venue_name in AICHI_VENUES

    return {
        "course": lane,
        "racer_name": racer_name,
        "average_st": avg_st,
        "course_average_st": course_avg_st,
        "current_st": current_st,
        "current_result": current_result,
        "f_status": f_status,
        "class_label": class_label,
        "age": age,
        "deashi": deashi,
        "nobi": nobi,
        "course_top3_rate": course_top3_rate,
        "course_race_count": course_race_count,
        "local_top3_rate": local_top3_rate,
        "local_race_count": local_race_count,
        "general_top3_rate": general_top3_rate,
        "general_race_count": general_race_count,
        "makuri": makuri,
        "makurizashi": makurizashi,
        "race_count": race_count,
        "sashi_rate": sashi_rate,
        "is_local_aichi": is_local_aichi,
        "is_local": is_local,
        "course_win_rate": course_win_rate,
        "local_win_rate": local_win_rate,
        "course_top2_rate": course_top2_rate,
        "racer_course_others": None,  # 後で1号のみセット
    }


# ═══════════════════════════════════════════════════════════
# racer_course_others 取得
# ═══════════════════════════════════════════════════════════

def _fetch_racer_course_others(
    sb,
    race_date: str,
    venue: str,
    race_no: int,
) -> Optional[Dict[str, Any]]:
    """racer_course_others テーブルから1号艇の対戦データを取得。"""
    try:
        resp = (
            sb.table("racer_course_others")
            .select("*")
            .eq("race_date", race_date)
            .eq("venue", venue)
            .eq("race_no", race_no)
            .eq("course", 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        # other_course をキーにした dict に変換
        result: Dict[str, Any] = {}
        for row in rows:
            oc = row.get("other_course")
            if oc is not None:
                result[str(oc)] = {
                    "win_rate": _safe_float(row.get("win_rate")),
                    "top2_rate": _safe_float(row.get("top2_rate")),
                    "top3_rate": _safe_float(row.get("top3_rate")),
                    "starts": _safe_int(row.get("starts")),
                    "sashi": _safe_int(row.get("sashi")),
                    "makuri": _safe_int(row.get("makuri")),
                    "makuri_sashi": _safe_int(row.get("makuri_sashi")),
                }
        return result if result else None
    except Exception as e:
        logger.warning("racer_course_others 取得失敗: %s", e)
        return None


# ═══════════════════════════════════════════════════════════
# venue_calibration 取得
# ═══════════════════════════════════════════════════════════

def _compute_venue_calibration(sb, venue: str) -> Optional[Dict[str, Any]]:
    """race_winner_log から当節較正データ（r, n）を算出。
    races.py の _compute_escape_calibration と同等ロジック。
    """
    try:
        resp = (
            sb.table("race_winner_log")
            .select("winner_course")
            .eq("venue", venue)
            .order("date", desc=True)
            .limit(60)
            .execute()
        )
        rows = resp.data or []
    except Exception:
        return None

    n = len(rows)
    if n == 0:
        return None
    in_head = sum(1 for r in rows if _safe_int(r.get("winner_course")) == 1)
    return {"r": in_head / n, "n": n}


# ═══════════════════════════════════════════════════════════
# day_no 取得
# ═══════════════════════════════════════════════════════════

def _fetch_day_no(sb, race_date: str, venue: str) -> int:
    """venue_events テーブルから day_no を取得。"""
    try:
        resp = (
            sb.table("venue_events")
            .select("day")
            .eq("date", race_date)
            .eq("venue", venue)
            .maybe_single()
            .execute()
        )
        if resp.data:
            return _parse_day_no(resp.data.get("day"))
    except Exception:
        pass
    # races テーブルの day_no フォールバック
    return 1


# ═══════════════════════════════════════════════════════════
# 公開API: race_id → (entries, environment)
# ═══════════════════════════════════════════════════════════

def build_dashgen_input(race_id: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Supabase DB から race_id に対応するデータを取得し、
    dashgen.generate_dashboard() に渡す (entries, environment) を返す。

    Args:
        race_id: races テーブルの id

    Returns:
        (entries, environment) タプル

    Raises:
        ValueError: レースまたはボートデータが見つからない場合
    """
    sb = get_supabase()

    # ── races テーブル取得 ──
    race_resp = sb.table("races").select("*").eq("id", race_id).maybe_single().execute()
    if not race_resp.data:
        raise ValueError(f"Race not found: id={race_id}")
    race = race_resp.data

    # ── boats テーブル取得 ──
    boats_resp = (
        sb.table("boats")
        .select("*, players(name, rank, registration_no, branch)")
        .eq("race_id", race_id)
        .order("lane")
        .execute()
    )
    boats = boats_resp.data or []
    if len(boats) < 6:
        raise ValueError(
            f"Insufficient boat data: race_id={race_id}, got {len(boats)} boats (need 6)"
        )

    # player 情報をフラット化（races.py と同じパターン）
    for boat in boats:
        player = boat.pop("players", None) or {}
        boat["name"] = boat.get("name") or player.get("name", "")
        boat["rank"] = boat.get("rank") or player.get("rank", "")
        if not boat.get("branch"):
            boat["branch"] = player.get("branch", "")

    # ── 会場名 ──
    venue_name = race.get("venue", "")

    # ── entries 構築 ──
    entries: List[Dict[str, Any]] = []
    for boat in boats[:6]:
        lane = _safe_int(boat.get("lane"), len(entries) + 1)
        entry = _boat_to_entry(boat, lane, venue_name)
        entries.append(entry)

    # ── 1号艇の racer_course_others ──
    race_date = race.get("date", "")
    race_no = _safe_int(race.get("race_no"))
    if race_date and venue_name and race_no:
        rco = _fetch_racer_course_others(sb, race_date, venue_name, race_no)
        if rco:
            entries[0]["racer_course_others"] = rco

    # ── environment 構築 ──
    day_no = _safe_int(race.get("day_no"), 0)
    if day_no <= 0:
        day_no = _fetch_day_no(sb, race_date, venue_name)

    # 月の取得
    month = 4  # デフォルト
    if race_date:
        try:
            if isinstance(race_date, str):
                dt = datetime.strptime(race_date, "%Y-%m-%d")
            else:
                dt = race_date
            month = dt.month
        except (ValueError, AttributeError):
            pass

    # is_seasonal_motor: 簡易判定（交換月±1ヶ月）
    is_seasonal_motor = month in SEASONAL_MOTOR_MONTHS

    # venue_calibration
    venue_calibration = _compute_venue_calibration(sb, venue_name)

    environment: Dict[str, Any] = {
        "venue": venue_name,
        "wind_dir": race.get("wind_direction") or "無風",
        "wind_speed": _safe_float(race.get("wind_speed"), 0.0),
        "race_number": race_no,
        "day_no": day_no,
        "month": month,
        "is_seasonal_motor": is_seasonal_motor,
        "venue_calibration": venue_calibration,
    }

    return entries, environment
