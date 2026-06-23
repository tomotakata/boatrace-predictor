# DOTレーティング step-2-1: ベースライン学習(LogisticRegression)実測レポート

> 既存 v58.7 再現エンジン(`backend/app/prediction/engine.py`)とは**完全独立**の新規データ駆動システム。
> 本番 Supabase は **SELECT のみ**・書込なし。engine.py 不変更。
> 実行スクリプト: `scripts/dot/train_baseline.py`(読取専用)。実測日: 2026-06-15。

## 1. データ(INNER JOIN: date+venue+race_no)

| 指標 | 実数 |
|---|---:|
| 学習可能レース | **454**(step-1-7時点430から増加。DB成長分) |
| 艇行数 | **2724**(=454×6) |
| 月別 | 2026-05 = 48R / 2026-06 = 406R |

## 2. 特徴量(リーク防止済み・43列)

- ベース: `lane, age, weight, f_count, avg_st, today_st, exhibition_st, standard_st, course1y_st, national_*, local_*, general1y_*, local5y_*, c1〜c6_win_rate, motor_place2_rate, gen_rate, hit_rate, exhibition_time`
- **枠内相対化**(同レース6艇内): `national_win_rate / national_place2_rate / local5y_win_rate / general1y_win_rate / avg_st / motor_place2_rate / weight` の **z-score** と **順位(rank)**。
- 欠損処理: パイプライン内 `SimpleImputer(median)` → `StandardScaler`。
- **リーク防止【検証済み】**: `winner_*/place2_*/place3_*/trifecta_*/exacta_*/result_all/is_win/is_top3` をブラックリストで二重排除。特徴量リスト ∩ リーク列 = **空(OK)**。全欠損列(`odds_win` 等)は除外済み。

## 3. 分割

- **6月内 会場層化 5-fold**(レース単位split=艇行リーク防止、会場で層化)。
- 5月48レースは**常に train に合流**(薄いため検証には使わない)。

## 4. 評価結果(6月OOF 406レース・ベースラインと同一集合)

### 4-1. is_win(1着)

| モデル | LogLoss | AUC | Top1的中 | 3連単的中 | 回収率 |
|---|---:|---:|---:|---:|---:|
| **DOT LogReg(is_win)** | **0.362** | **0.798** | 52.0% | 8.1% | 78.8% |
| (1) 1号ベタ | - | - | 54.2% | 8.6% | 96.9% |
| (2) national_win_rate順 | - | - | 38.2% | 6.7% | 135.7% |

### 4-2. is_top3(3着内)

| モデル | LogLoss | AUC | Top1的中 | 3連単的中 | 回収率 |
|---|---:|---:|---:|---:|---:|
| **DOT LogReg(is_top3)** | **0.591** | **0.749** | 48.0% | 8.9% | 107.6% |
| (1) 1号ベタ | - | - | 54.2% | 8.6% | 96.9% |
| (2) national_win_rate順 | - | - | 38.2% | 6.7% | 135.7% |

- **回収率の定義**: 各レースでスコア上位3艇をその順で3連単1点買い(100円)、実 `trifecta_result` と完全一致した時のみ `trifecta_payout` を回収。リーク無し・検証可能な実弾ベース。1号ベタ/national順も同一ルールで比較。

## 5. 所見

- **AUC=0.80(is_win)** と明確な識別力。LogLoss=0.362 も良好。**LogRegベースラインは実データで学習・評価が成立**。
- Top1的中は 1号ベタ(54.2%)に僅差で届かず(52.0%)。1号頭が極端に強い競艇で、線形モデルが1号を過信せず分散させた結果。AUC優位だが「頭1点」では1号ベタが強い。
- national_win_rate順は的中率が低い(38.2%)が、人気薄が稀に的中し回収率だけ跳ねる(高分散)。少標本(406R)では回収率は不安定で参考値。
- **次フェーズ(LightGBM)で改善見込み**: `general1y_*`(カバレッジ22%)等の欠損に強く、非線形・相互作用を拾える。今回 LogReg は median 補完で情報損失あり。

## 6. ACCEPT 確認

- [x] LogReg が実データ454レースで学習・評価でき、AUC/LogLoss/的中率/回収率が数値で出る。
- [x] 1号ベタ・national_win_rate順ベースラインと比較表が出る。
- [x] engine.py・本番DB不変更(学習は SELECT のみ・`insert/update/upsert/delete` 不使用を検証)。
- [x] リーク防止確認(特徴量リストに結果系列なし=自動検証 leak_free:true)。

## 7. 成果物

- `scripts/dot/train_baseline.py` — 学習パイプライン(取得→特徴整形→学習→評価、読取専用)
- `tmp/dot_baseline.json` — 評価結果の実測JSON
- 本レポート
