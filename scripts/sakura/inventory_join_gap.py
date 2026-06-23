#!/usr/bin/env python3
"""DOTレーティング学習データ拡大 — join可能レースのギャップ棚卸し(読み取り専用)

目的:
  学習に使える「join可能レース」= races(出走表/boats有) かつ
  race_winner_log(結果/trifecta_result有) が race_key で突合できるレース。
  本スクリプトは DB を一切書き込まない。以下を数値化する。

  1) 現状の join可能レース数(baseline)
       - races の計算race_key が race_winner_log のキー集合に存在する行数。
  2) entry欠損ギャップ(本タスクの主眼):
       - 結果(race_winner_log, trifecta_result有)は在るが
         races(boats>=1) が無い (date, venue, race_no) を洗い出し。
       - これが「entry取得で増やせる見込みレース数」。
       - date×venue 単位・会場単位・月単位に集計(段階取得のゲート設計用)。
  3) 結果欠損ギャップ(参考):
       - races(boats有) は在るが結果が無い (date,venue,race_no)。
  4) 日付レンジ(取得可能範囲の目安)。

join突合キー: race_winner_log の race_key(YYYYMMDD+code(2)+rno(2))を正とし、
  venue->code は race_winner_log から経験的に導出(backfill系と同一ロジック)。

使い方:
  python scripts/sakura/inventory_join_gap.py
  python scripts/sakura/inventory_join_gap.py --json out.json
"""
import os
import sys
import json
import argparse
from collections import defaultdict

from supabase import create_client

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
PAGE = 1000


def get_client():
    url = os.environ.get("SUPABASE_URL", DEFAULT_URL)
    key = os.environ.get("SUPABASE_KEY", DEFAULT_KEY)
    return create_client(url, key)


def fetch_all(sb, table, columns, *, gte=None, lte=None, eq=None, date_col="date"):
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
        batch = q.execute().data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def derive_vmap(rwl):
    """race_winner_log の race_key[8:10] から venue->code を経験導出。"""
    cnt = defaultdict(lambda: defaultdict(int))
    for r in rwl:
        rk = r.get("race_key")
        v = r.get("venue")
        if v and rk and len(rk) == 12:
            cnt[v][rk[8:10]] += 1
    return {v: max(c, key=c.get) for v, c in cnt.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default=None)
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    sb = get_client()
    gte, lte = args.from_date, args.to_date

    print("=" * 76)
    print("join可能レース ギャップ棚卸し(読み取り専用 / DB書き込みなし)")
    if gte or lte:
        print(f"  期間フィルタ: from={gte} to={lte}")
    print("=" * 76)

    # ---- race_winner_log: 結果ありキー集合 -------------------------------
    rwl = fetch_all(sb, "race_winner_log",
                    "race_key,date,venue,race_no,trifecta_result",
                    gte=gte, lte=lte)
    vmap = derive_vmap(rwl)
    # 結果が「有効」= trifecta_result 非NULL のキー集合(学習に使える結果)
    rwl_keys_valid = set()      # race_key (結果有効)
    rwl_keys_any = set()        # race_key (結果行が存在=trifecta問わず)
    rwl_dvr_valid = {}          # (date,venue,race_no) -> race_key (結果有効)
    for r in rwl:
        rk = r.get("race_key")
        if not rk or len(rk) != 12:
            continue
        rwl_keys_any.add(rk)
        if r.get("trifecta_result") is not None:
            rwl_keys_valid.add(rk)
            if r.get("date") and r.get("venue") and r.get("race_no") is not None:
                rwl_dvr_valid[(r["date"], r["venue"], r["race_no"])] = rk

    # ---- races + boats -----------------------------------------------------
    races = fetch_all(sb, "races", "id,date,venue,race_no", gte=gte, lte=lte)
    race_ids = [r["id"] for r in races]
    boats_count = defaultdict(int)
    CH = 200
    for i in range(0, len(race_ids), CH):
        chunk = race_ids[i:i + CH]
        start = 0
        while True:
            b = (sb.table("boats").select("race_id")
                 .in_("race_id", chunk).range(start, start + PAGE - 1).execute().data or [])
            for x in b:
                boats_count[x["race_id"]] += 1
            if len(b) < PAGE:
                break
            start += PAGE

    # races の計算 race_key と boats有無
    races_key_set = set()          # 計算race_key (boats有=出走表有)
    races_dvr_with_boats = set()   # (date,venue,race_no) boats>=1
    races_dvr_all = set()
    for r in races:
        vc = vmap.get(r["venue"])
        if vc is None or r["race_no"] is None:
            continue
        rk = f"{r['date'].replace('-', '')}{vc}{str(r['race_no']).zfill(2)}"
        has_boats = boats_count.get(r["id"], 0) >= 1
        dvr = (r["date"], r["venue"], r["race_no"])
        races_dvr_all.add(dvr)
        if has_boats:
            races_key_set.add(rk)
            races_dvr_with_boats.add(dvr)

    # ---- (1) baseline: join可能レース ------------------------------------
    # = boats有の races の race_key が 結果有効キーに存在
    join_ok = len(races_key_set & rwl_keys_valid)

    # ---- (2) entry欠損ギャップ(主眼) ------------------------------------
    # 結果有効(rwl_dvr_valid)があるが、races側 boats無 の (date,venue,race_no)
    gap_entry_dvr = []
    for dvr in rwl_dvr_valid:
        if dvr not in races_dvr_with_boats:
            gap_entry_dvr.append(dvr)
    # date×venue / venue / month に集計
    gap_entry_dv = defaultdict(int)       # (date,venue) -> 欠損レース数
    gap_by_venue = defaultdict(int)
    gap_by_month = defaultdict(int)
    gap_by_venue_month = defaultdict(int)
    for d, v, rno in gap_entry_dvr:
        gap_entry_dv[(d, v)] += 1
        gap_by_venue[v] += 1
        gap_by_month[d[:7]] += 1
        gap_by_venue_month[(v, d[:7])] += 1

    # ---- (3) 結果欠損ギャップ(参考) -------------------------------------
    gap_result_dvr = [dvr for dvr in races_dvr_with_boats
                      if dvr not in rwl_dvr_valid]

    # ---- 日付レンジ -------------------------------------------------------
    def minmax(rows):
        ds = [r["date"] for r in rows if r.get("date")]
        return (min(ds), max(ds)) if ds else (None, None)
    rwl_lo, rwl_hi = minmax(rwl)
    rc_lo, rc_hi = minmax(races)

    # ===================== 出力 ===========================================
    print("\n■ baseline")
    print(f"  race_winner_log 行数            : {len(rwl)}")
    print(f"  race_winner_log 有効結果キー数  : {len(rwl_keys_valid)}")
    print(f"  races 行数                       : {len(races)}")
    print(f"  races(boats>=1) のキー数         : {len(races_key_set)}")
    print(f"  >> join可能レース(baseline)      : {join_ok}")

    print("\n■ entry欠損ギャップ(=entry取得で増やせる見込み / 主眼)")
    print(f"  結果有効だが出走表(boats)無のレース数: {len(gap_entry_dvr)}")
    print(f"  対象 (date,venue) 組数               : {len(gap_entry_dv)}")
    print("  会場別 欠損レース数 上位15:")
    for v, n in sorted(gap_by_venue.items(), key=lambda x: -x[1])[:15]:
        print(f"      {v:6s}: {n:5d} レース  (code={vmap.get(v)})")
    print("  月別 欠損レース数:")
    for m, n in sorted(gap_by_month.items()):
        print(f"      {m}: {n:5d} レース")
    print("  会場×月 欠損 上位20(段階取得ゲート候補):")
    for (v, m), n in sorted(gap_by_venue_month.items(), key=lambda x: -x[1])[:20]:
        print(f"      {m} {v:6s}: {n:4d} レース")

    print("\n■ 結果欠損ギャップ(参考: 出走表は有るが結果無)")
    print(f"  出走表有だが結果無のレース数: {len(gap_result_dvr)}")

    print("\n■ 日付レンジ")
    print(f"  race_winner_log: {rwl_lo} 〜 {rwl_hi}")
    print(f"  races          : {rc_lo} 〜 {rc_hi}")

    print("\n■ 見込みサマリ")
    print(f"  現状 join可能         : {join_ok}")
    print(f"  entry取得で最大+      : {len(gap_entry_dvr)} (理論上限)")
    print(f"  到達見込み(理論最大)  : {join_ok + len(gap_entry_dvr)}")

    if args.json_out:
        out = {
            "baseline_join": join_ok,
            "rwl_rows": len(rwl),
            "rwl_valid_keys": len(rwl_keys_valid),
            "races_rows": len(races),
            "races_boats_keys": len(races_key_set),
            "entry_gap_races": len(gap_entry_dvr),
            "entry_gap_dv": len(gap_entry_dv),
            "gap_by_venue": dict(sorted(gap_by_venue.items(), key=lambda x: -x[1])),
            "gap_by_month": dict(sorted(gap_by_month.items())),
            "gap_by_venue_month": {f"{v}|{m}": n for (v, m), n in
                                   sorted(gap_by_venue_month.items(), key=lambda x: -x[1])},
            "gap_entry_dv_list": [[d, v, n] for (d, v), n in
                                  sorted(gap_entry_dv.items())],
            "result_gap_races": len(gap_result_dvr),
            "date_range": {"race_winner_log": [rwl_lo, rwl_hi], "races": [rc_lo, rc_hi]},
            "vmap": vmap,
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON出力: {args.json_out}")

    print("\n" + "=" * 76)
    print("棚卸し完了(DB書き込みなし)")
    print("=" * 76)


if __name__ == "__main__":
    main()
