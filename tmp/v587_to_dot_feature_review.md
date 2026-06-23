# v58.7 決定論ルール仕様 → DOT(LightGBM) 特徴量移植 解析レポート

> 解析のみ。engine.py / 本番DB は不変更(SELECT のみ実測)。
> 計測コード: `tmp/v587_engine_input_coverage.py` / 出力: `tmp/v587_engine_input_coverage.json`
> 既存実測: `tmp/dot_feature_coverage.json`(4594R) / 前回レポート: `tmp/dot_feature_improvement_report.md`

---

## 0. 結論(先に)

**「使えるが、ほぼ伸びない」。** v58.7 の決定論指標群は良質なドメイン知識だが、その**計算入力の大半が DOT の学習期間(2026-04/05)で実効カバレッジ 0%** であり、LightGBM の特徴量に移植しても**train で学習できない**。前回 G2/G3/G4 が頭打ちした原因とまったく同じ「列はあるが train が空」の壁に、v58.7 指標もそのまま衝突する。

- **唯一そのまま効くのは級別(rank, D-KAN成分⑤・EI成分H)= 既に G1_rank として採用済み**。v58.7 由来で新規に追加して効果が見込めるのは**「rank由来の合成指標」程度**。
- `gen_rate`/`hit_rate` は `boats` に列があり非欠損率 100% に見えるが、**train月は全行ゼロ(nunique=1)**で `is_local` と同じ情報量ゼロの罠。
- EI/TI/逃げ成立度/握り発生率/着内確率/2着期待 などの**合成指標は、engine.py に実装はあるが、その入力(`c{n}_win_rate`・`season_st`・`deashi/nobashi`・`nigiri_*`)が train で取れないため移植不可**。

DOT の頭打ち(Top1 ~55.6% / AUC 0.834)を、v58.7 仕様の流用で打破できる見込みは**低い**。本質的な制約はアルゴリズムではなく**データ(4-5月のリッチ列欠損)**側にある。

---

## 1. v58.7 決定論指標の棚卸しと engine.py 実装状況

| # | 指標 | engine.py 実装 | 実装の実態(spec原文との差) |
|---|---|---|---|
| 1 | EI(期待指数) | `_compute_ei` (engine.py:491) | **spec の A-H 8成分版ではなく簡略版**。実コードは `p1_raw*100*(motor/3+0.3)*st_factor`。spec の「重み付き合成(A:コース別3連率…H:級)」は**未実装**。 |
| 2 | TI指数 | `b.ti = b.p1_raw` (engine.py:454) | spec の P1×P2連鎖版ではなく、p1_raw を代入しているだけ。 |
| 3 | P1(1着確率) | `_run02` 正規化 (engine.py:557-601) | コース別1着率→ΣP1=1正規化+逃げ成立度較正。実装あり。 |
| 4 | 逃げ成立度 | `_run02` cal_r/factor (engine.py:566-593) | 当節較正(R<P0で減衰)として実装。spec の ap_nig/ba 分解版ではない。 |
| 5 | 握り率/握り発生率 | 入力 `nigiri_rate` を消費のみ | engine内で再計算せず DB値をそのまま使用。 |
| 6 | 着内確率(place_prob) | 該当メソッドなし | engine.py には spec の place_prob 計算は**ない**(買い目側の `_trifecta_p` 等で代替)。 |
| 7 | 2着期待(second_expect) | `_second_base` (engine.py 周辺) | 買い目生成用の2着基礎値として実装。 |
| 8 | 基準ST/優勢順位D/モーターrank | `_st_value`/motor_order (engine.py:475-483) | ST正本・モーター2連率順・EI順は実装。優勢順位D(SCORE_MAP)は簡略版。 |
| 9 | 捲り完遂力差g(makuri_g) | 明示メソッドなし | spec の対1号差 g は engine では D-KAN④/attack_type に吸収。 |
| 10 | D-KAN(完遂力5項目) | `_completion_power` (engine.py:527-548) | **spec通りに実装**。motor/ei/st/attack/class の5項目を 0-5 でカウント。 |
| 11 | 攻撃型(差/捲/捲差) | `_run01_read` 内 (engine.py:457-466) | sashi/makuri/makurizashi 比較で実装。 |

**所見**: 「全計算式 MD」は v58.7 の**設計仕様**であって、現行 engine.py は EI/TI を大幅簡略化した近似実装。spec の重み付きEI(A-H)や P2連鎖TIは**コードとして存在しない**ため、「engine.py の実装を再利用して特徴量化」できるのは D-KAN・attack_type・簡略EI・ST/motor順位程度に限られる。

---

## 2. 移植可否判定(実測カバレッジ付き)

カバレッジは学習可能サンプル(6艇×完全結果, 27564艇行/4594R)に対する実効非欠損率。**判定基準は前回同様「train月(04/05)が非ゼロ かつ 情報量あり」**。

| v58.7指標 | 必要入力(V-4/DB列) | 実効カバレッジ(04 / 05 / 06) | engine実装 | リーク | 移植可否 |
|---|---|---|---|---|---|
| 級別(EI-H/D-KAN⑤) | `players.rank` | **100% / 100% / 100%** | あり | なし(固定辞書) | **○ 既採用(G1)** |
| 攻撃型(差/捲/捲差) | `c{n}_nige/sashi/makuri/makurizashi`(整数) | **100% / 100% / 100%**(生列) | あり | なし | **△ 条件付き**(下記) |
| EI成分A/TI/逃げ(フォールバック) | `c{n}_win_rate`(自コース) | **0% / 0% / 10.5%** | あり(簡略) | なし | **✕ train空** |
| ST優勢/基準ST | `today_st`/`course1y_st`/`season_st` | today 0/0/11.4%・course1y 0/0/6.9%・season **0/0/0** | あり | なし | **✕ train空** |
| EI成分F(出足/伸び) | `deashi` / `nobashi` | **0% / 0% / 0%** | (入力前提) | なし | **✕ 全欠損** |
| 握り率/発生率 | `nigiri_rate` / `nigiri_occurrence` | **0% / 0% / 0%**(両方) | 消費のみ | なし | **✕ 全欠損** |
| 攻め発生率/被弾率 | `gen_rate` / `hit_rate` | **100% / 100% / 100%**(列) | あり | **要注意** | **✕ 情報量ゼロ**(下記) |
| 着内/2着期待/EI(2連率成分) | `c{n}_place2_rate` / `c{n}_tricast_rate` | **0% / 0% / 10.5%** | 一部 | なし | **✕ train空** |
| 進入コース起点(P2被弾) | `entry_course` / `racer_courses.others` | entry_course **0% / 0% / 0.9%** | あり | なし | **✕ ほぼ全欠損** |
| 展示補正 | `exhibition_time` / `exhibition_st` | 0/1.8/7.8% ・ 0/0/7.8% | あり | なし | **✕ train空** |

### 2-1. `gen_rate`/`hit_rate` の罠(重要)
列の非欠損率は 100% だが、**train月は全行が 0(nunique=1, zero率 100%)**、6月のみ非ゼロ(zero率 95-99%)。

```
gen_rate  2026-04: nunique=1 zero率=100.0%   2026-06: nunique=224 zero率=95.2%
hit_rate  2026-04: nunique=1 zero率=100.0%   2026-06: nunique= 55 zero率=99.1%
```

→ train(4/5月)で分散ゼロ=学習不能。6月だけに信号があるため、有効化すると **test期間固有情報への依存=実質リーク的**になり、汎化しない。`is_local`(nunique=1)と同じ不採用カテゴリ。

### 2-2. 攻撃型(△条件付き)の実態
`c{n}_nige/sashi/makuri/makurizashi` の**整数カウント列は 100%** だが、engine は「**進入コース(course)の決まり手だけ**」を集計(`engine.py:1768`)。DOT には entry_course が無い(0.9%)ため**lane=course と仮定**するしかなく、前回 G2_kimarite で「自コース決まり手比率=実効3.1%」と判明した経路と同じ。整数カウントから比率を作る場合は**全コース合算の選手攻め傾向**に縮退する(=既存 `local5y_*` 由来 G2 とほぼ同義で、前回 Δ≈0)。

### 2-3. リーク評価(全体)
- 級別・決まり手カウント・ST等はすべて**レース前確定値**でリークなし(spec注記でも build_dashboard はレース前情報)。
- 唯一の懸念は **`gen_rate`/`hit_rate`**: 名称は「発生率/被弾率」だが、engine 内では結果ではなくスクレイピング/導出のレース前値。ただし**train全ゼロ・6月のみ非ゼロという分布**が、実運用上 test期間バイアスを生むため、リークに準じる扱いで除外が妥当。

---

## 3. 優先移植候補(カバレッジ十分 & 実装再利用可 & リークなし)

| 優先 | 候補 | 入力 | カバレッジ | 期待効果 | 根拠 |
|---|---|---|---|---|---|
| **P1** | 級別由来の合成(rank×枠の交互作用、rank gap to 1号) | `players.rank`(100%)+`lane` | 100% | 小(+0〜0.2pt) | G1単体が既に+0.29pt。交互作用で僅かに上積みの可能性。 |
| **P2** | D-KAN風スコア(rank∈A1A2 + 簡略EI順位 + ST順位)の**train内で作れる部分集合** | rank(100%)+`national_win_rate`/`avg_st`(既存100%列) | 100% | 小 | engine `_completion_power` のロジックを、**train で取れる成分だけ**で再構成(motor_eval除く)。 |
| P3 | 攻撃型(全コース合算の攻め比率) | `c{n}_makuri/makurizashi/sashi`(100%) | 100%(ただし lane近似) | ほぼ0 | 前回 G2 で Δ≈0 実証済み。再挑戦の価値は低い。 |
| ✕ | EI/TI/逃げ成立度/着内/2着期待 | `c{n}_win_rate`等 | train 0% | 不能 | train で計算不能。 |

**実質的に新規で試す価値があるのは P1/P2 のみ**(どちらも既存 G1 の延長で、級別+既存100%列の合成)。v58.7 の「リッチな合成指標」本体(EI A-H, TI連鎖, 逃げ成立度分解, P2被弾)は **train データが無い以上、移植しても評価すらできない**。

---

## 4. 正直なレビュー

### 使える点
- v58.7 の **D-KAN / EI の "順位ベース合成" という設計思想**は、生カラムの z/rank 化(DOT が既に採用)と同方向で、ドメイン的に正しい。級別(G1)が効いたのはこの思想の部分的成功例。
- engine.py の `_completion_power`・`attack_type`・簡略EI は、**train で取れる入力(rank, national_win_rate, avg_st)だけ**に絞れば、リークなしで特徴量関数として再利用できる。

### 使えない点・限界(率直に)
1. **データ制約が支配的**。EI(A-H)・TI・逃げ成立度・握り発生率・着内確率・2着期待・P2被弾は、いずれも `c{n}_win_rate`/`c{n}_place2_rate`/`season_st`/`deashi`/`nobashi`/`nigiri_*`/`racer_courses.others` を必要とし、**これらは 4/5月で 0%**。移植は机上では可能だが、**LightGBM は train で見たことのない特徴を学習できない**ため無意味。
2. **`gen_rate`/`hit_rate` は見かけ100%の罠**(train全ゼロ)。「使える列が増えた」と誤認しやすいので明示的に除外すべき。
3. **買い目生成指標を勝率予測特徴に流用する妥当性**: EI/D-KAN等は**順位・ゲート判定用に設計**された量で、確率較正されていない(EIは簡略式、TIはp1_raw代入)。これを LightGBM の特徴に入れても、モデルは結局その**素の入力(コース別勝率・ST・級別)**を直接使う方が情報損失が少ない。**合成指標は素特徴の非線形変換に過ぎず、勾配ブースティングは元々それを学習できる**ため、合成済み指標を足しても上積みは小さい(前回 full +0.57pt の主因は G1 のみ、という結果と整合)。
4. **頭打ちの本質**: Top1 55.6% / AUC 0.834 の壁は、特徴量設計ではなく **「4-5月にリッチ列が無い」=情報そのものの不足**。v58.7 仕様を流用しても情報量は増えない。

### コスト/リスク
- コスト: P1/P2 の実装+ablation は小(既存 `_build_extra_features` に1グループ追加=半日相当)。
- リスク: ほぼなし(SELECTのみ・固定辞書エンコード)。ただし**「効果が出る」期待値は低い**ことを前提に。
- 最大リスク: `gen_rate`/`hit_rate` を安易に採用→6月のみ信号で OOF が見かけ改善→実運用で崩れる**過学習/疑似リーク**。

---

## 5. 具体的実装プラン(解析→検証、実装は未着手)

### 5-1. 追加する特徴グループ(train で 100% 取れる入力のみ)
`scripts/dot/train_baseline.py::_build_extra_features` に v58.7 思想由来の2グループを追加(関数追加のみ、既存ロジック不変更):

- **g5_dkan_lite**(D-KANの train可能部分集合 / engine `_completion_power` 移植)
  - 成分①(motor): `motor_place2_rate`(既存100%列)の枠内順位 ≤2 → 0/1
  - 成分②(ei順位): 簡略EI = `national_win_rate * st_factor(avg_st)` の枠内順位 ≤3 → 0/1(engine `_compute_ei` の motor項を train欠損のため national で代替)
  - 成分③(st順位): `avg_st` 昇順順位 ≤3 → 0/1
  - 成分④(attack): `c{lane}_makuri + c{lane}_makurizashi > 0` → 0/1(整数列100%、lane近似)
  - 成分⑤(class): `rank ∈ {A1,A2}` → 0/1
  - 出力: `dkan_lite`(0-5 合計) + 枠内 `dkan_lite_rank`
- **g6_rank_inter**(級別×枠 交互作用 / EI-H思想)
  - `rank_ord * (7 - lane)`(インほど級が効く交互作用)、`rank_gap_to_lane1 = rank_ord(self) - rank_ord(lane1)`

> いずれも **train(4/5月)100%カバレッジの入力のみ**で構成。`gen_rate/hit_rate/season_st/deashi/nobashi/c{n}_win_rate/nigiri_*` は使わない(train欠損のため)。

### 5-2. リーク防止
- 既存の `LEAK_BLACKLIST` / allowlist 検証を流用。新規列は全て fit前確定の選手・機材属性 + 枠内相対のみ。
- TRAIN_MONTHS={04,05}/TEST=06 の排他を継承。`leak_free` フラグで確認。

### 5-3. ablation 検証計画(前回と同一プロトコルで apples-to-apples)
```
python3 scripts/dot/train_lightgbm.py --ablation
```
- 分割: 6月内 会場層化 5-fold OOF(=1401R)+ holdout valid(1401R)、5月は常にtrain合流。
- 比較構成: `baseline(43)` / `+g1_rank(既採用)` / `+g5_dkan_lite` / `+g6_rank_inter` / `+g5+g6`。
- 指標: is_win の **OOF Top1 / CV AUC / holdout Top1 / holdout AUC**(両目的 is_win/is_top3 を出力)。
- **採用基準(DoD)**: 前回踏襲 — 「Top1 か AUC が改善、かつ両方悪化なし」。実効カバレッジ100%なので**ノイズ域(±0.05pt)を超える改善があるか**を判定。
- 過大評価回避: 改善が `g1_rank` 単体の +0.29pt を**有意に超えない**なら「v58.7 流用の上積みなし」と正直に結論。
- 追加で **selective_voting.py --extra 相当**で ROI 分布(8seed, test 479R)の下側安定化に寄与するかを確認(中央値>100%は期待しない前提)。

### 5-4. 期待される結論(正直な事前予測)
g5/g6 は train100%入力のため**ノイズ域は脱する可能性があるが、上積みは +0〜0.3pt 程度**。理由は §4-3(勾配ブースティングは素特徴から同等情報を既に学習)。**「v58.7 仕様で頭打ち打破」は期待しない**のが誠実な見立て。本質的改善には **4-5月のリッチ列バックフィル(`c{n}_win_rate`/ST/決まり手rate/`racer_courses.others`)= データ収集側の対応**が必要、というのが最終所見。

---

## 6. 受入基準の充足

- [x] 各指標の移植可否を**実測カバレッジ付き**で判定(§2、`tmp/v587_engine_input_coverage.json`・`tmp/dot_feature_coverage.json`)
- [x] engine.py 実装の再利用可否を確認(§1、行番号付き)
- [x] リーク評価(§2-3、特に gen_rate/hit_rate の疑似リーク)
- [x] 正直なレビュー: 使える/使えない/限界(§0・§4)
- [x] 具体的実装プラン + ablation 検証計画(§5)
- [x] 実装せず解析+プラン提示まで。本番DB/engine.py 不変更(SELECTのみ)
