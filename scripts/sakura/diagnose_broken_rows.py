#!/usr/bin/env python3
"""データ基盤修正フェーズ4 — 壊れた行の棚卸し(読み取り専用 / 更新なし)

supabase-py(PostgREST)経由で以下を集計する。DB書き込みは一切行わない。

- race_winner_log: trifecta_result 欠損 / result_all 欠損・二重エンコード / place系欠損
- races: boats=0 / boats<6 のレース数, race_key/venue_code 未設定
- バックフィル対象の (date, venue) ユニーク集合と件数
- 公式から取得可能とみなせる最古日付(= DB上の最古日付)

使い方:
    python scripts/sakura/diagnose_broken_rows.py
    python scripts/sakura/diagnose_broken_rows.py --json out.json   # 機械可読出力も保存
    python scripts/sakura/diagnose_broken_rows.py --venue 丸亀 --from 2026-06-01 --to 2026-06-12

環境変数 SUPABASE_URL / SUPABASE_KEY があればそれを優先。無ければ既定値(server.py と同一)。
"""
import os
import sys
import json
import argparse
from collections import defaultdict

try:
    from supabase import create_client
except Exception as e:  # pragma: no cover
    print("supabase-py が必要です: pip install supabase", file=sys.stderr)
    raise

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)

PAGE = 1000  # PostgREST 1リクエストあたりの取得上限


def get_client():
    url = os.environ.get("SUPABASE_URL", DEFAULT_URL)
    key = os.environ.get("SUPABASE_KEY", DEFAULT_KEY)
    return create_client(url, key)


def fetch_all(sb, table, columns, *, gte=None, lte=None, eq=None, date_col="date"):
    """PostgREST をページングで全件取得(読み取りのみ)。"""
    rows = []
    start = 0
    while True:
        q = sb.table(table).select(columns)
        if gte is not None:
            q = q.gte(date_col, gte)
        if lte is not None:
            q = q.lte(date_col, lte)
        if eq:
            for k, v in eq.items():
                q = q.eq(k, v)
        q = q.order(date_col).range(start, start + PAGE - 1)
        resp = q.execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def is_result_all_broken(value):
    """result_all がJSONBに正しい配列として入っているかを判定。
    壊れ: None / 文字列(二重エンコード) / 配列だが要素1以下(1着のみ)。
    正常: list で要素>=2(複数着順) 。"""
    if value is None:
        return ("missing", True)
    if isinstance(value, str):
        return ("double_encoded_str", True)
    if isinstance(value, list):
        if len(value) <= 1:
            return ("only_one_pos", True)
        return ("ok", False)
    return ("unexpected_type", True)


def pct(n, d):
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default=None, help="YYYY-MM-DD 集計開始")
    ap.add_argument("--to", dest="to_date", default=None, help="YYYY-MM-DD 集計終了")
    ap.add_argument("--venue", dest="venue", default=None, help="会場名で絞り込み(任意)")
    ap.add_argument("--json", dest="json_out", default=None, help="集計結果をJSONで保存するパス")
    args = ap.parse_args()

    sb = get_client()
    eq = {"venue": args.venue} if args.venue else None

    print("=" * 72)
    print("データ基盤フェーズ4 診断 — 壊れた行の棚卸し(読み取り専用)")
    if args.from_date or args.to_date or args.venue:
        print(f"  フィルタ: from={args.from_date} to={args.to_date} venue={args.venue}")
    print("=" * 72)

    # ------------------------------------------------------------------
    # 1) race_winner_log
    # ------------------------------------------------------------------
    rwl_cols = "race_key,date,venue,race_no,winner_lane,place2_lane,place3_lane,trifecta_result,result_all"
    rwl = fetch_all(sb, "race_winner_log", rwl_cols, gte=args.from_date, lte=args.to_date, eq=eq)
    total_rwl = len(rwl)

    tri_null = 0
    ra_broken = 0
    ra_reasons = defaultdict(int)
    place2_null = 0
    place3_null = 0
    rwl_target_dv = set()  # (date, venue) で再取得すべき集合
    for r in rwl:
        tri = r.get("trifecta_result")
        ra_reason, ra_is_broken = is_result_all_broken(r.get("result_all"))
        ra_reasons[ra_reason] += 1
        broken = False
        if tri is None:
            tri_null += 1
            broken = True
        if ra_is_broken:
            ra_broken += 1
            broken = True
        if r.get("place2_lane") is None:
            place2_null += 1
        if r.get("place3_lane") is None:
            place3_null += 1
        if broken:
            rwl_target_dv.add((r.get("date"), r.get("venue")))

    print("\n■ race_winner_log")
    print(f"  総行数                : {total_rwl}")
    print(f"  trifecta_result IS NULL: {tri_null}  ({pct(tri_null, total_rwl)})")
    print(f"  trifecta_result 非NULL : {total_rwl - tri_null}  ({pct(total_rwl - tri_null, total_rwl)})")
    print(f"  result_all 壊れ(計)    : {ra_broken}  ({pct(ra_broken, total_rwl)})")
    for k in ("ok", "missing", "double_encoded_str", "only_one_pos", "unexpected_type"):
        if ra_reasons.get(k):
            print(f"      - {k:20s}: {ra_reasons[k]}")
    print(f"  place2_lane IS NULL    : {place2_null}")
    print(f"  place3_lane IS NULL    : {place3_null}")
    print(f"  → 再取得対象 (date,venue): {len(rwl_target_dv)} 組")

    # ------------------------------------------------------------------
    # 2) races + boats(boats=0 / boats<6)
    # ------------------------------------------------------------------
    races = fetch_all(
        sb, "races", "id,date,venue,race_no,race_key,venue_code",
        gte=args.from_date, lte=args.to_date, eq=eq,
    )
    total_races = len(races)
    race_ids = [r["id"] for r in races]

    # boats を race_id ごとの件数で集計(id だけ取れば軽量)
    boats_count = defaultdict(int)
    CH = 200
    for i in range(0, len(race_ids), CH):
        chunk = race_ids[i:i + CH]
        start = 0
        while True:
            resp = (
                sb.table("boats").select("race_id")
                .in_("race_id", chunk)
                .range(start, start + PAGE - 1)
                .execute()
            )
            batch = resp.data or []
            for b in batch:
                boats_count[b["race_id"]] += 1
            if len(batch) < PAGE:
                break
            start += PAGE

    boats0 = 0
    boats_lt6 = 0
    rk_null = 0
    vc_null = 0
    boats0_target_dv = set()
    for r in races:
        c = boats_count.get(r["id"], 0)
        if c == 0:
            boats0 += 1
            boats0_target_dv.add((r.get("date"), r.get("venue")))
        if c < 6:
            boats_lt6 += 1
        if not r.get("race_key"):
            rk_null += 1
        if not r.get("venue_code"):
            vc_null += 1

    print("\n■ races / boats")
    print(f"  総レース数             : {total_races}")
    print(f"  boats=0 のレース       : {boats0}  ({pct(boats0, total_races)})")
    print(f"  boats<6 のレース       : {boats_lt6}  ({pct(boats_lt6, total_races)})")
    print(f"  race_key 未設定        : {rk_null}")
    print(f"  venue_code 未設定      : {vc_null}")
    print(f"  → boats=0 再取得対象 (date,venue): {len(boats0_target_dv)} 組")

    # ------------------------------------------------------------------
    # 3) 取得可能範囲(DB上の最古/最新日付)
    # ------------------------------------------------------------------
    def minmax_date(table):
        try:
            lo = sb.table(table).select("date").order("date").limit(1).execute().data
            hi = sb.table(table).select("date").order("date", desc=True).limit(1).execute().data
            return (lo[0]["date"] if lo else None, hi[0]["date"] if hi else None)
        except Exception as e:
            return (f"ERR:{e}", None)

    rwl_lo, rwl_hi = minmax_date("race_winner_log")
    rc_lo, rc_hi = minmax_date("races")
    print("\n■ 日付レンジ(取得可能範囲の目安)")
    print(f"  race_winner_log: {rwl_lo} 〜 {rwl_hi}")
    print(f"  races          : {rc_lo} 〜 {rc_hi}")

    # ------------------------------------------------------------------
    # 4) バックフィル対象サマリ
    # ------------------------------------------------------------------
    results_dv = sorted(rwl_target_dv)
    entry_dv = sorted(boats0_target_dv)
    print("\n■ バックフィル対象サマリ")
    print(f"  [results] 再取得 (date,venue) 組数: {len(results_dv)}")
    print(f"  [entry]   再取得 (date,venue) 組数: {len(entry_dv)}")
    # 日付別の組数上位を表示
    by_date = defaultdict(int)
    for d, _v in results_dv:
        by_date[d] += 1
    if by_date:
        print("  [results] 日付別 上位10:")
        for d, n in sorted(by_date.items(), key=lambda x: -x[1])[:10]:
            print(f"      {d}: {n} 会場")

    summary = {
        "race_winner_log": {
            "total": total_rwl,
            "trifecta_result_null": tri_null,
            "trifecta_result_nonnull_pct": (100.0 * (total_rwl - tri_null) / total_rwl) if total_rwl else None,
            "result_all_broken": ra_broken,
            "result_all_reasons": dict(ra_reasons),
            "place2_lane_null": place2_null,
            "place3_lane_null": place3_null,
            "target_date_venue_count": len(results_dv),
        },
        "races": {
            "total": total_races,
            "boats_zero": boats0,
            "boats_lt6": boats_lt6,
            "race_key_null": rk_null,
            "venue_code_null": vc_null,
            "target_date_venue_count": len(entry_dv),
        },
        "date_range": {
            "race_winner_log": [rwl_lo, rwl_hi],
            "races": [rc_lo, rc_hi],
        },
        "targets": {
            "results": [[d, v] for d, v in results_dv],
            "entry": [[d, v] for d, v in entry_dv],
        },
    }

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\nJSON出力: {args.json_out}")

    print("\n" + "=" * 72)
    print("診断完了(DB書き込みなし)")
    print("=" * 72)


if __name__ == "__main__":
    main()
