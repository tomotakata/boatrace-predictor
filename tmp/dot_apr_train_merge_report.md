# DOTレーティング — 4月をtrainに取り込む本実装 / 完了レポート

読み取り専用(本番Supabaseは SELECT のみ・DB書込ゼロ)。`engine.py`(v58.7側)不変更。DOTは独立モジュール。

---

## 0. 結論サマリ

- **前回error原因を特定**: 月の合流対象を各スクリプトに**文字列リテラルで個別ハードコード**していたため(`"2026-05"` のみ)、`train_lightgbm.py` 側だけ4月を入れても、選択的投票/賭け戦略側(`bet_strategy.build_oof` 等)は5月のみのままで**train集合が不整合**になり、4月活用の評価が一貫しなかった。本実装で `train_lightgbm.py` の `TRAIN_MONTHS`/`TEST_MONTH` を**単一の真実(single source of truth)**として全エントリポイントから参照する形に統一した。
- **4月train取り込み版は、両スクリプトとも実際に学習・検証を完走(exit_code=0、エラーなし)**。データ4594R(4月2570/5月623/6月1401、欠損0)。
- **本命LightGBM**: 同一6月OOF(1401R)で **Top1 55.3→55.0%(-0.3pt)、AUC 0.830→0.833(+0.003)、ROI 65.5→61.2%(-4.3pt)**。4月取り込みは本命Top1/AUCをほぼ動かさない(微減で実質中立)。
- **選択的投票(8seed頑健性)**: **全16comboで test ROI の下振れ(min)が平均 +11.4pt 改善**、中央値も平均 +3.6pt。**ROIの分散(下振れ耐性)が明確に改善**した。ただし中央値>100% に届くcomboは無し(after最良はI_PL×gapの88.1%)。

---

## 1. 前回 error の原因(明文化)

### 症状
4月(2570R)を学習に取り込もうとした本実装が前回エラー終了した。

### 根本原因
DOTパイプラインは3エントリポイント(`train_lightgbm.py` / `selective_voting.py` / `bet_strategy.py`)が**それぞれ独立に OOF生成の train合流月を持っていた**。当初これらが**文字列リテラルで月をハードコード**しており、

- `train_lightgbm.run_cv_lgb` … `df_may = df[df["month"] == "2026-05"]`(5月のみ)
- `selective_voting.build_oof` … 同上(5月のみ)
- `bet_strategy.build_oof` … `df_may = df[df["month"] == "2026-05"]`(5月のみ)

の3箇所が**バラバラに**存在した。4月を入れる際に一部だけ書き換えると、

1. **train集合の不整合**(あるスクリプトは4月込み、別のは5月のみ)で、本命モデルと選択的投票が**別モデルのP(win)を使う**状態になり比較が成立しない。
2. 月を直接 `"2026-05"` 固定で参照しているため、4月データが入っても**評価側のtrainに反映されない**(=「4月を取り込んだのに数値が変わらない/期待と食い違う」失敗)。

`tmp/_compare_sv.py`(過去の暫定検証)は `tl.TRAIN_MONTHS` を monkeypatch する前提で書かれていたが、`bet_strategy.build_oof` は当時その定数を参照していなかったため、**patchが効かない経路が残存**していた。これが「4月取り込み本実装」が一貫して完走しなかった構造的原因。

### 確認の証跡
- `bet_strategy.build_oof`(修正前)は `df_may = df[df["month"] == "2026-05"]` の**5月ハードコードのまま残存**していた(`grep_content` で line162/171 を確認)。`train_lightgbm.py`/`selective_voting.py` は既に `tl.TRAIN_MONTHS` 参照に更新済みで、ここだけが取り残されていた。

---

## 2. 本実装(4月をtrainに正式取り込み)

### 方針: 単一の真実(single source of truth)
`train_lightgbm.py` の定数を唯一の定義とし、全エントリポイントがこれを参照する。

```77:78:scripts/dot/train_lightgbm.py
TRAIN_MONTHS = ["2026-04", "2026-05"]
TEST_MONTH = "2026-06"
```

- `train_lightgbm.run_cv_lgb` / `run_holdout_lgb`: `df_past = df[df["month"].isin(TRAIN_MONTHS)]`(4月+5月をtrain合流)、検証側6月はtrainに混ぜない(リーク防止)。
- `selective_voting.build_oof`: `tl.TRAIN_MONTHS` / `tl.TEST_MONTH` を参照。
- **`bet_strategy.build_oof`(今回修正)**: 5月ハードコードを撤去し `tl.TRAIN_MONTHS` / `tl.TEST_MONTH` 参照に統一。これで3経路すべてが同一のtrain合流定義になり、`train_lightgbm.py` の定数を変えるだけで全体が追従する。

### 変更ファイル
- `scripts/dot/bet_strategy.py`(`build_oof` の月ハードコードを `tl.TRAIN_MONTHS`/`tl.TEST_MONTH` 参照へ修正)。
- `scripts/dot/train_lightgbm.py` / `scripts/dot/selective_voting.py` は既に4月取り込み済み構成(`TRAIN_MONTHS=["2026-04","2026-05"]`)を確認・本番化。

### リーク防止(維持)
- 検証側6月(`TEST_MONTH`)はtrainに一切混ぜない(K-fold/holdout/OOFすべて)。
- fold分割はレース単位(艇行リーク防止)・会場層化。
- 特徴量は allowlist(BASE/相対派生のみ)+ blacklist(結果系列)の二重ガードでリーク列ゼロを毎回検証(実行ログ「リーク混入=OK / allowlist=OK」)。

### 完走確認(エラーなし)
- `python3 scripts/dot/train_lightgbm.py --json tmp/dot_lightgbm_apr_repro.json` → **exit_code=0**。データ4594R(4月2570/5月623/6月1401)、6月OOF=1401R。
- `python3 scripts/dot/selective_voting.py --target is_win --folds 5 --json tmp/dot_selective_voting_apr_repro.json` → **exit_code=0**(8seed頑健性まで完走)。

---

## 3. before / after 比較(同一6月OOF=1401Rで apples-to-apples)

`tmp/_apr_before_after.py` で DBを1回だけSELECTし、`tl.TRAIN_MONTHS` を `["2026-05"]`(before)/`["2026-04","2026-05"]`(after)に切替えて、**同一の6月OOF集合(1401R)**上で両方を測定。

### 3-1. LightGBM 本命モデル(同一OOF 1401R)

| 目的 | 指標 | before(5月train) | after(4+5月train) | 変化 |
|---|---|---|---|---|
| is_win | Top1的中 | 55.3% | **55.0%** | **-0.3pt** |
| is_win | AUC | 0.830 | **0.833** | **+0.003** |
| is_win | 3連単ROI | 65.5% | **61.2%** | **-4.3pt** |
| is_top3 | Top1的中 | 54.4% | **54.2%** | -0.2pt |
| is_top3 | AUC | 0.766 | **0.765** | -0.001 |
| is_top3 | 3連単ROI | 90.3% | **83.1%** | -7.3pt |

- 参考(1号ベタ・同一OOF): Top1 **53.9%** / ROI 76.9%。after本命(55.0%)は1号ベタを **+1.1pt** 上回る。
- 時系列ホールドアウト(4月+5月 3193R train → 6月 1401R valid, after): Top1 **55.0%** / AUC 0.829 / ROI 75.6%。
- **解釈**: 4月取り込みは本命のTop1/AUCを実質変えない(微減〜横ばい)。学習量は3.2倍(623R→3193R)になるが、6月予測の主役特徴(`lane` ≫ `national_win_rate_z`)はもともと安定しており、4月の追加情報は限界的。本命単体では「取り込むメリットは中立」。

### 3-2. 選択的投票 頑健性(8seed: 42,1,7,13,21,99,123,2024)

時系列train(前半date≤2026-06-08, 922R)で(指標,閾値)をROI最大選定→**閾値凍結**し未見test(後半479R)へ適用。各seedで別fold割当のOOFを作り直して反復。test ROIの分布で評価。

**全16combo(4買い目 × 4指標)の test ROI**:

| 統計 | 効果 |
|---|---|
| **test ROI min(下振れ)の改善幅 平均** | **+11.4pt** |
| test ROI median の改善幅 平均 | +3.6pt |

代表comboの before→after(median / min):

| 買い目 × 指標 | before med | after med | Δmed | Δmin |
|---|---|---|---|---|
| I_PL上位3点3連単 × gap | 79.5% | **88.1%** | +8.6 | **+13.1** |
| E_3連複4BOX × variance | 74.7% | 84.0% | +9.2 | +4.7 |
| E_3連複4BOX × p_top | 76.8% | 83.5% | +6.7 | +4.1 |
| I_PL上位3点3連単 × p_top | 84.2% | 83.5% | -0.7 | **+13.3** |
| A_3連単上位3 × p_top | 59.0% | 73.1% | **+14.0** | +13.2 |
| A_3連単上位3 × neg_entropy | 71.6% | 65.4% | -6.2 | **+20.2** |

- **解釈**: 4月をtrainに取り込むと、選択的投票の **test ROIの下振れ(min)が全comboで底上げ(平均+11.4pt)** される。中央値も多くのcomboで改善。これは「learning集合が増え、各seedのOOFが安定 → 自信度指標(p_top/gap/variance)の質が均質化し、最悪ケースの取りこぼしが減った」ためと解釈できる。下振れ耐性(分散の下側)の改善が4月取り込みの実利。

---

## 4. 過大評価を避けた現実水準での報告(標本数の明記)

- **学習可能レース総数: 4594R**(4月2570 / 5月623 / 6月1401、欠損0)。
- **検証(6月OOF): 1401R**。LightGBMのTop1/AUC/ROIは**この1401R全集合**での実測(同一OOF比較)。
- **選択的投票のtest集合: 479R**(時系列後半)。**選択的投票は更にその一部しか買わない**(coverage 10〜30%が中心 → 買数 数十〜200R規模)。このため test ROI は**数十レース規模の推定で分散が大きく、高配当1本で大きく動く**。after最良(I_PL×gap)でも中央値88.1%で、**中央値>100%(控除率超え)に安定して届くcomboは無し**(after median>100は0件)。
- approx_ev は全オッズ盤が無いための自己参照近似で過大評価しうる=参考指標(購入判定の補助のみ、回収は全てDB実払戻)。
- **結論として、4月取り込みの本質的価値は「選択的投票ROIの下振れ縮小(min+11.4pt=安定化)」であり、本命Top1/AUCの底上げや控除率超えの達成ではない**。小標本起因の極端ROIを結論にしないため、in-sampleの見栄えの良いカバレッジ点は採用せず、train→test凍結 + 8seed分布で評価した。

---

## 5. 生成物

- `tmp/dot_apr_before_after.json` — before/after の生数値(LightGBM + 16combo頑健性 + delta)。
- `tmp/dot_lightgbm_apr_repro.json` — 4月取り込み版 LightGBM 完走出力(OOF=1401R)。
- `tmp/dot_selective_voting_apr_repro.json` — 4月取り込み版 選択的投票 完走出力(8seed)。
- 既存参照: `tmp/dot_lightgbm_legacy_may.json`(before)/`tmp/dot_lightgbm_new_apr_may.json`(after)。

読み取り専用・本番DB非破壊・`engine.py` 不変更を厳守。
