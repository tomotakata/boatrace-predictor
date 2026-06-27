#!/usr/bin/env python3
"""
run_prediction.py  –  宍戸予想 エンドツーエンドパイプライン

日付+会場を指定するだけで DB取得→データ整形→Claude API→買い目出力 の
全フローを1コマンドで実行する統合CLIスクリプト。

Usage:
    # 1レース分の予想
    python scripts/shishido/run_prediction.py --date 2026-06-23 --venue びわこ --race 1

    # 全12レース予想
    python scripts/shishido/run_prediction.py --date 2026-06-23 --venue びわこ

    # モデル指定
    python scripts/shishido/run_prediction.py --date 2026-06-23 --venue びわこ --race 1 --model claude-sonnet-4-5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 環境セットアップ
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
    _project_root = Path(__file__).resolve().parents[2]
    load_dotenv(_project_root / ".env")
except ImportError:
    _project_root = Path(__file__).resolve().parents[2]

# 同ディレクトリのモジュールを import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_race_data import fetch_race_v4, _get_supabase  # noqa: E402
from predict import (  # noqa: E402
    predict_race,
    _load_system_prompt,
    _extract_json,
    MODEL,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
INTER_RACE_DELAY = 2  # レース間のsleep秒数（レート制限対策）

# 全24会場
VALID_VENUES = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
    "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
    "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
    "下関", "若松", "芦屋", "福岡", "唐津", "大村",
]


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------

def _validate_date(date_str: str) -> str:
    """日付フォーマットを検証して返す"""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        sys.exit(f"ERROR: 日付フォーマットが不正です: {date_str} (YYYY-MM-DD形式で指定)")


def _validate_venue(venue: str) -> str:
    """会場名を検証して返す"""
    if venue in VALID_VENUES:
        return venue
    # 部分一致を試す
    matches = [v for v in VALID_VENUES if venue in v or v in venue]
    if len(matches) == 1:
        return matches[0]
    if matches:
        sys.exit(f"ERROR: 会場名が曖昧です: {venue} → 候補: {', '.join(matches)}")
    sys.exit(
        f"ERROR: 不明な会場名: {venue}\n"
        f"有効な会場: {', '.join(VALID_VENUES)}"
    )


def _check_races_exist(sb: Any, date: str, venue: str) -> list[int]:
    """指定日・会場にレースが存在するか確認し、レース番号リストを返す"""
    res = (
        sb.table("races")
        .select("race_no")
        .eq("date", date)
        .eq("venue", venue)
        .order("race_no")
        .execute()
    )
    if not res.data:
        sys.exit(
            f"ERROR: {date} {venue} のレースデータがDBに存在しません。\n"
            f"開催日・会場名を確認してください。"
        )
    return sorted([r["race_no"] for r in res.data])


# ---------------------------------------------------------------------------
# 結果保存
# ---------------------------------------------------------------------------

def _save_output(results: list[dict], date: str, venue: str) -> Path:
    """結果をJSONファイルに保存"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date}_{venue}.json"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# コンソールサマリー表示
# ---------------------------------------------------------------------------

def _print_race_summary(result: dict) -> None:
    """1レース分のサマリーをコンソールに表示"""
    race_no = result.get("race_no", "?")
    status = result.get("status", "unknown")

    if status == "error":
        print(f"  R{race_no}: ⚠ スキップ ({result.get('error', '不明なエラー')})")
        return

    if status == "parse_error":
        print(f"  R{race_no}: ⚠ JSONパース失敗（raw text保存済み）")
        return

    if status != "ok":
        print(f"  R{race_no}: ⚠ ステータス: {status}")
        return

    pred = result.get("prediction", {})
    analysis = pred.get("analysis", {})

    # 攻め主体
    atk = analysis.get("attack_subject", {})
    atk_str = ""
    if atk:
        atk_str = f"{atk.get('course', '?')}コース {atk.get('type', '?')} ({atk.get('attack_type', '?')})"

    # レース分類
    race_class = analysis.get("race_class", "不明")

    # 本線
    honsen = analysis.get("honsen_12", [])
    honsen_str = ", ".join(honsen[:6]) if honsen else "なし"
    if len(honsen) > 6:
        honsen_str += f" ... (計{len(honsen)}点)"

    # 2連単
    exacta = analysis.get("exacta_top", [])
    exacta_str = ", ".join(exacta) if exacta else "なし"

    # スイチ
    suichi = analysis.get("suichi", [])
    suichi_str = ", ".join(suichi) if suichi else "なし"

    print(f"  R{race_no}: [{race_class}] 攻め主体={atk_str}")
    print(f"       本線: {honsen_str}")
    print(f"       2連単: {exacta_str}  スイチ: {suichi_str}")


def _print_dashboard_summary(result: dict) -> None:
    """ダッシュボード数値のサマリー表示"""
    pred = result.get("prediction", {})
    analysis = pred.get("analysis", {})
    dashboard = analysis.get("dashboard", {})

    if not dashboard:
        return

    header = "       コース  EI    TI    P1    逃げ   着内   2着"
    print(header)
    for c in range(1, 7):
        d = dashboard.get(str(c), {})
        ei = d.get("EI", "-")
        ti = d.get("TI", "-")
        p1 = d.get("P1", "-")
        nige = d.get("nige", "-")
        place = d.get("place", "-")
        second = d.get("second", "-")
        print(f"         {c}    {ei:>5}  {ti:>5}  {p1:>5}  {nige:>5}  {place:>5}  {second:>5}")


# ---------------------------------------------------------------------------
# メインパイプライン
# ---------------------------------------------------------------------------

def run_pipeline(
    date: str,
    venue: str,
    race_numbers: list[int],
    model: str = MODEL,
    verbose: bool = False,
) -> list[dict]:
    """
    メインパイプライン: DB取得→Claude API→結果収集

    Returns:
        各レースの予想結果リスト
    """
    # Supabase 接続
    print("=" * 60)
    print(f"  宍戸予想パイプライン v1.0")
    print(f"  日付: {date}  会場: {venue}")
    print(f"  対象レース: {', '.join(f'R{r}' for r in race_numbers)}")
    print(f"  モデル: {model}")
    print("=" * 60)

    sb = _get_supabase()

    # 開催チェック
    print("\n[1/3] 開催データ確認中...", file=sys.stderr)
    available_races = _check_races_exist(sb, date, venue)
    print(f"  DB上のレース: {', '.join(f'R{r}' for r in available_races)}", file=sys.stderr)

    # 対象レースのフィルタリング
    target_races = [r for r in race_numbers if r in available_races]
    skipped_races = [r for r in race_numbers if r not in available_races]
    if skipped_races:
        print(
            f"  WARNING: 以下のレースはDBにデータがありません: "
            f"{', '.join(f'R{r}' for r in skipped_races)}",
            file=sys.stderr,
        )
    if not target_races:
        sys.exit("ERROR: 予想可能なレースがありません")

    # システムプロンプト読み込み
    print("\n[2/3] 計算式ドキュメント読み込み中...", file=sys.stderr)
    system_prompt = _load_system_prompt()
    print(f"  システムプロンプト: {len(system_prompt):,} 文字", file=sys.stderr)

    # 各レース予想実行
    print(f"\n[3/3] 予想実行中 ({len(target_races)}レース)...", file=sys.stderr)
    results: list[dict] = []

    for i, race_no in enumerate(target_races):
        result = predict_race(sb, date, venue, race_no, system_prompt, model=model)
        results.append(result)

        # レース間のsleep（レート制限対策）
        if i < len(target_races) - 1:
            time.sleep(INTER_RACE_DELAY)

    # スキップされたレースの結果も追加
    for race_no in skipped_races:
        results.append({
            "venue": venue,
            "date": date,
            "race_no": race_no,
            "status": "error",
            "error": "DBにデータなし",
        })

    # レース番号順にソート
    results.sort(key=lambda r: r.get("race_no", 0))

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="宍戸予想 エンドツーエンドパイプライン: DB→Claude API→買い目出力"
    )
    parser.add_argument("--date", required=True, help="日付 (YYYY-MM-DD)")
    parser.add_argument("--venue", required=True, help="会場名 (例: びわこ)")
    parser.add_argument(
        "--race", type=int, default=None,
        help="レース番号 (1-12)。省略時は全12レース",
    )
    parser.add_argument(
        "--model", default=MODEL,
        help=f"使用モデル (デフォルト: {MODEL})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="詳細出力（ダッシュボード数値を表示）",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="JSONファイル保存をスキップ",
    )
    args = parser.parse_args()

    # バリデーション
    date = _validate_date(args.date)
    venue = _validate_venue(args.venue)

    # 対象レース番号
    if args.race is not None:
        if not 1 <= args.race <= 12:
            sys.exit("ERROR: レース番号は1〜12で指定してください")
        race_numbers = [args.race]
    else:
        race_numbers = list(range(1, 13))

    # パイプライン実行
    results = run_pipeline(
        date=date,
        venue=venue,
        race_numbers=race_numbers,
        model=args.model,
        verbose=args.verbose,
    )

    # サマリー表示
    print("\n" + "=" * 60)
    print(f"  予想結果サマリー: {date} {venue}")
    print("=" * 60)

    ok_count = 0
    err_count = 0
    for result in results:
        _print_race_summary(result)
        if args.verbose:
            _print_dashboard_summary(result)
        if result.get("status") == "ok":
            ok_count += 1
        else:
            err_count += 1

    print("-" * 60)
    print(f"  成功: {ok_count} / エラー: {err_count} / 合計: {len(results)}")

    # JSON保存
    if not args.no_save:
        out_path = _save_output(results, date, venue)
        print(f"  保存先: {out_path}")

    print("=" * 60)

    # 全結果をstdoutにJSON出力（パイプ用）
    if sys.stdout.isatty():
        # ターミナル直接実行時はサマリーのみ（上で表示済み）
        pass
    else:
        # パイプ時はJSON出力
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
