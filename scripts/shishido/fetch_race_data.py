#!/usr/bin/env python3
"""
fetch_race_data.py  –  DB → V-4 入力スキーマ変換スクリプト

日付 + 会場 + レース番号を指定して Supabase DB からデータを取得し、
v58.7 の V-4 入力スキーマ JSON を出力する。

Usage:
    python scripts/shishido/fetch_race_data.py --date 2026-06-23 --venue びわこ --race 1
    python scripts/shishido/fetch_race_data.py --date 2026-06-23 --venue びわこ          # 全レース
    python scripts/shishido/fetch_race_data.py --date 2026-06-23 --venue びわこ --race 1 -o out.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    # プロジェクトルートの .env を読み込む
    _project_root = Path(__file__).resolve().parents[2]
    load_dotenv(_project_root / ".env")
except ImportError:
    # Vercel 環境では dotenv 不要（環境変数は設定済み）
    pass

from supabase import create_client, Client

# dashgen 統合: プロジェクトルートを sys.path に追加して backend モジュールを import 可能にする
_project_root_for_import = Path(__file__).resolve().parents[2]
if str(_project_root_for_import) not in sys.path:
    sys.path.insert(0, str(_project_root_for_import))

from backend.app.prediction.dashgen import generate_dashboard  # noqa: E402
from backend.app.prediction.dashgen_service import get_cached_dashgen  # noqa: E402


# ---------------------------------------------------------------------------
# Supabase 接続
# ---------------------------------------------------------------------------

def _get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が .env に設定されていません")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# 風向き変換ヘルパー
# ---------------------------------------------------------------------------

_WIND_EFFECT_MAP = {
    # (direction, speed_range) → wind_effect label
    # direction は DB の生値（東, 西, 南, 北, 北東, 南西 …）
    # speed_range は (min, max) の m/s
}


def _wind_effect(direction: Optional[str], speed: Optional[float]) -> str:
    """風向き + 風速 → V-4 の wind_effect 文字列を生成"""
    if not direction or speed is None:
        return "不明"
    # 追い風 / 向かい風 の判定は会場依存だが、簡易的に方角をそのまま使う
    d = direction.strip()
    s = int(round(speed))
    if s == 0:
        return "無風"
    return f"{d}{s}m"


def _classify_wind_direction(direction: Optional[str]) -> str:
    """DB の風向き（東, 西, 南西 等）→ V-4 の wind_direction（追い風/向かい風/横風/不明）"""
    if not direction:
        return "不明"
    # 簡易分類: 実際の追い/向かいは会場のコースレイアウト依存
    # ここでは生値をそのまま返す（v58.7 側で解釈する）
    return direction.strip()


# ---------------------------------------------------------------------------
# DB → V-4 変換
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val)


def _convert_boat(boat: dict, player: dict | None, entry_course: int) -> dict:
    """boats テーブル 1行 + players テーブル → V-4 entries[] の 1要素"""

    course = entry_course
    lane = boat.get("lane", course)

    # コース別成績: entry_course に対応する c{n}_* を取得
    c_prefix = f"c{course}_"
    course_win_rate = _safe_float(boat.get(f"{c_prefix}win_rate"))
    course_place2_rate = _safe_float(boat.get(f"{c_prefix}place2_rate"))
    course_tricast_rate = _safe_float(boat.get(f"{c_prefix}tricast_rate"))
    course_races = _safe_int(boat.get(f"{c_prefix}races"))
    course_makuri = _safe_int(boat.get(f"{c_prefix}makuri"))
    course_makurizashi = _safe_int(boat.get(f"{c_prefix}makurizashi"))
    course_sashi = _safe_int(boat.get(f"{c_prefix}sashi"))
    course_nige = _safe_int(boat.get(f"{c_prefix}nige"))

    # player 情報
    p_name = player["name"].replace("\u3000", " ").strip() if player else "不明"
    p_rank = _safe_str(player.get("rank") if player else None, "不明")
    p_branch = _safe_str(player.get("branch") if player else None, "不明")

    return {
        "course": course,
        "frame": lane,
        "name": p_name,
        "class": p_rank,
        "age": _safe_int(boat.get("age")),
        "branch": p_branch,
        "f_count": _safe_str(boat.get("f_count"), ""),
        "motor": {
            "deashi": _safe_float(boat.get("motor_dashfoot")),
            "nobi": _safe_float(boat.get("motor_extfoot")),
            "eval": _safe_str(boat.get("motor_eval")),
            "motor_no": _safe_int(boat.get("motor_no")),
            "place2_rate": _safe_float(boat.get("motor_place2_rate")),
        },
        "start": {
            "average_st": _safe_float(boat.get("avg_st")),
            "course_average_st": _safe_float(boat.get("course1y_st")),
            "current_st": _safe_float(boat.get("today_st")),
            "current_order": _safe_int(boat.get("today_st_rank")),
            "standard_st": _safe_float(boat.get("standard_st")),
            "st_advantage_rank": _safe_int(boat.get("st_advantage_rank")),
        },
        "course_stats": {
            "starts": course_races,
            "win_rate": course_win_rate,
            "top2_rate": course_place2_rate,
            "top3_rate": course_tricast_rate,
            "nige": course_nige,
            "makuri": course_makuri,
            "makuri_sashi": course_makurizashi,
            "sashi": course_sashi,
        },
        "local_stats": {
            "starts": _safe_int(boat.get("local5y_races")),
            "win_rate": _safe_float(boat.get("local5y_win_rate")),
            "top2_rate": _safe_float(boat.get("local5y_place2_rate")),
            "top3_rate": _safe_float(boat.get("local5y_tricast_rate")),
            "sashi": _safe_int(boat.get("local5y_sashi")),
            "makuri": _safe_int(boat.get("local5y_makuri")),
            "makuri_sashi": _safe_int(boat.get("local5y_makurizashi")),
        },
        "national": {
            "win_rate": _safe_float(boat.get("national_win_rate")),
            "top2_rate": _safe_float(boat.get("national_place2_rate")),
            "top3_rate": _safe_float(boat.get("national_place3_rate")),
        },
        "ippan": {
            "starts": _safe_int(boat.get("general1y_races")),
            "win_rate": _safe_float(boat.get("general1y_win_rate")),
            "top2_rate": _safe_float(boat.get("general1y_place2_rate")),
            "top3_rate": _safe_float(boat.get("general1y_tricast_rate")),
            "sashi": _safe_int(boat.get("general1y_sashi")),
            "makuri": _safe_int(boat.get("general1y_makuri")),
            "makuri_sashi": _safe_int(boat.get("general1y_makurizashi")),
        },
        "escape1y": {
            "top2_rate": _safe_float(boat.get("escape1y_place2_rate")),
            "top3_rate": _safe_float(boat.get("escape1y_tricast_rate")),
        },
        "exhibition": {
            "time": _safe_float(boat.get("exhibition_time")),
            "st": _safe_float(boat.get("exhibition_st")),
            "lap1": _safe_float(boat.get("exhibition_1lap")),
            "turning": _safe_float(boat.get("exhibition_turning")),
            "straight": _safe_float(boat.get("exhibition_straight")),
        },
    }


# ---------------------------------------------------------------------------
# dashgen 入力変換（dashgen_adapter.py の _boat_to_entry 相当）
# ---------------------------------------------------------------------------

# 愛知支部の会場（is_local_aichi 判定用）
_AICHI_VENUES = {"蒲郡", "常滑"}

# 季節モーター交換月
_SEASONAL_MOTOR_MONTHS = {4, 10}


def _rank_to_class(rank: Optional[str]) -> str:
    """DB の rank (A1/A2/B1/B2 等) を class_label に変換。"""
    if not rank:
        return "B1"
    s = str(rank).upper().strip()
    if s in ("A1", "A2", "B1", "B2"):
        return s
    return "B1"


def _compute_sashi_rate(boat: dict, lane: int) -> float:
    """コース別差し率(%) = c{lane}_sashi / c{lane}_races * 100。"""
    sashi = _safe_int(boat.get(f"c{lane}_sashi"))
    races = _safe_int(boat.get(f"c{lane}_races"))
    if races > 0:
        return sashi / races * 100.0
    return 0.0


def _boat_to_dashgen_entry(boat: dict, player: dict | None, lane: int, venue_name: str) -> dict:
    """boats テーブル 1行 → dashgen entry dict に変換"""
    rank = player.get("rank", "") if player else ""
    class_label = _rank_to_class(rank)
    avg_st = _safe_float(boat.get("avg_st"), 0.15)
    course_avg_st = _safe_float(boat.get(f"c{lane}_avg_st"), avg_st)
    current_st = _safe_float(
        boat.get("today_st") or boat.get("exhibition_st"),
        avg_st,
    )
    current_result = _safe_float(boat.get("today_st_rank"), 3.5)

    f_count = _safe_int(boat.get("f_count"))
    f_status: Optional[str] = None
    if f_count >= 2:
        f_status = "F2"
    elif f_count == 1:
        f_status = "F1未"

    deashi = _safe_float(boat.get("motor_dashfoot"), 50.0)
    nobi = _safe_float(boat.get("motor_extfoot"), 50.0)

    course_win_rate = _safe_float(boat.get(f"c{lane}_win_rate"), 10.0)
    course_top3_rate = _safe_float(boat.get(f"c{lane}_tricast_rate"), 30.0)
    course_race_count = _safe_int(boat.get(f"c{lane}_races"))
    course_top2_rate = _safe_float(boat.get(f"c{lane}_place2_rate"), 20.0)

    local_top3_rate = _safe_float(
        boat.get("local5y_tricast_rate") or boat.get("local_place2_rate"),
        30.0,
    )
    local_race_count = _safe_int(boat.get("local5y_races"), 0)
    local_win_rate = _safe_float(boat.get("local5y_win_rate") or boat.get("local_win_rate"), 10.0)

    makuri = _safe_int(boat.get(f"c{lane}_makuri"))
    makurizashi = _safe_int(boat.get(f"c{lane}_makurizashi"))
    race_count = _safe_int(boat.get(f"c{lane}_races"))
    sashi_rate = _compute_sashi_rate(boat, lane)

    is_local = bool(boat.get("is_local", False))
    is_local_aichi = is_local and venue_name in _AICHI_VENUES

    return {
        "course": lane,
        "racer_name": (player.get("name", "") if player else "").replace("\u3000", " ").strip(),
        "average_st": avg_st,
        "course_average_st": course_avg_st,
        "current_st": current_st,
        "current_result": current_result,
        "f_status": f_status,
        "class_label": class_label,
        "age": _safe_int(boat.get("age"), 30),
        "deashi": deashi,
        "nobi": nobi,
        "course_top3_rate": course_top3_rate,
        "course_race_count": course_race_count,
        "local_top3_rate": local_top3_rate,
        "local_race_count": local_race_count,
        "general_top3_rate": None,
        "general_race_count": None,
        "makuri": makuri,
        "makurizashi": makurizashi,
        "race_count": race_count,
        "sashi_rate": sashi_rate,
        "is_local_aichi": is_local_aichi,
        "is_local": is_local,
        "course_win_rate": course_win_rate,
        "local_win_rate": local_win_rate,
        "course_top2_rate": course_top2_rate,
        "racer_course_others": None,
    }


def _fetch_racer_course_others(sb: Client, race_date: str, venue: str, race_no: int) -> dict | None:
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
        result: dict = {}
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
    except Exception:
        return None


def _compute_venue_calibration(sb: Client, venue: str) -> dict | None:
    """race_winner_log から当節較正データ（r, n）を算出。"""
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


def _fetch_day_no(sb: Client, race_date: str, venue: str) -> int:
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
            import re as _re
            s = str(resp.data.get("day", "")).strip()
            if "初日" in s:
                return 1
            if "最終" in s:
                return 6
            m = _re.search(r"(\d+)", s)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return 1


def _run_dashgen(
    sb: Client,
    race: dict,
    boats_data: list[dict],
    players_map: dict[int, dict],
    venue: str,
) -> dict | None:
    """DB の race/boats データから dashgen.generate_dashboard() を実行して結果を返す。

    まず DB キャッシュ（dashgen_results テーブル）を確認し、
    計算済みであればそれを返す。なければ計算して返す。

    Returns:
        dashgen の出力 dict、またはエラー時 None
    """
    from datetime import datetime

    # DB キャッシュを確認
    race_id = race.get("id")
    if race_id:
        cached = get_cached_dashgen(race_id)
        if cached is not None:
            # cached フラグを除去して返す
            cached.pop("cached", None)
            cached.pop("calculated_at", None)
            cached.pop("race_id", None)
            return cached

    try:
        # dashgen 用 entries 構築
        dg_entries = []
        for boat in boats_data[:6]:
            lane = boat.get("entry_course") or boat.get("lane", len(dg_entries) + 1)
            player = players_map.get(boat.get("player_id"))
            entry = _boat_to_dashgen_entry(boat, player, lane, venue)
            dg_entries.append(entry)

        # コース順にソート
        dg_entries.sort(key=lambda e: e["course"])

        # 1号艇の racer_course_others
        race_date = race.get("date", "")
        race_no_val = _safe_int(race.get("race_no"))
        if race_date and venue and race_no_val:
            rco = _fetch_racer_course_others(sb, race_date, venue, race_no_val)
            if rco:
                dg_entries[0]["racer_course_others"] = rco

        # environment 構築
        day_no = _safe_int(race.get("day_no"), 0)
        if day_no <= 0:
            day_no = _fetch_day_no(sb, race_date, venue)

        month = 4
        if race_date:
            try:
                dt = datetime.strptime(str(race_date), "%Y-%m-%d")
                month = dt.month
            except (ValueError, AttributeError):
                pass

        is_seasonal_motor = month in _SEASONAL_MOTOR_MONTHS
        venue_calibration = _compute_venue_calibration(sb, venue)

        dg_environment = {
            "venue": venue,
            "wind_dir": race.get("wind_direction") or "無風",
            "wind_speed": _safe_float(race.get("wind_speed"), 0.0),
            "race_number": race_no_val,
            "day_no": day_no,
            "month": month,
            "is_seasonal_motor": is_seasonal_motor,
            "venue_calibration": venue_calibration,
        }

        # dashgen 実行
        result = generate_dashboard(dg_entries, dg_environment)
        return result

    except Exception as e:
        print(f"WARNING: dashgen 計算エラー: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# DB → V-4 変換
# ---------------------------------------------------------------------------

def fetch_race_v4(
    sb: Client,
    date: str,
    venue: str,
    race_no: int,
) -> dict | None:
    """1 レース分の V-4 JSON を生成して返す（dashgen 計算結果付き）"""

    # races テーブルから取得
    res = (
        sb.table("races")
        .select("*")
        .eq("date", date)
        .eq("venue", venue)
        .eq("race_no", race_no)
        .execute()
    )
    if not res.data:
        print(f"WARNING: レースが見つかりません: {date} {venue} R{race_no}", file=sys.stderr)
        return None

    race = res.data[0]
    race_id = race["id"]

    # boats テーブルから取得
    boats_res = (
        sb.table("boats")
        .select("*")
        .eq("race_id", race_id)
        .order("lane")
        .execute()
    )
    if not boats_res.data:
        print(f"WARNING: ボートデータがありません: race_id={race_id}", file=sys.stderr)
        return None

    # player_id → players テーブルを一括取得
    player_ids = [b["player_id"] for b in boats_res.data if b.get("player_id")]
    players_map: dict[int, dict] = {}
    if player_ids:
        pl_res = sb.table("players").select("*").in_("id", player_ids).execute()
        for p in pl_res.data:
            players_map[p["id"]] = p

    # 各艇を V-4 形式に変換
    entries = []
    for boat in boats_res.data:
        entry_course = boat.get("entry_course") or boat.get("lane", 0)
        player = players_map.get(boat.get("player_id"))
        entries.append(_convert_boat(boat, player, entry_course))

    # コース順にソート
    entries.sort(key=lambda e: e["course"])

    # 環境情報
    environment = {
        "weather": _safe_str(race.get("weather"), "不明"),
        "wind_speed_mps": _safe_float(race.get("wind_speed")),
        "wind_direction": _classify_wind_direction(race.get("wind_direction")),
        "wind_effect": _wind_effect(race.get("wind_direction"), race.get("wind_speed")),
        "wave_height_cm": _safe_float(race.get("wave_height")),
    }

    # day_no → 日目表記
    day_no = race.get("day_no")
    day_label = f"{day_no}日目" if day_no else "不明"

    # dashgen 計算実行
    dashgen_result = _run_dashgen(sb, race, boats_res.data, players_map, venue)

    result = {
        "venue": venue,
        "date": date,
        "race_no": race_no,
        "race_id": race_id,
        "day": day_label,
        "status": _safe_str(race.get("status"), "scheduled"),
        "entries": entries,
        "environment": environment,
    }

    if dashgen_result is not None:
        result["dashgen"] = dashgen_result

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Supabase DB → V-4 入力スキーマ JSON 変換"
    )
    parser.add_argument("--date", required=True, help="日付 (YYYY-MM-DD)")
    parser.add_argument("--venue", required=True, help="会場名 (例: びわこ)")
    parser.add_argument("--race", type=int, default=None, help="レース番号 (省略時: 全レース)")
    parser.add_argument("-o", "--output", default=None, help="出力ファイルパス (省略時: stdout)")
    parser.add_argument("--pretty", action="store_true", default=True, help="整形出力 (デフォルト: True)")
    args = parser.parse_args()

    sb = _get_supabase()

    if args.race is not None:
        # 単一レース
        result = fetch_race_v4(sb, args.date, args.venue, args.race)
        if result is None:
            sys.exit(1)
        output = result
    else:
        # 全レース
        results = []
        for rno in range(1, 13):
            r = fetch_race_v4(sb, args.date, args.venue, rno)
            if r is not None:
                results.append(r)
        if not results:
            print(f"ERROR: {args.date} {args.venue} のレースが見つかりません", file=sys.stderr)
            sys.exit(1)
        output = results

    indent = 2 if args.pretty else None
    json_str = json.dumps(output, ensure_ascii=False, indent=indent)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"出力: {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
