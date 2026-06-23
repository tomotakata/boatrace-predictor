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

from dotenv import load_dotenv

# プロジェクトルートの .env を読み込む
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

from supabase import create_client, Client


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


def fetch_race_v4(
    sb: Client,
    date: str,
    venue: str,
    race_no: int,
) -> dict | None:
    """1 レース分の V-4 JSON を生成して返す"""

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

    return {
        "venue": venue,
        "date": date,
        "race_no": race_no,
        "race_id": race_id,
        "day": day_label,
        "status": _safe_str(race.get("status"), "scheduled"),
        "entries": entries,
        "environment": environment,
    }


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
