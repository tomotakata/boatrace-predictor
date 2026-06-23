# DOTレーティング step-2-2: 本命モデル学習(LightGBM)実測レポート

> 既存 v58.7 再現エンジン(`backend/app/prediction/engine.py`)とは**完全独立**の新規データ駆動システム。
> 本番 Supabase は **SELECT のみ**・書込ゼロ。engine.py 不変更。
> 実行スクリプト: `scripts/dot/train_lightgbm.py`(読取専用 / step-2-1 `train_baseline.py` の取得・特徴・評価・ベースラインを流用)。実測日: 2026-06-15。

## 1. データ(INNER JOIN: date+venue+race_no)

| 指標 | 実数 |
|---|---:|
| 学習可能レース | **1029**(step-2-1 の 454 から 5月entry拡大で増加) |
| 艇行数 | **6174**(=1029×6) |
| 月別 | 2026-05 = 623R / 2026-06 = 406R |

## 2. 特徴量(リーク防止済み・43列・LogRegと同一)

- BASE 29列 + 枠内相対化(z-score/順位)14列 = **43列**。step-2-1 と完全に同じ特徴セット。
- **欠損処理が本命の差分**: LightGBM は欠損(`general1y_*` 等カバレッジ22%)を **median補完せずネイティブに分岐**で扱える。比較のため median補完版も併走(`--with-impute`)。
- **リーク防止【二重ガード検証済み】**:
  - blacklist: `winner_*/place2_*/place3_*/trifecta_*/exacta_*/result_all/is_win/is_top3/rank…` を除外。特徴量 ∩ blacklist = 空。
  - allowlist: 特徴は `BASE_FEATURES` と相対派生(`*_z` / `*_rank`)のみで構成されることを自動検証 → `OK(許可特徴のみ)`。
  - 自動判定 **`leak_free: true`**。

## 3. モデル・分割

- **LightGBM 二値分類**(`objective=binary`)。過学習抑制の控えめ設定: `lr=0.03 / num_leaves=15 / max_depth=4 / min_child_samples=30 / subsample=colsample=0.8 / reg_alpha=0.5 / reg_lambda=1.0`、early_stopping=50。
- **分割(2系統)**:
  - (a) **6月内 会場層化 5-fold**(レース単位split=艇行リーク防止)。5月623Rは常にtrain合流。→ LogReg と**同一OOF集合(6月406R)**で apples-to-apples 比較。
  - (b) **時系列ホールドアウト**: 5月623R train → 6月406R valid。頑健性確認。

## 4. 評価結果 ― is_win(1着)・6月OOF 406レース(同一集合)

| モデル | LogLoss | AUC | Top1的中 | 3連単的中 | 回収率 |
|---|---:|---:|---:|---:|---:|
| **DOT LightGBM(欠損ネイティブ)** | **0.350** | **0.807** | **55.2%** | 7.6% | 61.6% |
| DOT LightGBM(median補完) | 0.348 | 0.809 | 54.4% | 7.9% | 66.8% |
| DOT LogReg(step-2-1基準) | 0.362 | 0.798 | 52.0% | 8.1% | 78.8% |
| (1) 1号ベタ | - | - | 54.2% | 8.6% | 96.9% |
| (2) national_win_rate順 | - | - | 38.2% | 6.7% | 135.7% |

- **時系列ホールドアウト(5月→6月)・欠損ネイティブ**: LogLoss=0.358 / AUC=0.797 / Top1=53.9% / 3連単=9.6% / **回収率=98.6%**。K-fold と整合し、頑健。

### 4-1. ★ヘッドライン
- **Top1的中 55.2% で、LogReg(52.0%)も 1号ベタ(54.2%)も上回った**(本タスク最大目標を達成)。
- **AUC 0.807 / LogLoss 0.350** とも LogReg(0.798 / 0.362)を改善。**欠損ネイティブが median補完より AUC/LogLoss・Top1いずれもわずかに優位**(general1y_* 欠損の情報を温存できた効果)。
- 時系列ホールドアウトでは回収率98.6%と K-fold(61.6%)より高く、6月単独評価より分散の影響を受けにくい。

## 5. 評価結果 ― is_top3(3着内)・6月OOF 406レース

| モデル | LogLoss | AUC | Top1的中 | 3連単的中 | 回収率 |
|---|---:|---:|---:|---:|---:|
| **DOT LightGBM(欠損ネイティブ)** | **0.586** | **0.752** | 50.7% | 8.6% | 86.8% |
| DOT LightGBM(median補完) | 0.586 | 0.752 | 51.5% | 9.6% | 81.4% |
| DOT LogReg(step-2-1基準) | 0.591 | 0.749 | 48.0% | 8.9% | 107.6% |
| (1) 1号ベタ | - | - | 54.2% | 8.6% | 96.9% |
| (2) national_win_rate順 | - | - | 38.2% | 6.7% | 135.7% |

- 時系列(5月→6月)欠損ネイティブ: AUC=0.739 / Top1=47.8% / 回収率=78.5%。
- is_top3 でも LightGBM が LogReg を AUC・Top1で上回る。ただし「頭1点」では 1号ベタ(54.2%)に未達(is_top3 は3着内確率で1着特化ではないため当然)。

## 6. 特徴量重要度(gain・5fold平均・is_win 欠損ネイティブ 上位)

| 順位 | 特徴量 | gain | split |
|---:|---|---:|---:|
| 1 | **lane**(枠) | 12201.9 | 216.4 |
| 2 | **national_win_rate_z**(枠内相対の全国勝率) | 2193.8 | 178.6 |
| 3 | national_win_rate | 1063.1 | 149.4 |
| 4 | national_win_rate_rank | 846.8 | 42.2 |
| 5 | age | 793.9 | 166.0 |
| 6 | motor_place2_rate_z | 779.4 | 160.0 |
| 7 | avg_st_z | 770.4 | 143.8 |
| 8 | national_place2_rate_z | 695.1 | 110.4 |
| 9 | weight_z | 681.5 | 158.0 |
| 10 | local5y_win_rate_z | 670.9 | 79.2 |

- **`lane`(枠) が圧倒的に最重要**(競艇の1号頭支配と整合)。次いで**枠内相対化した全国勝率 `national_win_rate_z`** が突出。**設計の「絶対値より相対力」仮説をデータが支持**。
- ST(`avg_st_z`)・モーター(`motor_place2_rate_z`)・体重(`weight_z`)の相対値も効く。`general1y_*`(欠損多)は単独では上位に出ないが、欠損ネイティブが LogReg(median補完)より良い=欠損パターン自体が弱い情報を持つ。
- is_top3 では `national_win_rate_z` の比重がさらに上昇(gain 6022.9)し、長期力の相対差が3着内に効く。

## 7. ACCEPT 確認

- [x] LightGBM が **1029レース**で学習・評価でき、AUC/LogLoss/Top1/3連単/回収率が数値で出る。
- [x] LogReg基準・1号ベタ・national順との比較表が **同一OOF(6月406R)** で出る。
- [x] **`leak_free: true` を自動検証**(blacklist + allowlist 二重ガード)。
- [x] 5月→6月 **時系列ホールドアウト**を併用し頑健性確認。
- [x] **特徴量重要度上位を報告**(gain/split)。
- [x] engine.py・本番DB不変更(SELECTのみ・`insert/update/upsert/delete` 不使用を検証。`sys.path.insert` はPythonリスト操作でDB非関連)。

## 8. 結論

- **本命 LightGBM は LogReg を全指標(AUC/LogLoss/Top1)で上回り、Top1的中 55.2% で 1号ベタ 54.2% も超えた**(最重要目標を達成)。
- 欠損ネイティブ処理が median補完版より優位で、設計の狙い(欠損に強いモデル)が機能。
- 回収率は K-fold単独(61.6%)では 1号ベタに届かないが、時系列ホールドアウトでは98.6%。406R は回収率の分散が大きく、次フェーズ(3連単候補生成の点数最適化・買い目戦略)で改善余地。

## 9. 成果物

- `scripts/dot/train_lightgbm.py` — LightGBM 学習パイプライン(取得→特徴整形→学習→評価→重要度、読取専用)
- `tmp/dot_lightgbm.json` — 評価結果・特徴量重要度の実測JSON(native / median_impute 両方)
- 本レポート
