# データ基盤修正フェーズ4 実施レポート — 過去の壊れた行の一括バックフィル

実施日: 2026-06-14
対象本番: VPS `ubuntu@153.121.51.74` / `boatrace-scraper.service` (server.py v6.2-v60.0)
方式: ローカルから supabase-py で対象抽出 → VPS既存 `/scrape`(items=[results]/[entry])を会場×日付単位で**逐次**呼び出し(本番 server.py 非改変・冪等 upsert on_conflict=race_key)

---

## 1. 改善サマリ(DoD)

| 指標 | 実施前 | 実施後 | 評価 |
|---|---|---|---|
| race_winner_log 総行数 | 1989 | 2026 | +37(欠損していた結果行を新規補完) |
| trifecta_result IS NULL | 1838 (92.4%) | **2 (0.1%)** | 非NULL率 7.6% → **99.9%** |
| result_all 壊れ(欠損+二重エンコード) | 1989 (100%) | **2 (0.1%)** | ほぼ全解消 |
| place2_lane / place3_lane NULL | 1695 / 1732 | 2 / 2 | ほぼ全解消 |
| races boats=0 | 660 (46.6%) | **444 (31.4%)** | 実在レース216件を補完 |

- **trifecta_result は実質100%達成。** 残2件は公式が「不成立・返還」のため三連単結果が存在しないレース(芦屋 2026-06-08 R7=不成立/返還、尼崎 2026-06-11 R11=返還)。データ欠損ではなく仕様上の正しい状態。
- **boats=0 の残444件は全て status=`scheduled` の空プレースホルダ行(幻レース)。** 公式サイトに出走表・結果のいずれも存在せず(その会場×日付で実際に開催されていない)、再取得では回復不可。

## 2. 処理ログ

### results 再取得(race_winner_log)
- 対象: `trifecta_result IS NULL` の (date,venue) = 169組
- 結果: **168/168 バッチ成功・失敗0**(丸亀06-06は試行で先行処理)、saved合計 2012、経過 約55分
- 追加2件(芦屋06-08・尼崎06-11)を個別再実行 → 各 saved=11(残1レースは不成立/返還で恒久的に三連単なし)

### entry 再取得(races/boats)
- 対象: `boats=0` の (date,venue) = 55組
- 結果: **55/55 バッチ成功・失敗0**、saved合計 1296(=216レース×6艇)、経過 約80分
- 内訳: 18バッチ(2026-05-06, 05-24)が saved=72 で成功、37バッチ(2026-06-06/08/12)は saved=0 = 公式に出走表が存在しない幻レース

## 3. 非破壊性の確認
- 総行数は増加のみ(1989→2026)で**削除ゼロ**。
- upsert は `on_conflict=race_key` で対象キーのみ更新。実施前から正常だった151行は `result_all` 正常(ok)のまま保持。
- entry は server.py 仕様により「6艇揃い時のみ保存」=部分破壊なし。

## 4. throttle / 安全策(実績)
- 並列なし完全逐次、バッチ間 sleep 4.0秒、HTTPタイムアウト300秒、エラー時指数バックオフ(5s→10s)最大2回。
- リトライ発動は数件のみ、全てidempotent upsertで安全に再実行。本番サービスへの影響は観測されず。

## 5. 残課題(今回スコープ外・要判断)

1. **幻レース444行(status=scheduled・boats=0・公式に実体なし)**
   - 再取得不可。本質的には DELETE 対象だが破壊的操作のため未実施。
   - 対応するなら Dashboard手動SQL で `DELETE FROM races WHERE status='scheduled' AND id NOT IN (SELECT race_id FROM boats)` 等を要検討(別途承認推奨)。

2. **races.race_key 未設定(全1416行)/ venue_code 未設定(996行)**
   - phase3 で列は追加済みだが既存行の再計算が未実施。
   - results側(race_winner_log)のバックフィルには非依存のため今回は対象外。必要なら別フェーズで一括 UPDATE を検討。

## 6. 成果物
- `scripts/sakura/diagnose_broken_rows.py` — 壊れ行棚卸し(読み取り専用・再利用可)
- `scripts/sakura/backfill_phase4.py` — バックフィル・オーケストレータ(--dry-run/--max-batches/段階実行対応)
- `tmp/phase4_diag.json`(実施前) / `tmp/phase4_diag_after.json`(実施後)
- `tmp/phase4_results_full.jsonl` / `tmp/phase4_entry_full.jsonl`(実行ログ)
