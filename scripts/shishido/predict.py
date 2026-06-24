#!/usr/bin/env python3
"""
predict.py  –  宍戸予想システム: Claude API 連携スクリプト

v58.7 全計算式 MD をシステムプロンプトとして Claude に渡し、
fetch_race_data.py で取得した V-4 形式データから買い目を生成する。

Usage:
    # 単一レース予想
    python scripts/shishido/predict.py --date 2026-06-23 --venue びわこ --race 1

    # 全レース予想（会場指定）
    python scripts/shishido/predict.py --date 2026-06-23 --venue びわこ --all

    # 出力をファイルに保存
    python scripts/shishido/predict.py --date 2026-06-23 --venue びわこ --race 1 -o output.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    # プロジェクトルートの .env を読み込む
    _project_root = Path(__file__).resolve().parents[2]
    load_dotenv(_project_root / ".env")
except ImportError:
    _project_root = Path(__file__).resolve().parents[2]

# fetch_race_data をモジュールとして import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_race_data import fetch_race_v4, _get_supabase

import anthropic


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-5"
SPEC_PATH = _project_root / "data" / "v587_full_spec.md"
OUTPUT_DIR = _project_root / "tmp" / "shishido"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
INTER_RACE_DELAY = 2  # seconds between races in --all mode


# ---------------------------------------------------------------------------
# システムプロンプト読み込み
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """v587_full_spec.md を読み込んでシステムプロンプトとして返す"""
    if not SPEC_PATH.exists():
        raise RuntimeError(f"計算式ファイルが見つかりません: {SPEC_PATH}")
    text = SPEC_PATH.read_text(encoding="utf-8")
    return (
        "あなたは競艇予想AI v58.7 のエンジンです。\n"
        "以下の全計算式ドキュメントに厳密に従って、与えられた出走データから予想を実行してください。\n"
        "計算式の省略や独自解釈は禁止です。ドキュメントに記載された手順を忠実に再現してください。\n\n"
        "────────────────────────────────────────\n"
        f"{text}"
    )


# ---------------------------------------------------------------------------
# ユーザーメッセージ構成
# ---------------------------------------------------------------------------

def _build_user_message(race_data: dict) -> str:
    """V-4 JSON データからユーザーメッセージを構成"""
    race_json = json.dumps(race_data, ensure_ascii=False, indent=2)
    return (
        "以下の出走データについて、v58.7の全計算式に従って予想を実行してください。\n\n"
        "【出力形式】以下のJSON形式で出力してください：\n"
        "```json\n"
        "{\n"
        '  "venue": "会場名",\n'
        '  "date": "YYYY-MM-DD",\n'
        '  "race_no": N,\n'
        '  "analysis": {\n'
        '    "attack_subject": {"course": N, "type": "α/β/γ/ε/δ", "attack_type": "逃/差/捲/捲差"},\n'
        '    "head": [N, N],\n'
        '    "box": [N, N, N, N],\n'
        '    "honsen_12": ["N-N-N", ...],\n'
        '    "race_class": "見送り/通常/勝負/判定不能",\n'
        '    "exacta_top": ["N-N", ...],\n'
        '    "suichi": ["N-N-N", ...],\n'
        '    "dashboard": {\n'
        '      "1": {"EI": N, "TI": N, "P1": N, "nige": N, "place": N, "second": N},\n'
        '      "2": {"EI": N, "TI": N, "P1": N, "nige": N, "place": N, "second": N},\n'
        '      "3": {"EI": N, "TI": N, "P1": N, "nige": N, "place": N, "second": N},\n'
        '      "4": {"EI": N, "TI": N, "P1": N, "nige": N, "place": N, "second": N},\n'
        '      "5": {"EI": N, "TI": N, "P1": N, "nige": N, "place": N, "second": N},\n'
        '      "6": {"EI": N, "TI": N, "P1": N, "nige": N, "place": N, "second": N}\n'
        "    },\n"
        '    "calculation_steps": {\n'
        '      "step5_p2_linkage": {\n'
        '        "title": "⑤g P2連動要約(他艇成績→2着連動率)",\n'
        '        "data": {\n'
        '          "1": {"second_top": "2(82)", "second_next": "4(75)", "reliability": "中/完全/低"},\n'
        '          "2": {"second_top": "4(49)", "second_next": "1(43)", "reliability": "中"},\n'
        '          "...": "各コース1-6について同様"\n'
        "        }\n"
        "      },\n"
        '      "step6_ei": {\n'
        '        "title": "⑥格付け(EI 期待指数)",\n'
        '        "data": {\n'
        '          "1": {"A": N, "B": N, "C": N, "D": N, "F": N, "G": N, "H": N, "EI": N, "EI_rank": N},\n'
        '          "...": "各艇1-6について同様"\n'
        "        }\n"
        "      },\n"
        '      "step7_nige_ti": {\n'
        '        "title": "⑦逃げ成立度・TI",\n'
        '        "data": {\n'
        '          "nige_success_rate": N,\n'
        '          "damping_1c": N,\n'
        '          "attack_pressure": N,\n'
        '          "threat_total": N,\n'
        '          "ti": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N},\n'
        '          "ti_rank": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N}\n'
        "        }\n"
        "      },\n"
        '      "step8_fire_boat": {\n'
        '        "title": "⑧発動艇判定",\n'
        '        "data": {\n'
        '          "fire_boat": N or null,\n'
        '          "fire_boat_occ_rate": N,\n'
        '          "dkan": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N},\n'
        '          "dkan_detail": {\n'
        '            "1": {"motor": 0or1, "ei": 0or1, "st": 0or1, "attack": 0or1, "class": 0or1, "total": N},\n'
        '            "...": "各艇同様"\n'
        "          }\n"
        "        }\n"
        "      },\n"
        '      "step9_attack_decision": {\n'
        '        "title": "⑨攻め主体決定過程",\n'
        '        "data": {\n'
        '          "cal_win": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N},\n'
        '          "gap": N,\n'
        '          "cal_nige": N,\n'
        '          "distrust_1": true/false,\n'
        '          "alpha_check": "条件の判定結果テキスト",\n'
        '          "beta_check": "条件の判定結果テキスト",\n'
        '          "gamma_check": "条件の判定結果テキスト",\n'
        '          "epsilon_check": "条件の判定結果テキスト",\n'
        '          "result_type": "α/β/γ/ε/δ",\n'
        '          "result_reason": "決定理由の要約"\n'
        "        }\n"
        "      },\n"
        '      "step10_honsen": {\n'
        '        "title": "⑩本線生成過程",\n'
        '        "data": {\n'
        '          "head_boats": [N, N],\n'
        '          "axis_boats": [N, N],\n'
        '          "box_boats": [N, N, N, N],\n'
        '          "sink_boat": N or null,\n'
        '          "sink_override": "沈み解除の有無と理由",\n'
        '          "physical_death": [N] or [],\n'
        '          "kinsa": true/false,\n'
        '          "box_scores": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N},\n'
        '          "place_prob": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N},\n'
        '          "second_expect": {"1": N, "2": N, "3": N, "4": N, "5": N, "6": N}\n'
        "        }\n"
        "      }\n"
        "    }\n"
        "  },\n"
        '  "reasoning": "判断の要約"\n'
        "}\n"
        "```\n\n"
        "【注意事項】\n"
        "- dashboard の各指標は計算式に従って算出した数値を記載\n"
        "- nige は1号艇のみ（逃げ成立度）。他艇は 0 で可\n"
        "- honsen_12 は本線12点の3連単買い目リスト\n"
        "- exacta_top は2連単の上位候補\n"
        "- suichi はスイチ候補（万舟狙い）\n"
        "- calculation_steps は各計算ステップの途中経過を記載。全ステップ必須\n"
        "  - step5_p2_linkage: 各コース(1-6)が勝った場合の2着筆頭・次点・信頼度\n"
        "  - step6_ei: EI算出の各成分(A-H)と最終EI・EI順位\n"
        "  - step7_nige_ti: 逃げ成立度・減衰係数・攻め圧力・脅威合計・TI値・TI順位\n"
        "  - step8_fire_boat: D-KAN(5項目)の内訳と発動艇認定結果\n"
        "  - step9_attack_decision: 較正後1着率(cal_win)・GAP・α/β/γ/ε/δ各条件の判定結果\n"
        "  - step10_honsen: 頭・軸・箱・沈み・物理死亡・僅差判定・箱スコア・着内確率・2着期待\n"
        "- JSON以外の出力は不要です。JSONブロックのみ出力してください\n\n"
        f"【出走データ】\n```json\n{race_json}\n```"
    )


# ---------------------------------------------------------------------------
# Claude API 呼び出し
# ---------------------------------------------------------------------------

def _call_claude(system_prompt: str, user_message: str, model: str = MODEL) -> str:
    """Claude API を呼び出してレスポンステキストを返す"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY が環境変数に設定されていません")

    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  Claude API 呼び出し中... (attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
            response = client.messages.create(
                model=model,
                max_tokens=16384,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            # テキストブロックを結合
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            print(
                f"  完了 (tokens: input={response.usage.input_tokens}, output={response.usage.output_tokens})",
                file=sys.stderr,
            )
            return text

        except anthropic.RateLimitError:
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  Rate limit hit. {wait}秒後にリトライ...", file=sys.stderr)
                time.sleep(wait)
            else:
                raise
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  Server error ({e.status_code}). {wait}秒後にリトライ...", file=sys.stderr)
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# レスポンスパース
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | None:
    """Claude のレスポンスから JSON ブロックを抽出してパース"""
    # ```json ... ``` ブロックを探す
    pattern = r"```json\s*\n(.*?)\n\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # ``` ... ``` ブロック（言語指定なし）
    pattern2 = r"```\s*\n(.*?)\n\s*```"
    match2 = re.search(pattern2, text, re.DOTALL)
    if match2:
        try:
            return json.loads(match2.group(1))
        except json.JSONDecodeError:
            pass

    # 生の JSON を試す（{ で始まり } で終わる最大範囲）
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# 予想実行
# ---------------------------------------------------------------------------

def predict_race(
    sb: Any,
    date: str,
    venue: str,
    race_no: int,
    system_prompt: str,
    model: str = MODEL,
) -> dict:
    """1レース分の予想を実行して結果を返す"""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  予想開始: {date} {venue} R{race_no}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # V-4 データ取得
    print("  V-4 データ取得中...", file=sys.stderr)
    race_data = fetch_race_v4(sb, date, venue, race_no)
    if race_data is None:
        return {
            "venue": venue,
            "date": date,
            "race_no": race_no,
            "error": "レースデータが見つかりません",
            "status": "error",
        }

    # ユーザーメッセージ構成
    user_message = _build_user_message(race_data)

    # Claude API 呼び出し
    raw_response = _call_claude(system_prompt, user_message, model=model)

    # JSON パース
    parsed = _extract_json(raw_response)

    if parsed:
        result = {
            "venue": venue,
            "date": date,
            "race_no": race_no,
            "status": "ok",
            "prediction": parsed,
        }
    else:
        print("  WARNING: JSONパース失敗。raw textを保存します", file=sys.stderr)
        result = {
            "venue": venue,
            "date": date,
            "race_no": race_no,
            "status": "parse_error",
            "raw_response": raw_response,
        }

    return result


# ---------------------------------------------------------------------------
# 結果保存
# ---------------------------------------------------------------------------

def _save_result(result: dict | list, date: str, venue: str, race_no: int | None) -> Path:
    """結果を tmp/shishido/ に保存"""
    day_dir = OUTPUT_DIR / date
    day_dir.mkdir(parents=True, exist_ok=True)

    if race_no is not None:
        filename = f"{venue}_R{race_no:02d}.json"
    else:
        filename = f"{venue}_all.json"

    out_path = day_dir / filename
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="宍戸予想システム: Claude API 連携予想スクリプト"
    )
    parser.add_argument("--date", required=True, help="日付 (YYYY-MM-DD)")
    parser.add_argument("--venue", required=True, help="会場名 (例: びわこ)")
    parser.add_argument("--race", type=int, default=None, help="レース番号 (1-12)")
    parser.add_argument("--all", action="store_true", help="全12レースを予想")
    parser.add_argument("-o", "--output", default=None, help="出力ファイルパス (省略時: stdout + tmp保存)")
    parser.add_argument("--model", default=MODEL, help=f"使用モデル (デフォルト: {MODEL})")
    args = parser.parse_args()

    if args.race is None and not args.all:
        parser.error("--race N または --all を指定してください")

    # 使用モデル
    model = args.model

    # システムプロンプト読み込み
    print("計算式ドキュメント読み込み中...", file=sys.stderr)
    system_prompt = _load_system_prompt()
    print(f"  システムプロンプト: {len(system_prompt):,} 文字", file=sys.stderr)

    # Supabase 接続
    sb = _get_supabase()

    if args.all:
        # 全レース予想
        results = []
        for rno in range(1, 13):
            result = predict_race(sb, args.date, args.venue, rno, system_prompt, model=model)
            results.append(result)
            # rate limit 対策
            if rno < 12:
                time.sleep(INTER_RACE_DELAY)

        output = results
        auto_path = _save_result(results, args.date, args.venue, None)
        print(f"\n自動保存: {auto_path}", file=sys.stderr)
    else:
        # 単一レース予想
        result = predict_race(sb, args.date, args.venue, args.race, system_prompt, model=model)
        output = result
        auto_path = _save_result(result, args.date, args.venue, args.race)
        print(f"\n自動保存: {auto_path}", file=sys.stderr)

    # 出力
    json_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"出力ファイル: {args.output}", file=sys.stderr)
    else:
        print(json_str)

    # サマリー表示
    print(f"\n{'='*60}", file=sys.stderr)
    print("  予想完了サマリー", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    if isinstance(output, list):
        ok_count = sum(1 for r in output if r.get("status") == "ok")
        err_count = sum(1 for r in output if r.get("status") != "ok")
        print(f"  成功: {ok_count} / エラー: {err_count} / 合計: {len(output)}", file=sys.stderr)
    else:
        status = output.get("status", "unknown")
        print(f"  ステータス: {status}", file=sys.stderr)
        if status == "ok" and "prediction" in output:
            pred = output["prediction"]
            analysis = pred.get("analysis", {})
            if "honsen_12" in analysis:
                print(f"  本線: {len(analysis['honsen_12'])}点", file=sys.stderr)
            if "attack_subject" in analysis:
                atk = analysis["attack_subject"]
                print(f"  攻め主体: {atk.get('course')}コース {atk.get('type')} ({atk.get('attack_type')})", file=sys.stderr)
            if "race_class" in analysis:
                print(f"  レース分類: {analysis['race_class']}", file=sys.stderr)


if __name__ == "__main__":
    main()
