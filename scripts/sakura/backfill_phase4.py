#!/usr/bin/env python3
"""データ基盤修正フェーズ4 — バックフィル・オーケストレータ

壊れた行を抱える (date, venue) を supabase-py で抽出し、VPS の既存
`/scrape` エンドポイント(items=[results] / [entry])を会場×日付単位で
逐次呼び出して埋め直す。本番 server.py 本体は改変しない(既存経路のみ使用)。

安全側設計:
  - 並列なし(完全逐次)。バッチ間 sleep(デフォルト 4.0 秒, 最低 3.0)。
  - エラー時は指数バックオフでリトライ(デフォルト最大2回)。
  - 取得可能範囲(DB最古日付)で自動クランプ。範囲外はスキップしログに残す。
  - --dry-run で送信せず対象一覧のみ出力。--max-batches で件数制限(段階実行)。
  - 冪等: VPS側が upsert(on_conflict=race_key)。既存正常行は非破壊。

使い方:
  # 対象一覧の確認(送信なし)
  python scripts/sakura/backfill_phase4.py --dry-run
  # 小範囲試行(results を 1会場×数日 など最大5バッチ)
  python scripts/sakura/backfill_phase4.py --items results --venue 丸亀 --max-batches 5
  # 全期間(results)
  python scripts/sakura/backfill_phase4.py --items results
  # 出走表(entry)
  python scripts/sakura/backfill_phase4.py --items entry

環境変数 SUPABASE_URL / SUPABASE_KEY / VPS_BASE / API_SECRET があれば優先。
"""
import os
import sys
import json
import time
import argparse
import datetime as dt
from collections import defaultdict

try:
    import httpx
except Exception:
    print("httpx が必要です: pip install httpx", file=sys.stderr)
    raise
try:
    from supabase import create_client
except Exception:
    print("supabase-py が必要です: pip install supabase", file=sys.stderr)
    raise

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
DEFAULT_VPS = "http://153.121.51.74:8080"
DEFAULT_SECRET = "boatrace-sakura-secret-2024"

PAGE = 1000


def get_client():
    url = os.environ.get("SUPABASE_URL", DEFAULT_URL)
    key = os.environ.get("SUPABASE_KEY", DEFAULT_KEY)
    return create_client(url, key)


def fetch_all(sb, table, columns, *, gte=None, lte=None, eq=None, is_null=None, date_col="date"):
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
        if is_null:
            for k in is_null:
                q = q.is_(k, "null")
        q = q.order(date_col).range(start, start + PAGE - 1)
        resp = q.execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def collect_results_targets(sb, eq, gte, lte):
    """trifecta_result IS NULL の (date, venue) ユニーク集合。"""
    rows = fetch_all(
        sb, "race_winner_log", "date,venue,trifecta_result",
        gte=gte, lte=lte, eq=eq, is_null=["trifecta_result"],
    )
    dv = set()
    for r in rows:
        if r.get("date") and r.get("venue"):
            dv.add((r["date"], r["venue"]))
    return sorted(dv)


def collect_entry_targets(sb, eq, gte, lte):
    """boats=0 の (date, venue) ユニーク集合。"""
    races = fetch_all(sb, "races", "id,date,venue", gte=gte, lte=lte, eq=eq)
    race_ids = [r["id"] for r in races]
    boats_count = defaultdict(int)
    CH = 200
    for i in range(0, len(race_ids), CH):
        chunk = race_ids[i:i + CH]
        start = 0
        while True:
            resp = (
                sb.table("boats").select("race_id")
                .in_("race_id", chunk).range(start, start + PAGE - 1).execute()
            )
            batch = resp.data or []
            for b in batch:
                boats_count[b["race_id"]] += 1
            if len(batch) < PAGE:
                break
            start += PAGE
    dv = set()
    for r in races:
        if boats_count.get(r["id"], 0) == 0 and r.get("date") and r.get("venue"):
            dv.add((r["date"], r["venue"]))
    return sorted(dv)


def collect_all_results_dv(sb, eq, gte, lte):
    """race_winner_log の全 (date, venue) ユニーク集合(壊れ有無を問わない)。"""
    rows = fetch_all(sb, "race_winner_log", "date,venue", gte=gte, lte=lte, eq=eq)
    return sorted({(r["date"], r["venue"]) for r in rows if r.get("date") and r.get("venue")})


def collect_all_entry_dv(sb, eq, gte, lte):
    """races の全 (date, venue) ユニーク集合(壊れ有無を問わない)。"""
    rows = fetch_all(sb, "races", "date,venue", gte=gte, lte=lte, eq=eq)
    return sorted({(r["date"], r["venue"]) for r in rows if r.get("date") and r.get("venue")})


def month_of(date_iso):
    return date_iso[:7]  # YYYY-MM


def enumerate_slices(sb, eq, gte, lte, items):
    """(venue, YYYY-MM) スライスを列挙し、各スライスの
    バッチ数(=対象日付数)と現在の壊れ件数を集計して返す。"""
    slices = {}  # (item, venue, month) -> {"dates": set, "broken_dv": set}

    if items in ("results", "both"):
        all_dv = collect_all_results_dv(sb, eq, gte, lte)
        broken_dv = set(collect_results_targets(sb, eq, gte, lte))
        for d, v in all_dv:
            key = ("results", v, month_of(d))
            s = slices.setdefault(key, {"dates": set(), "broken_dates": set()})
            s["dates"].add(d)
            if (d, v) in broken_dv:
                s["broken_dates"].add(d)

    if items in ("entry", "both"):
        all_dv = collect_all_entry_dv(sb, eq, gte, lte)
        broken_dv = set(collect_entry_targets(sb, eq, gte, lte))
        for d, v in all_dv:
            key = ("entry", v, month_of(d))
            s = slices.setdefault(key, {"dates": set(), "broken_dates": set()})
            s["dates"].add(d)
            if (d, v) in broken_dv:
                s["broken_dates"].add(d)

    out = []
    for (item, venue, mon), s in slices.items():
        out.append({
            "item": item, "venue": venue, "month": mon,
            "batches": len(s["dates"]),
            "broken_batches": len(s["broken_dates"]),
        })
    out.sort(key=lambda r: (r["item"], r["month"], r["venue"]))
    return out


def oldest_available_date(sb):
    """DB上の最古日付 = 取得可能範囲の下限の目安。"""
    cands = []
    for t in ("race_winner_log", "races"):
        try:
            d = sb.table(t).select("date").order("date").limit(1).execute().data
            if d:
                cands.append(d[0]["date"])
        except Exception:
            pass
    return min(cands) if cands else None


def to_yyyymmdd(date_iso):
    return date_iso.replace("-", "")


def enumerate_explicit_dates(from_iso, to_iso):
    """--from/--to(両端含む)の連続日付を YYYY-MM-DD で列挙。
    DB種に依らない明示バッチ化(4月のゼロ新規取得)用。"""
    if not from_iso or not to_iso:
        raise SystemExit("--explicit は --from と --to の両方が必須です")
    d0 = dt.date.fromisoformat(from_iso)
    d1 = dt.date.fromisoformat(to_iso)
    if d1 < d0:
        raise SystemExit("--to は --from 以降の日付にしてください")
    out = []
    cur = d0
    while cur <= d1:
        out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out


def post_scrape(base, secret, date_iso, venue, item, *, timeout, retries, backoff):
    """VPS /scrape を1会場×1日で叩く。リトライ付き。"""
    url = base.rstrip("/") + "/scrape"
    payload = {
        "date": to_yyyymmdd(date_iso),
        "venues": [venue],
        "items": [item],
        "secret": secret,
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return {"ok": True, "body": resp.json()}
            last_err = f"http_{resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            wait = backoff * (2 ** attempt)
            print(f"      retry {attempt+1}/{retries} after {wait:.1f}s ({last_err})")
            time.sleep(wait)
    return {"ok": False, "error": last_err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", choices=["results", "entry", "both"], default="results",
                    help="再取得対象(results=結果, entry=出走表, both=両方)")
    ap.add_argument("--venue", default=None, help="会場名で絞り込み(段階実行/小範囲試行用)")
    ap.add_argument("--venues", default=None,
                    help="会場名カンマ区切り(--explicit時の会場ゲート用。例: 丸亀,大村)")
    ap.add_argument("--from", dest="from_date", default=None, help="YYYY-MM-DD 下限")
    ap.add_argument("--to", dest="to_date", default=None, help="YYYY-MM-DD 上限")
    ap.add_argument("--explicit", action="store_true",
                    help="DB種に依らず --from/--to の全日付 × 指定会場を明示的にバッチ化"
                         "(DB未取得の月=4月のゼロ新規取得用。oldestクランプを無効化)")
    ap.add_argument("--sleep", type=float, default=4.0, help="バッチ間sleep秒(最低3.0)")
    ap.add_argument("--timeout", type=float, default=180.0, help="1リクエストのHTTPタイムアウト秒")
    ap.add_argument("--retries", type=int, default=2, help="エラー時リトライ回数")
    ap.add_argument("--backoff", type=float, default=5.0, help="指数バックオフ基準秒(5,10,...)")
    ap.add_argument("--max-batches", type=int, default=0, help="処理する最大バッチ数(0=無制限)")
    ap.add_argument("--dry-run", action="store_true", help="送信せず対象一覧のみ出力")
    ap.add_argument("--list-slices", action="store_true",
                    help="会場×月スライスの一覧(バッチ数・壊れ件数)を出力して終了")
    ap.add_argument("--all-dates", action="store_true",
                    help="壊れ行だけでなく範囲内の全(date,venue)を対象にする(スライス再取得用)")
    ap.add_argument("--log", default=None, help="実行ログJSONLの保存先")
    args = ap.parse_args()

    sleep_s = max(3.0, args.sleep)  # 安全側下限
    base = os.environ.get("VPS_BASE", DEFAULT_VPS)
    secret = os.environ.get("API_SECRET", DEFAULT_SECRET)
    sb = get_client()
    eq = {"venue": args.venue} if args.venue else None

    # 会場ゲート: --venues(カンマ区切り) または --venue を会場リストへ正規化
    explicit_venues = None
    if args.venues:
        explicit_venues = [v.strip() for v in args.venues.split(",") if v.strip()]
    elif args.venue:
        explicit_venues = [args.venue]

    # 取得可能範囲でクランプ(--explicit時はクランプ無効)
    oldest = oldest_available_date(sb)
    if args.explicit:
        if not explicit_venues:
            raise SystemExit("--explicit は --venue か --venues で会場ゲートの指定が必須です(全会場一括禁止)")
        gte = args.from_date
        lte = args.to_date
    else:
        gte = args.from_date or oldest
        lte = args.to_date

    print("=" * 72)
    print("データ基盤フェーズ4 バックフィル・オーケストレータ")
    print(f"  items={args.items} venue={args.venue or '(all)'} from={gte} to={lte or '(latest)'}")
    print(f"  VPS={base}  sleep={sleep_s}s timeout={args.timeout}s retries={args.retries} "
          f"backoff={args.backoff}s max_batches={args.max_batches or '∞'} dry_run={args.dry_run}")
    print(f"  取得可能最古日付(DB): {oldest}")
    print("=" * 72)

    # --list-slices: 会場×月スライス一覧を出して終了
    if args.list_slices:
        rows = enumerate_slices(sb, eq, gte, lte, args.items)
        print(f"\n会場×月スライス一覧 (items={args.items}):")
        print(f"  {'item':7s} {'month':8s} {'venue':6s} {'batches':>7s} {'broken':>7s}")
        tot_b = tot_brk = 0
        for r in rows:
            tot_b += r["batches"]; tot_brk += r["broken_batches"]
            print(f"  {r['item']:7s} {r['month']:8s} {r['venue']:6s} "
                  f"{r['batches']:>7d} {r['broken_batches']:>7d}")
        print(f"\n  スライス数={len(rows)} 合計バッチ={tot_b} 壊れバッチ={tot_brk}")
        print("  実行例: python scripts/sakura/backfill_phase4.py --items results "
              "--venue びわこ --from 2026-05-01 --to 2026-05-31 --all-dates")
        return

    # 対象集合の構築。(date,venue,item) のフラットなバッチ列に展開。
    # --explicit: DB種に依らず from..to の全日付 × 指定会場を直接バッチ化。
    # --all-dates: 壊れ行に限らず範囲内の全(date,venue)を対象(スライス再取得)。
    batches = []  # list of (date_iso, venue, item)
    if args.explicit:
        date_list = enumerate_explicit_dates(gte, lte)
        item_list = (["results", "entry"] if args.items == "both" else [args.items])
        # results→entry の順序を保つため item を外ループにしない(日付昇順優先)
        for d in date_list:
            for v in explicit_venues:
                for it in item_list:
                    batches.append((d, v, it))
    else:
        if args.items in ("results", "both"):
            src = collect_all_results_dv if args.all_dates else collect_results_targets
            for d, v in src(sb, eq, gte, lte):
                batches.append((d, v, "results"))
        if args.items in ("entry", "both"):
            src = collect_all_entry_dv if args.all_dates else collect_entry_targets
            for d, v in src(sb, eq, gte, lte):
                batches.append((d, v, "entry"))

    # 取得可能範囲外(oldest 未満)はスキップ(--explicit時はクランプ無効)
    if args.explicit:
        skipped_oob = []
    else:
        skipped_oob = [b for b in batches if oldest and b[0] < oldest]
        batches = [b for b in batches if not (oldest and b[0] < oldest)]
    # 日付昇順 → item(results→entry) → 会場 で安定ソート
    item_rank = {"results": 0, "entry": 1}
    batches.sort(key=lambda x: (x[0], item_rank.get(x[2], 9), x[1]))

    print(f"\n対象バッチ総数: {len(batches)}  (範囲外スキップ: {len(skipped_oob)})")
    by_item = defaultdict(int)
    for _d, _v, it in batches:
        by_item[it] += 1
    for it, n in by_item.items():
        print(f"  - {it}: {n} バッチ")

    if args.max_batches and args.max_batches > 0:
        batches = batches[:args.max_batches]
        print(f"  → max-batches により {len(batches)} バッチに制限")

    # 所要時間の概算(逐次 + sleep)
    est_sec = len(batches) * (sleep_s + 2.0)  # 1リクエスト平均2秒+sleepの粗い見積り
    print(f"  概算所要: 約 {est_sec/60.0:.1f} 分 (1バッチ≈{sleep_s+2.0:.1f}s 想定)")

    if args.dry_run:
        print("\n[dry-run] 送信せず対象を表示します(先頭30件):")
        for d, v, it in batches[:30]:
            print(f"    {it:7s} {d} {v}")
        if len(batches) > 30:
            print(f"    ... 他 {len(batches)-30} バッチ")
        print("\n[dry-run] 完了(送信なし)")
        return

    # 実行(逐次)
    logf = open(args.log, "w", encoding="utf-8") if args.log else None
    total = len(batches)
    ok_cnt = 0
    err_cnt = 0
    saved_sum = 0
    started = time.time()
    for i, (d, v, it) in enumerate(batches, 1):
        print(f"[{i}/{total}] {it} {d} {v} ...", flush=True)
        res = post_scrape(base, secret, d, v, it,
                          timeout=args.timeout, retries=args.retries, backoff=args.backoff)
        rec = {"idx": i, "date": d, "venue": v, "item": it}
        if res["ok"]:
            body = res["body"]
            # /scrape は results=[{venue,item,status,saved/...}] と summary を返す
            saved = 0
            statuses = []
            for r in body.get("results", []):
                statuses.append(r.get("status"))
                saved += r.get("saved", 0) or r.get("boats", 0) or 0
            saved_sum += saved
            ok_cnt += 1
            rec.update({"ok": True, "saved": saved, "statuses": statuses,
                        "summary": body.get("summary")})
            print(f"      ok saved={saved} statuses={statuses} ({body.get('summary')})")
        else:
            err_cnt += 1
            rec.update({"ok": False, "error": res["error"]})
            print(f"      ERROR: {res['error']}")
        if logf:
            logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logf.flush()
        if i < total:
            time.sleep(sleep_s)

    elapsed = time.time() - started
    if logf:
        logf.close()

    print("\n" + "=" * 72)
    print("バックフィル完了")
    print(f"  処理バッチ : {total}")
    print(f"  成功 / 失敗: {ok_cnt} / {err_cnt}")
    print(f"  saved合計  : {saved_sum}")
    print(f"  経過時間   : {elapsed/60.0:.1f} 分")
    if skipped_oob:
        print(f"  範囲外スキップ: {len(skipped_oob)} バッチ(最古日付 {oldest} 未満)")
    if args.log:
        print(f"  実行ログ   : {args.log}")
    print("=" * 72)


if __name__ == "__main__":
    main()
