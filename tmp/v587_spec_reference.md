# 競艇予想AI v58.7（Build r113-format-by-class） 買い目生成 全計算式

> 開発依頼者提供。engine.py(v58.7)の決定論ルール仕様。DOT(LightGBM)特徴量移植の参照用に保存。
> 全文は manager 会話で受領。以下は解析の起点となる「特徴量候補」の観点での要約index。
> 詳細な数式原文は会話ログ/ユーザー提供MD参照。本ファイルはタスク作業の足場。

## システム構成（重要な前提）
- dashgen_code.py: 出走データ→ダッシュボード（各艇指標）を決定論計算
- engine/v58_7_engine.py: ダッシュボード→展開ロック(run_analysis)→オッズ反映(apply_return_gate)

## DOT特徴量として移植候補になる決定論指標（第I部 build_dashboard 由来）
各艇iについて算出される指標。すべてレース前情報＝リーク懸念低い。

1. EI（期待指数, ei）/ ei_order
   - 成分A=_shrink(コース別3連率,出走数), B=_shrink(当地3連率,当地出走数), C=_shrink(一般戦3連率,一般戦出走数/無ければA),
     D=SCORE_MAP[優勢順位D-1], F=出足desc*0.45+伸びdesc*0.55, G=min(握り率*0.45+握り発生率*0.55,90)(1号0),
     H=級(A1=95/A2=75/B1=55/他 年齢≤30=45/超=40)
   - 重み EI_W={A:1.05,B:0.95,C:0.85,D:1.55,F:1.65,G:1.20,H:0.90}
   - J枠補正/K着順補正/L事故F/N当地適性/I級×枠固定/M外伸び 等の乗算・加算
2. TI指数（ti）/ ti_order: 1号=逃げ成立度*100*(P1raw/コース基準1C勝率)*min(出走/20,1); 他=Σ(P1[j]*P2[i|j])*min(出走/20,1)
3. P1（1着確率 first_prob, %）: p1raw×g×ST補正×左隣補正×mot_m×season×rnum 等→正規化
4. 逃げ成立度（nige_success_rate, 0-1, 1号のみ）: 攻め圧力ap_nig+場固有脅威ba+条件加算→clamp
5. 握り率（nigiri_rate, %）/ 握り発生率（occurrence_rate, %, 2-6号の連鎖計算）
6. 着内確率（place_prob, %, 6艇合計≒300）: w3*ability*benefit, 上流受益up
7. 2着期待（second_expect, %, 6艇合計≒100）
8. 基準ST（base_st）, 優勢順位D（advantage_order）, モーターrank（S/A/B/C/D）, rank_order
9. 捲り完遂力差g（makuri_g）: ST/モーター/級 の対1号差
10. D-KAN（完遂力5項目, RUN-04）: motor(rank∈AB or order≤2)+ei(順位≤3)+st(順位≤3)+attack(makuri>0 or makuri_sashi>0)+class(∈A1A2)、0-5
11. 攻撃型 _derive_attack_type（差/捲/捲差）

## 入力スキーマ（V-4）— DOTで取得可能か要カバレッジ確認
- entries[i]: course,frame,class,age,branch,f_count, motor.deashi/nobi,
  start.average_st/course_average_st/current_st/current_order,
  course_stats.{starts,win_rate,top2_rate,top3_rate,makuri,makuri_sashi,sashi},
  local_stats.{starts,win_rate,top3_rate}, ippan.{top3,starts}
- racer_courses[c].others[相手].{win_rate,top2_rate,sashi,makuri,makuri_sashi} ← 被弾分析/P2用。★カバレッジ要注意
- environment: weather,wind_speed_mps,wind_direction,wind_effect,wave_height_cm

## 会場別係数 VENUES（24会場）: base_wr/base_ei/base_1c_wr/k_b/mot_w/rider_max/kado/core_mult/exploit_kado/use_rnum/floor_basis/nige_floor
## 定数: CLASS_VAL={A1:4,A2:3,B1:2,B2:1}, SCORE_MAP=[100,80,60,40,20,0]
## データファイル: sujime_templates.json / benefit_map.json / venue_master.json

## 注記（V-5 落とし穴）
- P1の風波補正は未適用(build_dashboardが[1.0])。風が効くのは握り発生率のみ。
- season_motor未使用。_run07_honsen_legacy_r85はデッドコード。formula_library.jsonは計算未使用。
- 数値は会場設定/データファイルに強依存。丸め・同点タイ規則も一致必須。

> ★DOT精度改善の観点: 上記1-11の決定論指標を「特徴量」としてLightGBMに供給できれば、生カラムでは表現不能なドメイン知識を注入できる。ただし racer_courses.others 等のカバレッジが4-6月データで足りるかが鍵（前回の特徴量追加で実効カバレッジ不足の壁あり）。
