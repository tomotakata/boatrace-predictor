データ基盤修正のフェーズ1「結果保存の完全化」を実装します。plan modeなので、まず正確な実装計画（差分・適用手順・検証・ロールバック）を提示し、承認後に本番反映してください。本番VPSのスクレイパーを触る高リスク作業です。慎重に。

## 対象
- 本番VPSの結果スクレイパー: /home/ubuntu/boatrace/server.py（接続情報・認証は tmp/vps_access.txt を読むこと）
- サービス: boatrace-scraper.service（uvicorn server:app, port 8080, 現在 active running）
- DB: Supabase（接続情報は .env: SUPABASE_URL / SUPABASE_KEY）
- 注意: engine.py（v58.7再現側）は触らない。

## 診断で確定済みの根本原因（詳細: tmp/data_infra_fix_plan.md を読むこと）
1. server.py:1055-1065 = 拡張列保存失敗時に winner_lane など最小列だけで再upsertするフォールバック → 1着しか残らない
2. server.py:1022 = result_all を _json.dumps した「文字列」でJSONB列に投入 → 型不整合で保存失敗を誘発
3. 拡張列前提なしで欠落時もジョブを止めない

## フェーズ1でやること
### ステップA（必須・最初に実施）: スキーマ確認
- race_winner_log の実カラムと型を確認（place2_lane, place3_lane, trifecta_result, exacta_result, trifecta_payout, exacta_payout, trifecta_place_payout, result_all が存在するか、result_all はJSONBか）。
- 重要: 拡張列が無い場合はフォールバック廃止を先にやってはいけない。無ければ先にmigration（列追加）が必要 → その要否を計画に明記。

### ステップB: server.py 修正（バックアップ必須）
- 編集前に cp でタイムスタンプ付きバックアップ（git管理外のため）。
- (1) フォールバックupsert（1055-1065）を廃止し、完全列が保存できない場合はerror扱い＋race_key単位でログ。
- (2) result_all は JSON文字列ではなく Python list/dict をそのままJSONBに渡す（:1022修正）。
- (3) 保存前の必須列チェック追加（winner_lane, place2_lane, place3_lane, trifecta_result, result_all）。

### ステップC: 安全な検証
- いきなり全体再起動せず、まず1レース（直近の確定済みレース1件）で保存パスを検証。
- 「trifecta_result非NULL・result_allが3着含むJSON配列・winner_laneのみ行が出ない」を確認。
- 既存の正常データを壊さないこと（upsert対象race_keyを絞る）。

### ステップD: 本番適用
- 問題なければサービス再起動（認証は tmp/vps_access.txt）。
- 再起動後 active running を確認し、新規取得1件で完全保存を再確認。

## 計画に必ず含めること
- スキーマ確認の結果とmigrationの要否
- 変更する具体的なコード差分（before/after）
- バックアップ手順・ロールバック手順
- 壊さずに確認する検証手順
- リスクと注意点

## 厳守
- 既存の壊れた行を一括変更しない（バックフィルは別フェーズ）。今回は「今後の新規データが完全保存される」ことがゴール。
- 本番DB全体を書き換えるSQLは実行しない。
- plan modeなので、まず計画を提示して承認を得てから本番反映すること。
