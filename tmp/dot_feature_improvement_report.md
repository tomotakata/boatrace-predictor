# DOTレーティング本命(LightGBM)特徴量追加 改善レポート

対象スクリプト: `scripts/dot/train_lightgbm.py` / `train_baseline.py` / `selective_voting.py` / `bet_strategy.py` / `feature_coverage.py`(新規)
データ: 全期間 **4594R**(2026-04=2570 / 05=623 / 06=1401・欠損0)。train=4+5月(3193R)、test/OOF=6月(**1401R**)。
リーク防止: `train_lightgbm.TRAIN_MONTHS={04,05}` / `TEST_MONTH=06` を単一の真実として全経路が参照。test月をtrainに混入させない(排他確認=OK)。本番DBは SELECT のみ。

---

## 1. 現状特徴量セットの棚卸し

### 1-1. 現在モデルが使う特徴(43列)
`BASE_FEATURES`(29 raw)+ `RELATIVE_FEATURES` の枠内 z/rank 派生(7特徴×2=14列)。各艇の**当日1スナップショット**のみ。

- BASE(29): `lane, age, weight, f_count, avg_st, today_st, exhibition_st, standard_st, course1y_st, national_win_rate, national_place2_rate, local_win_rate, local_place2_rate, general1y_win_rate, general1y_place2_rate, general1y_tricast_rate, local5y_win_rate, local5y_place2_rate, local5y_tricast_rate, c1_win_rate..c6_win_rate, motor_place2_rate, gen_rate, hit_rate, exhibition_time`
- 相対派生(z/rank): `national_win_rate, national_place2_rate, local5y_win_rate, general1y_win_rate, avg_st, motor_place2_rate, weight`

### 1-2. ベースライン確定値(本レポートで再実行・OOF=1401R / holdout valid=1401R)
| 目的 | OOF Top1 | CV AUC | holdout Top1 | holdout AUC |
|---|---|---|---|---|
| is_win | **55.03%** | **0.8334** | 54.96% | 0.8285 |
| is_top3 | 54.18% | 0.7652 | 53.75% | 0.7583 |

(1号ベタ 53.9% 超を維持。)

---

## 2. 追加候補のカバレッジ評価(`tmp/dot_feature_coverage.json`)

`feature_coverage.py` で『DB実在だが未使用の列』の月別非欠損率を計測。プラン基準 **全月(4/5/6)≥30%** で一次選別。

### 2-1. 一次採用(全月≥30%)
- `players.rank`(級別 A1/A2/B1/B2): **100%**
- `is_local`(当地選手フラグ): 100%
- `c{n}_nige/sashi/makuri/makurizashi`, `local5y_sashi/makuri/makurizashi`: 生列は100%

### 2-2. 不採用(構造的に学習不能・train月0%)
気象(`weather/wind_speed/wind_direction/water_temperature/wave_height/temperature`), `general1y_*`, `escape1y_*`, `today_st_rank/course1y_st_rank/st_advantage_rank`, `motor_dashfoot/extfoot(_score)`, `motor_eval/motor_rank_*`, `c{n}_place2_rate/c{n}_tricast_rate`, `nigiri_rate`, `tide_*` 等は **train月(4/5)で0%**、6月のみ ~3〜10%。trainが全欠損のため学習不能 → 取得対象から除外。`players.win_rate/place_rate_*/birth_place` は全欠損。

> リスク所見(正直な前提): 本データは2026年4〜6月の限定期間で、上記「リッチな」列の多くは6月の一部レースにしか存在せず、過去から積み上げる時系列集計(G6)も母数不足で有効化できないと判断し、今回は静的列のみに絞った。

---

## 3. 実装した追加特徴グループとリーク防止

`build_features(include_extra=True)` でグループ化(全て**レース前確定の選手/機材属性**のみ。固定辞書エンコード・枠内相対のためデータ依存統計やtest情報を一切使わず構造的にリーク無し)。

| グループ | 内容 | 列数 |
|---|---|---|
| g1_rank | 級別を順序エンコード(A1=4..B2=1) `rank_ord` + 枠内 z/rank | 3 |
| g2_kimarite | 自進入コース決まり手比率(逃げ/攻め/差し)+ 当地5年攻め比率 + 決まり手母数 | 6 |
| g3_islocal | `is_local` | 1 |
| g4_st_rel | `today_st/exhibition_st/course1y_st` の枠内 z/rank | 6 |

- リーク列混入チェック=**OK**(結果系列なし)/ allowlist検証=**OK**(許可特徴のみ)/ train・test月排他=**OK**。`leak_free=true`。

### 3-1. 実効カバレッジの重大所見(過大評価回避のための検証)
生列は100%でも、**艇ごとの「自分の進入コースの決まり手比率」やST相対は実効カバレッジが極端に低い**ことを実データで確認:

| 特徴 | 実効非欠損率 | 備考 |
|---|---|---|
| `rank_ord`(g1) | **100%** | 唯一しっかり埋まる実信号 |
| `rank_ord_z` | 90.7% | |
| `course_*_ratio`(g2) | **3.1%** | 自コースの`c{lane}_*`はほぼ欠損(他コースのc{n}が埋まっているだけ) |
| `local5y_aggr_ratio`(g2) | 0.7% | |
| `is_local`(g3) | nunique=**1**(定数) | 情報量ゼロ |
| `today/exhibition/course1y_st 相対`(g4) | 2〜3.5% | ST生列がほぼ欠損 |

→ **実質的に機能するのは G1(級別)のみ。** g2/g3/g4 は実効ほぼ空で、ablationの微小差はノイズ域。

---

## 4. before/after + ablation(標本数明記)

`python3 scripts/dot/train_lightgbm.py --ablation`(OOF=5fold会場層化, OOF/holdout valid=**1401R**)。`tmp/dot_lightgbm_v2.json`。

### 4-1. is_win(主軸)
| 構成 | feats | OOF Top1 | CV AUC | holdout Top1 | holdout AUC |
|---|---|---|---|---|---|
| baseline | 43 | 55.03% | 0.8334 | 54.96% | 0.8285 |
| +g1_rank | 46 | **55.32%(+0.29pt)** | **0.8352(+0.0019)** | 54.75% | 0.8307(+0.0022) |
| +g2_kimarite | 49 | 55.03%(±0) | 0.8334(+3e-5) | 54.96% | 0.8285 |
| +g3_islocal | 44 | 55.03%(±0) | 0.8334(±0) | 54.96% | 0.8285 |
| +g4_st_rel | 49 | 55.10%(+0.07pt) | 0.8335(+1e-4) | 54.96% | 0.8285 |
| **full(全追加)** | 59 | **55.60%(+0.57pt)** | **0.8342(+0.0008)** | 54.75% | 0.8307(+0.0022) |

### 4-2. is_top3(副次)
| 構成 | feats | OOF Top1 | CV AUC | holdout Top1 | holdout AUC |
|---|---|---|---|---|---|
| baseline | 43 | 54.18% | 0.7652 | 53.75% | 0.7583 |
| +g1_rank | 46 | 53.96%(-0.21pt) | 0.7658(+0.0006) | 54.25% | 0.7613 |
| +g2_kimarite | 49 | 54.39%(+0.21pt) | 0.7650(-0.0003) | 53.75% | 0.7583 |
| +g4_st_rel | 49 | 54.25%(+0.07pt) | 0.7653(+7e-5) | 53.75% | 0.7583 |
| full | 59 | 53.96% | 0.7649 | 54.25% | 0.7613 |

---

## 5. 採用 / 不採用の判断(DoD: Top1かAUCが改善し両方悪化なし)

| グループ | is_win判定 | 根拠(標本数=OOF 1401R) |
|---|---|---|
| **g1_rank** | **採用** | OOF Top1 +0.29pt かつ CV AUC +0.0019、holdout AUC も +0.0022。実効カバレッジ100%で実信号。 |
| g4_st_rel | 不採用(実質) | OOF AUC +1e-4・Top1 +0.07pt は微差で、実効カバレッジ2〜3%。改善はノイズ域と判断し本採用しない。 |
| g2_kimarite | 不採用 | is_winでΔ≈0。実効カバレッジ3.1%で自コース決まり手がほぼ取得できず機能しない。 |
| g3_islocal | 不採用 | 列が定数(nunique=1)で情報量ゼロ。 |

**結論(本命is_win)**: 実装・検証の結果、**級別(rank, G1)のみが現実的に有効**。他3グループは現データの実効カバレッジ不足で効果なし → 不採用。is_top3 では g1 が Top1 を僅かに下げる(-0.21pt)ため、本命優先方針に従い G1 は is_win 用として位置づける。

> 推奨運用構成: **baseline 43列 + g1_rank(=46列)**。fullの+0.57ptは空特徴を多数含むため過剰。G1単体の +0.29pt / AUC+0.0019 を採用水準とする。

---

## 6. 選択的投票ROIへの波及(8seed robustness・標本数明記)

`selective_voting.py`(baseline vs `--extra`)。test=**479R**、各seedで別fold割当のOOF→同一の時系列train/test手順。`tmp/dot_selective_base.json` / `tmp/dot_selective_extra.json`。

代表コンボ `I_PL上位3点3連単 × neg_entropy`(実購入=median **約85〜87R/479R**):

| | ROI min | ROI median | ROI max | >100%割合 |
|---|---|---|---|---|
| BASE(43列) | 66.9% | 79.3% | 91.0% | 0/8 |
| EXTRA(59列) | **86.7%** | **99.8%** | 111.8% | 4/8 |

- 全16コンボ中ほぼ全てで ROI 分布が**上方シフト+下側(min)安定化**。ただし**中央値が控除率(ROI100%)を安定して超えるコンボは依然なし**(frac_over_100=0.5 が最高で、複数seedでは100%割れ)。
- 過大評価回避: 購入数 median ≈85R(test 479R中)と小標本。max 111.8% 等の上振れは標本分散であり結論にしない。**実利は「分散下側の安定化」水準**であり、ROI>100%の安定確保には至らない、という現実水準で報告する。
- 注: `--extra` は full(空特徴含む59列)で実行。OOF AUC改善の主因は G1(rank)。

---

## 7. 受入基準の充足

- [x] 現状特徴量(43列)の棚卸し(§1)+ DB未使用列の列挙(§2)
- [x] 追加候補をリーク評価付きで提示(§2-2 不採用理由・§3 リーク防止)
- [x] 時系列リーク防止の担保(TRAIN/TEST月排他・固定辞書エンコード・allowlist/blacklist検証OK・`leak_free=true`)
- [x] before/after + ablation を標本数明記(OOF/holdout=1401R)で提示、採用/不採用根拠明確(§4-5)
- [x] 選択投票ROIの min/median を標本数(test 479R・購入 ~85R)付きで再測、過大評価回避(§6)

## 8. 成果物
- `tmp/dot_feature_coverage.json` — 候補列カバレッジ
- `tmp/dot_lightgbm_v2.json` — before/after + ablation(全グループ・両目的)
- `tmp/dot_selective_base.json` / `tmp/dot_selective_extra.json` — ROI robustness(8seed)
- 本レポート `tmp/dot_feature_improvement_report.md`
