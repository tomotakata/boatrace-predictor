#!/usr/bin/env python3
"""データ基盤修正フェーズ4(Q2) — races.race_key / venue_code 決定論補完

ローカルから supabase-py(PostgREST)で races の race_key / venue_code を
決定論的に補完する。VPSからDB直結不可のため PostgREST 経由 UPDATE を採用。

- race_key 式 : f"{YYYYMMDD}{venue_code}{race_no:02d}"  (server.py:1091 踏襲)
- venue_code  : VENUE_CODE_MAP[venue]                    (server.py:26-30 踏襲)

安全策(冪等・非破壊):
  - 既に正しい値が入っている行は書き込まない(スキップ)。
  - 既存の非NULL値が計算値と「異なる」行は上書きせず conflict として報告のみ。
  - 計算 race_key の重複(date+venue+race_no 衝突)を事前検出。
  - --dry-run で対象件数・サンプル・conflict・重複を提示(書き込みなし)。

使い方:
  python scripts/sakura/backfill_racekey.py --dry-run
  python scripts/sakura/backfill_racekey.py            # 本実行(冪等)
"""
import os
import sys
import time
import argparse
from collections import defaultdict

from supabase import create_client

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)

# 公式コード(クロスチェック用)。race_winner_log の race_key から実行時に
# 経験的に導出したマップを「正」とし、これは照合用の参考に留める。
# 注: server.py の VENUE_CODE_MAP は びわこ/住之江 が実データと逆(=誤り)のため使わない。
OFFICIAL_VENUE_CODE = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05", "浜名湖": "06",
    "蒲郡": "07", "常滑": "08", "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16", "宮島": "17", "徳山": "18",
    "下関": "19", "若松": "20", "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}
PAGE = 1000


def get_client():
    url = os.environ.get("SUPABASE_URL", DEFAULT_URL)
    key = os.environ.get("SUPABASE_KEY", DEFAULT_KEY)
    return create_client(url, key)


def derive_venue_code_map(sb):
    """race_winner_log の race_key(YYYYMMDD+code(2)+rno(2))から
    venue -> code を経験的に導出する。これが join 突合の正となる。
    複数コードが観測された venue があれば例外で停止(要調査)。"""
    rows = []
    s = 0
    while True:
        b = sb.table("race_winner_log").select("venue,race_key").range(s, s + PAGE - 1).execute().data or []
        rows.extend(b)
        if len(b) < PAGE:
            break
        s += PAGE
    counts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        rk = r.get("race_key")
        v = r.get("venue")
        if not v or not rk or len(rk) != 12:
            continue
        counts[v][rk[8:10]] += 1
    vmap = {}
    conflicts = {}
    for v, codes in counts.items():
        if len(codes) > 1:
            conflicts[v] = dict(codes)
        vmap[v] = max(codes, key=codes.get)
    if conflicts:
        raise RuntimeError(f"race_winner_log に複数コードの会場あり(要調査): {conflicts}")
    # 公式マップとの突合(参考ログ)
    for v, c in vmap.items():
        if OFFICIAL_VENUE_CODE.get(v) and OFFICIAL_VENUE_CODE[v] != c:
            print(f"  [warn] 経験コード {v}={c} が公式参考表({OFFICIAL_VENUE_CODE[v]})と相違")
    return vmap


def fetch_all_races(sb):
    rows = []
    s = 0
    while True:
        b = (sb.table("races").select("id,date,venue,race_no,race_key,venue_code")
             .order("date").range(s, s + PAGE - 1).execute().data or [])
        rows.extend(b)
        if len(b) < PAGE:
            break
        s += PAGE
    return rows


def compute(date_iso, venue, race_no, vmap):
    vc = vmap.get(venue)
    if vc is None or race_no is None:
        return None, None
    rk = f"{date_iso.replace('-', '')}{vc}{str(race_no).zfill(2)}"
    return rk, vc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="書き込まず対象を提示")
    ap.add_argument("--sleep", type=float, default=0.05, help="UPDATE間の待機秒(既定0.05)")
    ap.add_argument("--limit-sample", type=int, default=10, help="dry-run時のサンプル表示数")
    args = ap.parse_args()

    sb = get_client()
    print("venue->code マップを race_winner_log から導出中...")
    vmap = derive_venue_code_map(sb)
    print(f"  導出会場数: {len(vmap)}")
    races = fetch_all_races(sb)
    total = len(races)

    # 集計
    unknown_venue = []           # マップに無い会場
    none_rno = 0                 # race_no=None
    dup_map = defaultdict(list)  # 計算race_key -> [id]
    need_rk = []                 # race_key 補完が必要 (id, rk)
    need_vc = []                 # venue_code 補完が必要 (id, vc)
    conflict_rk = []             # 既存race_keyが計算値と不一致(上書きしない)
    conflict_vc = []             # 既存venue_codeが計算値と不一致(上書きしない)
    ok_rk = 0                    # 既に正しいrace_key
    ok_vc = 0                    # 既に正しいvenue_code
    samples = []

    for r in races:
        rk, vc = compute(r["date"], r["venue"], r["race_no"], vmap)
        if r["venue"] not in vmap:
            unknown_venue.append(r["venue"])
            continue
        if r["race_no"] is None:
            none_rno += 1
            continue
        dup_map[rk].append(r["id"])

        cur_rk = r.get("race_key")
        cur_vc = r.get("venue_code")
        # race_key
        if not cur_rk:
            need_rk.append((r["id"], rk))
        elif cur_rk == rk:
            ok_rk += 1
        else:
            conflict_rk.append((r["id"], cur_rk, rk))
        # venue_code
        if not cur_vc:
            need_vc.append((r["id"], vc))
        elif str(cur_vc) == vc:
            ok_vc += 1
        else:
            conflict_vc.append((r["id"], cur_vc, vc))

        if len(samples) < args.limit_sample:
            samples.append((r["date"], r["venue"], r["race_no"], cur_rk, rk, cur_vc, vc))

    dups = {k: v for k, v in dup_map.items() if len(v) > 1}

    print("=" * 72)
    print("races.race_key / venue_code 決定論補完")
    print(f"  モード: {'DRY-RUN(書き込みなし)' if args.dry_run else '本実行'}")
    print("=" * 72)
    print(f"races 総行数              : {total}")
    print(f"マップに無い会場          : {sorted(set(unknown_venue))} ({len(unknown_venue)}行)")
    print(f"race_no=None 行           : {none_rno}")
    print(f"計算 race_key の重複       : {len(dups)} (一意制約安全=0であること)")
    for k, v in list(dups.items())[:5]:
        print(f"    dup {k}: {v}")
    print("-" * 72)
    print(f"race_key  補完対象        : {len(need_rk)}")
    print(f"race_key  既に正しい(skip): {ok_rk}")
    print(f"race_key  conflict(上書きせず): {len(conflict_rk)}")
    for c in conflict_rk[:5]:
        print(f"    conflict id={c[0]} 既存={c[1]} 計算={c[2]}")
    print(f"venue_code 補完対象       : {len(need_vc)}")
    print(f"venue_code 既に正しい(skip): {ok_vc}")
    print(f"venue_code conflict(上書きせず): {len(conflict_vc)}")
    for c in conflict_vc[:5]:
        print(f"    conflict id={c[0]} 既存={c[1]} 計算={c[2]}")
    print("-" * 72)
    print("サンプル (date venue R | 既存rk -> 計算rk | 既存vc -> 計算vc):")
    for s in samples:
        print(f"    {s[0]} {s[1]} R{s[2]} | {s[3]} -> {s[4]} | {s[5]} -> {s[6]}")

    if args.dry_run:
        print("\n[dry-run] 書き込みは行いません。")
        print("=" * 72)
        return

    # 本実行: 補完が必要なフィールドのみ UPDATE(冪等・非破壊)
    # id 単位で race_key/venue_code をまとめて更新
    need_rk_map = dict(need_rk)
    need_vc_map = dict(need_vc)
    target_ids = set(need_rk_map) | set(need_vc_map)
    print(f"\n本実行: {len(target_ids)} 行を UPDATE します...")
    updated = 0
    errors = 0
    for i, rid in enumerate(sorted(target_ids), 1):
        patch = {}
        if rid in need_rk_map:
            patch["race_key"] = need_rk_map[rid]
        if rid in need_vc_map:
            patch["venue_code"] = need_vc_map[rid]
        try:
            sb.table("races").update(patch).eq("id", rid).execute()
            updated += 1
        except Exception as e:
            errors += 1
            print(f"    ERR id={rid}: {e}")
        if i % 200 == 0:
            print(f"    {i}/{len(target_ids)} ...")
        if args.sleep:
            time.sleep(args.sleep)

    print("\n" + "=" * 72)
    print(f"完了: updated={updated} errors={errors}")
    print("=" * 72)


if __name__ == "__main__":
    main()
