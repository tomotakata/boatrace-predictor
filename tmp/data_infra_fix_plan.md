# データ基盤修正 第1弾 診断・修正設計プラン

## 前提

- 今回は診断と修正設計のみ。実装・再起動・DB更新は行わない。
- `engine.py`（v58.7再現側）は対象外。
- 調査対象はローカル `backend` と VPS 上の `/home/ubuntu/boatrace/server.py`。

## 結論サマリ

- **結果書き込み元の主系は VPS の `/home/ubuntu/boatrace/server.py`**。ローカル `backend` 側には `race_winner_log` への書き込み処理はなく、参照のみ。
- **「1着しか保存されない」主因は、VPS 側の結果保存で拡張カラム書き込みに失敗した際、`winner_lane` など最小列だけでフォールバック upsert する実装があるため**。
- **1〜3着・3連単の取得元は boatrace.jp 公式結果ページで取得可能**。現コードは取得自体を試みているが、保存失敗時に欠損を許容してしまっている。
- **`boats` 欠損の主因は、出走表保存が「レース行だけ先に作る」設計で、艇保存失敗時も未完成レースを残すこと**。さらに HTML 依存の厳しい行判定があり、0件のまま終了しうる。
- **`race_key` 結合不整合の主因は、`race_winner_log.race_key` が `YYYYMMDD + venue_code + race_no(2桁)` なのに対し、`races` 側は `date + venue + race_no` しか持たず、しかも `venue_code` を保持していないこと**。結合仕様がコード上で統一されていない。

---

## 1. 結果保存の診断（最重要）

### 1-1. 書き込み元の確定

#### VPS 側
- `/home/ubuntu/boatrace/server.py:913` に `async def scrape_results(date, venues):`
- `/home/ubuntu/boatrace/server.py:1053` で `sb.table("race_winner_log").upsert(row, on_conflict="race_key").execute()`

#### ローカル backend 側
- `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/backend/app/api/races.py:247-251`
  では `race_winner_log` を **select** しているだけ
- ローカル `backend/app` 配下には `race_winner_log` への insert / upsert は見当たらない

### 1-2. 公式結果ソース

- `/home/ubuntu/boatrace/server.py:985-988`
  で公式結果ページ `https://www.boatrace.jp/owpc/pc/race/raceresult?...` を取得
- `/home/ubuntu/boatrace/server.py:957-982`
  の `extract_result_rows` で着順表をパース
- `/home/ubuntu/boatrace/server.py:927-955`
  の `extract_payouts` で払戻表をパース

つまり、**1〜3着・3連単・2連単・払戻を取得できる設計自体は存在**する。

### 1-3. 根本原因

#### 原因A: 保存失敗時に「1着だけ保存」へフォールバックする実装

該当箇所:
- `/home/ubuntu/boatrace/server.py:1055-1065`

内容:
- 拡張列を含む upsert が失敗すると、例外文字列に
  `place2_lane`, `place3_lane`, `trifecta_result`, `exacta_result`, `trifecta_payout`, `exacta_payout`, `trifecta_place_payout`, `result_all`
  が含まれる場合に、
- `race_key, venue, date, race_no, winner_course, winner_lane` だけの `old_row` を再 upsert して成功扱いにしている

影響:
- スキーマ未反映や型不整合がある期間、**結果取得はできていても DB には winner 系だけ残る**
- 実測の「`result_all` が1着しか保存されていない/実質1件以下が70.3%」と整合

#### 原因B: `result_all` を JSONB 列に文字列で保存している

該当箇所:
- `/home/ubuntu/boatrace/server.py:1022`

内容:
- `result_all` に `_json.dumps(result_all, ensure_ascii=False)` を入れている

懸念:
- Supabase/PostgREST 側で JSONB に文字列投入が常に許容されるとは限らず、環境や既存データ状態によっては失敗要因になる
- 失敗すると上記フォールバックに入り、結果として `winner_lane` だけ残る

#### 原因C: 拡張列の存在を前提にせず、欠落時もジョブを止めない

該当箇所:
- `/home/ubuntu/boatrace/server.py:1278-1285`
- `/home/ubuntu/boatrace/server.py:1295-1302`

内容:
- `place2_lane` 以降の列は後付け migration 前提
- しかし `scrape_results` 側は列不足時にジョブ失敗ではなく旧列保存へ退避する

影響:
- 運用上は「成功」に見えるが、学習データとしては壊れる

### 1-4. 追加所見

#### `winner_course` が実質 `winner_lane` と同値になっている

該当箇所:
- `/home/ubuntu/boatrace/server.py:977-980`

内容:
- `extract_result_rows` で `course` に `lane_digits` をそのまま入れている

影響:
- 進入コースではなく枠番を保存している可能性が高い
- 今回の主題ではないが、結果品質として別途修正対象

### 1-5. 修正方針

対象:
- `/home/ubuntu/boatrace/server.py`

方針:
1. `scrape_results` のフォールバック保存を廃止し、**完全列が保存できない場合は error 扱い**に変更
2. `result_all` は JSON 文字列ではなく **Python list/dict をそのまま JSONB に渡す**
3. 保存前に必須列チェックを追加
   - `winner_lane`
   - `place2_lane`
   - `place3_lane`
   - `trifecta_result`
   - `result_all`
4. 失敗時は `race_key` 単位でログを残し、欠損を可視化
5. `winner_course` は別途、公式 HTML から進入コースを正しく取れるか確認して修正

検証指標:
- 新規取得分で `trifecta_result` 非NULL率が 100%
- `result_all` が 3着まで含む JSON 配列で保存される率が 100%
- `winner_lane` のみ保存される行が 0 件

---

## 2. 出走表6艇欠損の診断

### 2-1. VPS 側の主処理

該当箇所:
- `/home/ubuntu/boatrace/server.py:96-208` `fetch_race_entry`
- `/home/ubuntu/boatrace/server.py:210-230` `scrape_entry`

### 2-2. 根本原因

#### 原因A: `races` を先に作り、`boats` が0件でも未完成レースを残す

該当箇所:
- `/home/ubuntu/boatrace/server.py:108-115`

内容:
- 出走表取得前に `races` 行を insert
- その後 `boats_saved` が 0 件でもそのまま return

影響:
- `races` はあるが `boats` が 0 件のレースが大量に残る
- 実測の「660レースは boats 0件」と整合

#### 原因B: HTML 行判定が厳しすぎる

該当箇所:
- `/home/ubuntu/boatrace/server.py:117-119`

内容:
- `cells = row.find_all(["td","th"])`
- `if len(cells) < 20: continue`

影響:
- 公式 HTML 構造変更や一部レースページ差異で、選手行を全スキップしうる
- その場合 `boats_saved = 0` のまま終了

#### 原因C: 会場×12R を並列取得するが、6艇揃いを完了条件にしていない

該当箇所:
- `/home/ubuntu/boatrace/server.py:223-227`

内容:
- `asyncio.gather(..., return_exceptions=True)` 後に単純合計だけ返す
- レース単位で「6艇揃ったか」の検証がない

影響:
- 1〜5艇しか保存されない中途半端なレースも成功扱い

### 2-3. ローカル backend 側の補足

ローカルにも出走表系スクレイパーはある:
- `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/backend/app/scrapers/boaters.py:68-137`
- `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/backend/app/scrapers/boatfrontier.py`
- `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/backend/app/scrapers/exhibition.py`

ただし今回の実データ欠損の主因としては、VPS 側 `scrape_entry` の運用ジョブが主系とみるのが妥当。

### 2-4. 修正方針

対象:
- `/home/ubuntu/boatrace/server.py`

方針:
1. `fetch_race_entry` を **レース単位の完全性検証付き** に変更
   - 6艇揃わなければ失敗扱い
2. `races` 先行作成は維持しても、`entry_status` 的な完了状態を持たせる
   - `scheduled`
   - `entry_partial`
   - `entry_complete`
3. HTML パース条件を `len(cells) < 20` のような固定列数依存から、枠番・登録番号・選手名の存在ベースへ変更
4. 1レース単位で再試行可能にする
5. 日次棚卸しで `boats_count != 6` を検知する監査クエリを追加

検証指標:
- `races` に対する `boats=0` 件数が 0
- `boats_count=6` のレース率が 100%
- `boats_count in (1..5)` の中途半端レースが 0

---

## 3. `race_key` 結合不整合の診断

### 3-1. 現行仕様

#### 結果側
- `/home/ubuntu/boatrace/server.py:1007`
- `race_key = f"{date}{jcd}{str(rno).zfill(2)}"`

仕様:
- `YYYYMMDD + venue_code(2桁) + race_no(2桁)`

#### races 側
- VPS:
  - `/home/ubuntu/boatrace/server.py:109-113`
- ローカル:
  - `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/backend/app/scrapers/boaters.py:53-58`

仕様:
- `date`
- `venue`（日本語会場名）
- `race_no`

### 3-2. 根本原因

#### 原因A: `races` に `venue_code` がなく、`race_key` を同一仕様で再構成できない

影響:
- `race_key` 文字列だけで直接結合しようとしても、`races` 側に同じキー材料がない

#### 原因B: 結合仕様がコード上で統一されていない

証拠:
- ローカル API は `race_winner_log` 参照時に `date + venue + race_no` で検索している
  - `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/backend/app/api/races.py:247-251`
- 一方、結果保存は `race_key` を主キー相当として upsert している
  - `/home/ubuntu/boatrace/server.py:1053`

影響:
- 文字列キー運用と複合キー運用が混在
- 棚卸し時に `race_key` ベースで突合すると一致率が極端に落ちる

#### 原因C: `venue_code` と `venue` 名称の変換責務が DB に保存されていない

該当箇所:
- `/home/ubuntu/boatrace/server.py:42-49` `resolve_venue`

影響:
- アプリ内では変換できても、DB 上の永続キーとしては不十分

### 3-3. 修正方針

対象:
- `/home/ubuntu/boatrace/server.py`
- ローカル `backend` の race 参照系
- DB スキーマ

方針:
1. `races` に `venue_code` を追加
2. `races` に正規化キー `race_key` を追加し、**結果側と同一仕様で保存**
3. `race_winner_log` の主結合キーを `race_key` に統一
4. API 参照も `date+venue+race_no` ではなく、可能なら `race_key` ベースへ寄せる
5. 既存 `races` は `date`, `venue`, `race_no` から `venue_code` を補完して `race_key` 再計算

検証指標:
- `race_winner_log.race_key` と `races.race_key` の一致率 100%
- `race_winner_log` と `races` の結合件数が理論値まで回復

---

## 4. 過去データのバックフィル戦略

## 4-1. 可否

- **可**。VPS 現行コードがすでに boatrace.jp 公式結果ページを日付・会場・レース番号単位で取得できる構造になっている。
- 該当箇所:
  - `/home/ubuntu/boatrace/server.py:985-988`

### 4-2. バックフィル対象

1. `race_winner_log`
   - `place2_lane`
   - `place3_lane`
   - `trifecta_result`
   - `exacta_result`
   - `trifecta_payout`
   - `exacta_payout`
   - `trifecta_place_payout`
   - `result_all`
2. `races`
   - `venue_code`
   - `race_key`
3. `boats`
   - 0件レース
   - 6艇未満レース

### 4-3. 実施順序

#### フェーズ1: スキーマ整合確認
- `race_winner_log` 拡張列が本番 DB に存在することを確認
- `races` に `venue_code`, `race_key` を追加する設計を確定

#### フェーズ2: 新規取得ロジック修正
- まず今後の新規データが壊れない状態にする

#### フェーズ3: `races` 正規化
- 既存 `races` に `venue_code`, `race_key` を再計算

#### フェーズ4: 結果バックフィル
- 対象期間の日付×会場×1〜12R を再取得
- `race_key` で upsert
- 既存の `winner_lane` のみ行を完全結果で上書き

#### フェーズ5: 出走表バックフィル
- `boats=0` または `boats_count<6` のレースだけ再取得

### 4-4. 対象期間・件数見込み

現状棚卸しベース:
- `races`: 1404
- `race_winner_log`: 1989
- 完全結果: 151

回復見込み:
- `race_winner_log` は、対象期間の公式結果が残っている限り **大半を完全結果化できる見込み**
- `races` 1404 件に対して `race_key` 正規化後、結果結合率は大幅改善見込み
- `boats` は公式出走表ページが取得可能な期間なら、660件の 0件レースを再取得可能

### 4-5. 注意点

- 公式サイト側で古い日付の公開範囲制限がある場合、全期間回復できない可能性あり
- 既存 `race_winner_log` に重複や不正 JSON がある場合、upsert 前に整形が必要
- バックフィルは本番 DB を更新するため、**dry-run 集計 → 小期間試行 → 全期間実行** の順が必須

---

## 5. 実装フェーズ分割

### フェーズ1: 結果保存の完全化

対象:
- `/home/ubuntu/boatrace/server.py`

内容:
- フォールバック保存廃止
- JSONB 正常保存
- 完全結果必須チェック

確認指標:
- 新規取得分の `trifecta_result` 非NULL率
- `result_all` 完全保存率
- `winner_lane` のみ行の新規発生ゼロ

### フェーズ2: 出走表完全化

対象:
- `/home/ubuntu/boatrace/server.py`

内容:
- 6艇揃い検証
- 部分保存の失敗扱い
- 再試行設計

確認指標:
- `boats=0` レース数
- `boats_count<6` レース数

### フェーズ3: キー正規化

対象:
- DB スキーマ
- VPS 保存処理
- ローカル API 参照処理

内容:
- `races.venue_code`
- `races.race_key`
- 結合キー統一

確認指標:
- `race_winner_log` と `races` の結合率

### フェーズ4: バックフィル

対象:
- 結果
- 出走表

内容:
- 欠損レースのみ再取得
- 完全結果・6艇揃いを回復

確認指標:
- 「出走表 + 完全結果」両方揃ったレース数
- 学習可能レース数

---

## 6. リスク・注意点

- 本番 DB / VPS が対象のため、**読み取り調査と更新作業を厳密に分離**すること
- `scrape_results` のフォールバック廃止後は、スキーマ未整合があるとジョブが明示的に失敗する。先に migration 状態確認が必要
- `race_key` 正規化は既存参照処理に影響するため、API 側の参照キー移行を段階的に行う
- `winner_course` は現状誤値の可能性が高く、DOT 学習特徴として使うなら別途是正が必要
- `engine.py` は今回対象外。予想ロジックには触れない

---

## 7. 直近の実装優先順位

1. VPS `scrape_results` のフォールバック保存廃止
2. `result_all` の JSONB 保存方式修正
3. `races` に `venue_code` / `race_key` を持たせる設計
4. `scrape_entry` の 6艇完全性チェック追加
5. 小期間バックフィル
6. 全期間バックフィル


## 8. VPS接続情報ファイルによる再確認

- 接続情報は `/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor/tmp/vps_access.txt` を読み取り確認した。
- 指定どおり `host=153.121.51.74`, `user=ubuntu`, 対象ファイル `/home/ubuntu/boatrace/server.py` を読み取り専用で確認した。
- `systemctl status boatrace-scraper.service --no-pager` により、実運用サービスが `uvicorn server:app` で `/home/ubuntu/boatrace/server.py` を起動していることを確認した。
- これにより、**実運用中の結果保存コードが VPS 上の `server.py` であることを再確認**した。

### 8-1. サービス実行確認

該当証拠:
- `boatrace-scraper.service`
- `Main PID: ... uvicorn server:app --host 0.0.0.0 --port 8080`

意味:
- 読み取った `server.py` は単なる退避ファイルではなく、現行サービスの実行対象。
- よって `scrape_results` / `scrape_entry` の診断結果は本番運用コードに対するものと判断できる。
