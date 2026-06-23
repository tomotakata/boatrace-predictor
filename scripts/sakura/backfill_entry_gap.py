#!/usr/bin/env python3
"""DOTレーティング学習データ拡大 — entry欠損ギャップの会場ゲート取得ドライバ

inventory_join_gap.py が洗い出した「結果有・出走表(boats)無」の
(date, venue) ギャップに対し、VPS /scrape (items=[entry]) を会場単位ゲートで
逐次POSTして races/boats を埋める。

なぜ backfill_phase4.py を直接使わないか:
  backfill_phase4.py --all-dates は races テーブルから (date,venue) を
  列挙するため、races行が存在しないギャップ日付を取りこぼす。
  本ドライバは race_winner_log(結果)起点で対象を決めるため取りこぼさない。

安全側設計(ユーザー厳守ルール準拠):
  - 会場単位ゲート必須(--venue)。全会場一括は禁止のため --venue 無しは拒否。
  - 完全逐次・sleep>=3s・指数バックオフ(post_scrapeを再利用)。
  - VPS側 scrape_entry は 6艇揃った時のみ upsert / 既存非破壊。
  - --dry-run で対象提示のみ(送信なし)。

使い方:
  python scripts/sakura/backfill_entry_gap.py --venue 尼崎 --dry-run
  python scripts/sakura/backfill_entry_gap.py --venue 尼崎
"""
import os
import sys
import json
import time
import argparse
from collections import defaultdict

# backfill_phase4 の post_scrape / クライアントを再利用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backfill_phase4 import get_client, post_scrape, DEFAULT_VPS, DEFAULT_SECRET  # noqa: E402
from inventory_join_gap import fetch_all, derive_vmap  # noqa: E402


def collect_entry_gap(sb, gte=None, lte=None):
    """結果有効(trifecta_result非NULL)だが boats無 の (date,venue) -> 欠損レース数。
    race_winner_log 起点。"""
    rwl = fetch_all(sb, "race_winner_log",
                    "race_key,date,venue,race_no,trifecta_result", gte=gte, lte=lte)
    # 結果有効 (date,venue,race_no)
    valid_dvr = set()
    for r in rwl:
        if (r.get("trifecta_result") is not None and r.get("date")
                and r.get("venue") and r.get("race_no") is not None):
            valid_dvr.add((r["date"], r["venue"], r["race_no"]))

    # races(boats>=1) の (date,venue,race_no)
    races = fetch_all(sb, "races", "id,date,venue,race_no", gte=gte, lte=lte)
    race_ids = [r["id"] for r in races]
    boats_count = defaultdict(int)
    PAGE = 1000
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
    have_boats = set()
    for r in races:
        if boats_count.get(r["id"], 0) >= 1 and r.get("race_no") is not None:
            have_boats.add((r["date"], r["venue"], r["race_no"]))

    gap_dv = defaultdict(int)
    for d, v, rno in valid_dvr:
        if (d, v, rno) not in have_boats:
            gap_dv[(d, v)] += 1
    return gap_dv


def measure_join(sb, gte=None, lte=None):
    """現状の join可能レース数を返す(inventory と同一定義)。"""
    rwl = fetch_all(sb, "race_winner_log",
                    "race_key,date,venue,race_no,trifecta_result", gte=gte, lte=lte)
    vmap = derive_vmap(rwl)
    valid_keys = set()
    for r in rwl:
        rk = r.get("race_key")
        if rk and len(rk) == 12 and r.get("trifecta_result") is not None:
            valid_keys.add(rk)
    races = fetch_all(sb, "races", "id,date,venue,race_no", gte=gte, lte=lte)
    race_ids = [r["id"] for r in races]
    boats_count = defaultdict(int)
    PAGE = 1000
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
    keys = set()
    for r in races:
        vc = vmap.get(r["venue"])
        if vc is None or r["race_no"] is None:
            continue
        if boats_count.get(r["id"], 0) >= 1:
            keys.add(f"{r['date'].replace('-', '')}{vc}{str(r['race_no']).zfill(2)}")
    return len(keys & valid_keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", required=True,
                    help="会場名(必須・会場ゲート)。全会場一括は禁止。")
    ap.add_argument("--from", dest="from_date", default=None)
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument("--sleep", type=float, default=4.0, help="バッチ間sleep秒(最低3.0)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--backoff", type=float, default=5.0)
    ap.add_argument("--max-batches", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-measure", action="store_true",
                    help="前後のjoin計測をスキップ(高速化)")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    sleep_s = max(3.0, args.sleep)
    base = os.environ.get("VPS_BASE", DEFAULT_VPS)
    secret = os.environ.get("API_SECRET", DEFAULT_SECRET)
    sb = get_client()

    print("=" * 76)
    print("entry欠損ギャップ 会場ゲート取得ドライバ")
    print(f"  venue={args.venue} from={args.from_date} to={args.to_date}")
    print(f"  VPS={base} sleep={sleep_s}s retries={args.retries} dry_run={args.dry_run}")
    print("=" * 76)

    gap_dv = collect_entry_gap(sb, args.from_date, args.to_date)
    # 会場フィルタ
    targets = sorted([(d, v, n) for (d, v), n in gap_dv.items() if v == args.venue])
    if not targets:
        print(f"\n対象なし: venue={args.venue} の entry欠損ギャップは 0 です。")
        return

    total_gap_races = sum(n for _d, _v, n in targets)
    print(f"\n会場 {args.venue} の entry欠損ギャップ:")
    print(f"  対象日付数: {len(targets)}  欠損レース合計: {total_gap_races}")
    for d, v, n in targets:
        print(f"    {d} {v}: {n} レース欠損")

    if args.max_batches and args.max_batches > 0:
        targets = targets[:args.max_batches]
        print(f"  → max-batches により {len(targets)} 日付に制限")

    if args.dry_run:
        print("\n[dry-run] 送信なし。")
        return

    # 前計測
    join_before = None
    if not args.no_measure:
        print("\njoin可能レース(全体)を計測中(取得前)...")
        join_before = measure_join(sb)
        print(f"  join_before = {join_before}")

    logf = open(args.log, "w", encoding="utf-8") if args.log else None
    boats_sum = 0
    ok_cnt = err_cnt = 0
    partial_dates = []
    for i, (d, v, n) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] entry {d} {v} (欠損{n}) ...", flush=True)
        res = post_scrape(base, secret, d, v, "entry",
                          timeout=args.timeout, retries=args.retries, backoff=args.backoff)
        rec = {"idx": i, "date": d, "venue": v, "item": "entry"}
        if res["ok"]:
            body = res["body"]
            saved = 0
            statuses = []
            for r in body.get("results", []):
                statuses.append(r.get("status"))
                saved += r.get("boats", 0) or 0
                if r.get("status") == "partial":
                    partial_dates.append((d, v, r.get("incomplete_races")))
            boats_sum += saved
            ok_cnt += 1
            rec.update({"ok": True, "boats": saved, "statuses": statuses})
            print(f"      ok boats={saved} statuses={statuses}")
        else:
            err_cnt += 1
            rec.update({"ok": False, "error": res["error"]})
            print(f"      ERROR: {res['error']}")
        if logf:
            logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logf.flush()
        if i < len(targets):
            time.sleep(sleep_s)
    if logf:
        logf.close()

    print("\n" + "-" * 76)
    print(f"取得boats合計: {boats_sum}  成功/失敗: {ok_cnt}/{err_cnt}")
    if partial_dates:
        print(f"partial(6艇未満)日付: {partial_dates}")

    # 後計測
    if not args.no_measure:
        print("\njoin可能レース(全体)を計測中(取得後)...")
        join_after = measure_join(sb)
        delta = (join_after - join_before) if join_before is not None else None
        print(f"  join_before = {join_before}")
        print(f"  join_after  = {join_after}")
        print(f"  join増減    = {('+' + str(delta)) if delta is not None and delta >= 0 else delta}")

    print("=" * 76)


if __name__ == "__main__":
    main()
