#!/usr/bin/env python3
"""DOTレーティング学習データ拡大 — 月次・会場ゲートの新規取得ドライバ

既存の backfill_phase4.py / backfill_entry_gap.py は対象 (date,venue) を
DB(races / race_winner_log)から列挙するため、DBに1行も存在しない月
(例: 2026-04)を取りこぼす(=種が無いと0バッチ)。

本ドライバは DB を種にせず、指定期間の「日付カレンダー × 1会場」を直接列挙し、
VPS /scrape に results→entry の順で逐次POSTして race_winner_log/races/boats を
新規に埋める。VPS側は 6艇揃った時のみ upsert / 既存非破壊(部分保存防止)。

安全側設計(ユーザー厳守ルール準拠):
  - 会場単位ゲート必須(--venue)。全会場一括は禁止のため --venue 無しは拒否。
  - 完全逐次・sleep>=3s・指数バックオフ(backfill_phase4.post_scrape を再利用)。
  - --dry-run で対象日付提示のみ(送信なし)。
  - results→entry の順(結果を種にしてから出走表)。--items で変更可。
  - 非開催日/未開催レースは VPS 側で静かにスキップ(races行も作らない)。

使い方:
  # 対象日付の確認(送信なし)
  python scripts/sakura/backfill_month_venue.py --venue 丸亀 --from 2026-04-01 --to 2026-04-30 --dry-run
  # 実取得(results→entry)
  python scripts/sakura/backfill_month_venue.py --venue 丸亀 --from 2026-04-01 --to 2026-04-30 --log tmp/apr_marugame.jsonl
"""
import os
import sys
import json
import time
import argparse
import datetime as dt
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backfill_phase4 import post_scrape, DEFAULT_VPS, DEFAULT_SECRET  # noqa: E402


def daterange(from_iso, to_iso):
    d0 = dt.date.fromisoformat(from_iso)
    d1 = dt.date.fromisoformat(to_iso)
    cur = d0
    while cur <= d1:
        yield cur.isoformat()
        cur += dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", required=True,
                    help="会場名(必須・会場ゲート)。全会場一括は禁止。")
    ap.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD 下限")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD 上限")
    ap.add_argument("--items", default="results,entry",
                    help="取得順(カンマ区切り)。既定 results,entry")
    ap.add_argument("--sleep", type=float, default=4.0, help="POST間sleep秒(最低3.0)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--backoff", type=float, default=5.0)
    ap.add_argument("--max-dates", type=int, default=0, help="処理する最大日付数(0=無制限)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    sleep_s = max(3.0, args.sleep)
    base = os.environ.get("VPS_BASE", DEFAULT_VPS)
    secret = os.environ.get("API_SECRET", DEFAULT_SECRET)
    items = [x.strip() for x in args.items.split(",") if x.strip()]

    dates = list(daterange(args.from_date, args.to_date))
    if args.max_dates and args.max_dates > 0:
        dates = dates[:args.max_dates]

    print("=" * 76)
    print("月次・会場ゲート 新規取得ドライバ")
    print(f"  venue={args.venue} from={args.from_date} to={args.to_date} items={items}")
    print(f"  VPS={base} sleep={sleep_s}s retries={args.retries} dry_run={args.dry_run}")
    print(f"  対象日付数={len(dates)} (会場ゲート: {args.venue} のみ)")
    print("=" * 76)

    if args.dry_run:
        print("\n[dry-run] 送信なし。対象日付:")
        for d in dates:
            print(f"    {d} {args.venue} items={items}")
        print(f"\n[dry-run] 完了({len(dates)}日 × {len(items)}item = "
              f"{len(dates)*len(items)} POST予定)")
        return

    logf = open(args.log, "w", encoding="utf-8") if args.log else None
    n_post = 0
    ok_cnt = err_cnt = 0
    saved_by_item = defaultdict(int)
    status_counter = defaultdict(int)
    partial_list = []
    posts = [(d, it) for d in dates for it in items]
    total = len(posts)
    for i, (d, it) in enumerate(posts, 1):
        n_post += 1
        print(f"[{i}/{total}] {it} {d} {args.venue} ...", flush=True)
        res = post_scrape(base, secret, d, args.venue, it,
                          timeout=args.timeout, retries=args.retries, backoff=args.backoff)
        rec = {"idx": i, "date": d, "venue": args.venue, "item": it}
        if res["ok"]:
            body = res["body"]
            saved = 0
            statuses = []
            for r in body.get("results", []):
                st = r.get("status")
                statuses.append(st)
                status_counter[st] += 1
                saved += (r.get("saved", 0) or r.get("boats", 0) or 0)
                if st == "partial":
                    partial_list.append((d, it, r.get("incomplete_races")))
            saved_by_item[it] += saved
            ok_cnt += 1
            rec.update({"ok": True, "saved": saved, "statuses": statuses,
                        "summary": body.get("summary")})
            print(f"      ok saved={saved} statuses={statuses}")
        else:
            err_cnt += 1
            rec.update({"ok": False, "error": res["error"]})
            print(f"      ERROR: {res['error']}")
        if logf:
            logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logf.flush()
        if i < total:
            time.sleep(sleep_s)
    if logf:
        logf.close()

    print("\n" + "-" * 76)
    print("取得サマリ")
    print(f"  POST総数      : {total}  成功/失敗: {ok_cnt}/{err_cnt}")
    for it in items:
        print(f"  saved[{it}]  : {saved_by_item.get(it, 0)}")
    print(f"  status内訳     : {dict(status_counter)}")
    if partial_list:
        print(f"  partial(6艇未満): {len(partial_list)} 件")
        for d, it, inc in partial_list[:20]:
            print(f"      {d} {it} incomplete={inc}")
    if args.log:
        print(f"  実行ログ       : {args.log}")
    print("=" * 76)


if __name__ == "__main__":
    main()
