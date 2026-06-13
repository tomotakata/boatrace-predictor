"""
競艇予想AI v59.0 完全版 システム実装
PDFプロンプト「競艇予想AI v58.7 完全版」のロジックをAIプロンプトではなく
Pythonの計算式（決定論的システム）として実装したもの。

中核思想：
  買い目は「一艇の攻めから派生する一本の因果の木」の枝としてのみ生成する。
  数値ソート・独立最適化は禁止。

主要改正の実装：
  - 改正30/42  本線フォーマット固定 A(A-BCD-BCDE) / B(AB-ABCD-ABCD)
  - 改正43/47  EV歪みゲート  EV = 我々の展開確率 × オッズ
  - 改正46/48/53 逃げ成立度の当節較正＋再正規化（ΣP(1着)=1）
  - 改正49     二連単=独立世界線（(頭-2着)完全一致のみ非被り）
  - 改正44     二連単ガミ禁止（Σ(1/オッズ)<1.0）
  - 改正54     弱頭判定（A型 頭1着率<50% / B型 頭合計<50% → 勝負禁止）
  - 改正51/57  展開連動3着補正 SINK
  - 改正52/59  万舟 6〜8点抽出義務＋保険枠（EVゲート例外）
  - 改正56     ODDS_T時点ロック（オッズ取得不能なら全枝見送り）
  - 改正58     筋目分離（2差し/2捲り・4-1256・6単独大外）

RUN順:
  RUN-00 進入評価・初日判定・SINK適用可否
  RUN-01 直接読み（1着率/2着期待/逃げ成立度/⑤b/モーター/ST）
  RUN-02 D-NAMIBA + D-REGIME + 逃げ成立度較正 + 再正規化
  RUN-03b 攻めの主体A & 攻撃型の確定
  RUN-04  筋目エンジン（受益ラダー → 着順テンプレ）
  RUN-05  本線フォーマット選択 & 軸確定
  RUN-06  資金枠取り
  RUN-07  データ違和感停止
  RUN-08  EV算出 → EV歪みゲート（見送り/通常/勝負）
  RUN-09  二連単（独立世界線）＋ 万舟（6〜8点）
  RUN-10  整合チェック → 出力
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


# ═══════════════════════════════════════════════════════════
# 閾値台帳（改正57b：数値閾値はすべて記号で参照）
# ═══════════════════════════════════════════════════════════
EV_MIN = 1.15      # 採用閾値（v58.7では内部参考値のみ）
EV_BAT = 1.70      # 勝負閾値（v58.7では内部参考値のみ）
GAP = 1.6          # フォーマット/軸ギャップ閾値（倍）
DEC1 = 0.85        # 逃げ成立度減衰係数（イン弱日）
DEC2 = 0.70        # 逃げ成立度減衰係数（大荒れ日）
N_CAL = 24         # 較正最低標本（R）
SINK = 0.5         # 沈み艇3着補正係数
MANSHU_MIN_ODDS = 100.0   # 万舟=100倍以上
WEAK_HEAD_TH = 0.50       # 弱頭判定（1着率合計<50%）

# 改正60：戻り額ゲート（合成オッズ反比例配分→戻り額で見送り/通常/勝負）
PAYOUT_SKIP = 30000.0     # 戻り額≤この値→見送り
PAYOUT_BET = 50000.0      # 戻り額≥この値→勝負（間は通常）

# 改正65：発動艇認定
GEN_FIRE = 0.05           # 発生率≥5%
DKAN_FIRE = 2             # D-KAN2項目以上
HIT_HIGH = 0.40           # 被弾率⑤f：1号A型禁止/崩壊枝厚みの高被弾閾値


# ─────────────────────────────────────────
# データクラス
# ─────────────────────────────────────────

@dataclass
class BoatEntry:
    lane: int                # 枠番 1-6
    course: int              # 進入コース 1-6
    name: str = ""
    rank: str = ""           # A1/A2/B1/B2/F
    f_count: int = 0

    # 全国・コース別の率（%値想定。_prob()で0-1へ正規化）
    win_rate_1st: float = 0.0          # 全国1着率（平均点の場合あり→参考）
    win_rate_2nd: float = 0.0          # 全国2連率
    place_rate: float = 0.0            # 全国2連率（着内）

    course_win_rates: Dict[int, float] = field(default_factory=dict)     # コース別1着率
    course_place2_rates: Dict[int, float] = field(default_factory=dict)  # コース別2連率
    course_tricast_rates: Dict[int, float] = field(default_factory=dict) # コース別3連率（着内率）

    # 決まり手（⑤b）コース別カウント
    sashi: int = 0
    makuri: int = 0
    makurizashi: int = 0
    nigiri_rate: float = 0.0           # 握り率⑤c（無ければ0）

    # モーター
    motor_eval: str = ""               # A/B/C/D
    motor_place2_rate: float = 0.0

    # ST
    avg_st: float = 0.15
    today_st: float = 0.0
    season_st: float = 0.0
    standard_st: float = 0.15
    st_rank: int = 3
    exhibition_time: float = 0.0
    exhibition_st: float = 0.0

    # 当地5年
    local5y_win_rate: float = 0.0
    local5y_tricast_rate: float = 0.0

    # v58.7 新規（スクレイピング導出値）
    gen_rate: float = 0.0    # 攻め発生率（per艇・非1号フィールドで使用／0-1）
    hit_rate: float = 0.0    # 被弾率⑤f（1号評価専用：差され/捲られ落ち率／0-1）

    # P2連動（⑤g・参考/EV用）
    p2_link: Dict[int, float] = field(default_factory=dict)  # {頭号艇: P(this 2着|頭)}

    # ── 計算済み（エンジン内部）──
    p1_raw: float = 0.0      # 較正前 P(1着)
    p1: float = 0.0          # 較正・再正規化後 P(1着)  ΣP1=1
    ei: float = 0.0          # 期待指数
    ti: float = 0.0          # TI（1着確率の総合）
    attack_type: str = ""    # 差し/捲り/捲差
    completion_power: int = 0
    entry_type: str = "P0"
    is_sink: bool = False    # S4で確定した沈み候補（SINK対象）


@dataclass
class RaceInput:
    race_id: int
    venue: str
    race_no: int
    day_no: int = 1
    date: str = ""
    weather: str = ""
    wind_speed: float = 0.0
    wind_direction: str = ""
    wave_height: float = 0.0
    boats: List[BoatEntry] = field(default_factory=list)

    # オッズ（ODDS_T正本）
    odds_3t: Dict[str, float] = field(default_factory=dict)  # "1-2-3" -> 倍率
    odds_2t: Dict[str, float] = field(default_factory=dict)  # "1-2" -> 倍率
    odds_win: Dict[str, float] = field(default_factory=dict)
    odds_updated_at: str = ""

    # 逃げ成立度較正（改正46/48）: 実1号頭率R と標本数N
    cal_r: Optional[float] = None    # 同場直近2節＋当節の実1号頭率（0-1）
    cal_n: int = 0                   # 標本レース数


@dataclass
class BuyPoint:
    combo: str
    p: float        # 展開確率
    odds: float     # ODDS_T倍率（0=未取得）
    ev: float       # EV = p * odds（v58.7では内部参考値）
    grade: str      # "勝負"/"通常"/"見送り"/"保険"
    branch: str     # 筋目/世界線ラベル
    payout: float = 0.0   # 改正60：この点の戻り額（合成オッズ×投資総額）


@dataclass
class PredictionOutput:
    race_type: str = ""
    regime: str = ""              # 順当/隠れ混戦/明白混戦
    surface_type: str = ""
    s_in: str = ""
    in_win_rate: float = 0.0

    # 攻め
    main_attack_course: int = 1
    main_attack_lane: int = 1
    attack_type: str = ""         # 1逃げ/2差し/2捲り/3主体/4捲り/5単独捲り差し/6単独大外
    gen_rate: float = 0.0         # 外攻め発生率

    # フォーマット
    fmt: str = "A"                # A/B
    head_boats: List[int] = field(default_factory=list)
    head_type: str = "A"
    axis_boats: List[int] = field(default_factory=list)   # 2着軸
    hus_boats: List[int] = field(default_factory=list)    # 3着紐

    # 較正
    cal_applied: bool = False
    cal_factor: float = 1.0

    # 買い目（EVゲート後）
    honsen: List[BuyPoint] = field(default_factory=list)        # 本線
    exacta: List[BuyPoint] = field(default_factory=list)        # 二連単
    manshu: List[BuyPoint] = field(default_factory=list)        # 万舟（抽出6-8点）

    odds_available: bool = False
    race_verdict: str = "見送り"   # 見送り/通常/勝負
    weak_head: bool = False

    # v58.7 改正60：戻り額ゲート表示用
    synthetic_odds: float = 0.0    # 合成オッズ = 1/Σ(1/oddsᵢ)
    payout: float = 0.0            # 戻り額 = 合成オッズ × 投資総額
    payout_grade: str = "見送り"   # 戻り額判定（見送り/通常/勝負）

    # v58.7 改正65：発動艇認定・D-KAN
    fire_boat_lane: int = 0        # 発動艇の枠番（0=無し）
    fire_boat_gen: float = 0.0     # 発動艇の発生率
    dkan_counts: Dict[int, int] = field(default_factory=dict)  # {枠番: D-KAN充足数}

    # 予算
    budget_main: int = 14000
    budget_exacta: int = 3000
    budget_manshu: int = 3000

    confidence: float = 50.0
    wave_score: float = 30.0
    regime_dispersion: float = 0.0
    regime_hit_rate: float = 0.0
    regime_attack_density: int = 0

    notes: List[str] = field(default_factory=list)
    boat_evals: List[Dict] = field(default_factory=list)
    insufficient_boats: bool = False
    reasoning: str = ""


# ═══════════════════════════════════════════════════════════
# 定数
# ═══════════════════════════════════════════════════════════

VENUE_SURFACE_TYPE = {
    "三国": "差し", "尼崎": "差し",
    "桐生": "捲り", "戸田": "捲り", "芦屋": "捲り",
    "住之江": "標準", "びわこ": "標準", "琵琶湖": "標準",
    "大村": "標準", "唐津": "標準", "福岡": "標準",
    "宮島": "標準", "児島": "標準", "丸亀": "標準",
    "平和島": "標準", "多摩川": "標準", "浜名湖": "標準",
    "常滑": "標準", "津": "標準", "蒲郡": "標準",
    "鳴門": "標準", "高松": "標準", "下関": "標準",
    "若松": "標準", "徳山": "標準", "江戸川": "標準",
}

# 場のイン1号頭率 prior（P0）
VENUE_IN_PRIOR = {
    "住之江": 0.55, "大村": 0.62, "びわこ": 0.50, "琵琶湖": 0.50,
    "桐生": 0.45, "戸田": 0.40, "芦屋": 0.50, "三国": 0.50,
    "尼崎": 0.54, "江戸川": 0.35, "平和島": 0.50, "多摩川": 0.48,
    "浜名湖": 0.53, "常滑": 0.55, "津": 0.56, "蒲郡": 0.55,
    "宮島": 0.52, "児島": 0.52, "丸亀": 0.55, "下関": 0.56,
    "若松": 0.54, "福岡": 0.54, "唐津": 0.53, "徳山": 0.57,
    "鳴門": 0.53, "高松": 0.55,
}


# ─────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────

def _prob(x: float) -> float:
    """率を0-1の確率へ正規化（55.0→0.55, 0.55→0.55）"""
    try:
        x = float(x or 0)
    except (TypeError, ValueError):
        return 0.0
    if x < 0:
        return 0.0
    return x / 100.0 if x > 1.5 else x


def _motor_grade(motor_eval: str) -> int:
    return {"A": 3, "B": 2, "C": 1, "D": 0}.get(
        (motor_eval or "").upper()[:1], 1)


def _rank_grade(rank: str) -> int:
    return {"A1": 4, "A2": 3, "B1": 2, "B2": 1, "F": 0}.get(
        (rank or "").upper(), 1)


def _normalize(d: Dict[int, float]) -> Dict[int, float]:
    s = sum(v for v in d.values() if v > 0)
    if s <= 0:
        n = len(d)
        return {k: 1.0 / n for k in d} if n else {}
    return {k: (max(0.0, v) / s) for k, v in d.items()}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════
# メインエンジン
# ═══════════════════════════════════════════════════════════

class BoatracePredictor:
    """競艇予想AI v59.0 Pythonシステム実装"""

    def predict(self, race: RaceInput) -> PredictionOutput:
        self.race = race
        self.boats = sorted(race.boats, key=lambda b: (b.lane, b.course))
        self.out = PredictionOutput()
        self.out.notes = []
        self.benefit_ladder = []
        self.suji_templates = []

        if not self.boats:
            self.out.notes.append("艇データ欠損：予測対象が存在しないため見送り")
            self.out.race_verdict = "見送り"
            self.out.payout_grade = "見送り"
            self.out.reasoning = "艇データ欠損により予測見送り"
            return self.out

        self._normalize_boat_field()

        self._run00_entry()
        self._run01_read()
        self._run02_namiba_regime_calibration()
        self._run03b_main_attack()
        self._run04_suji()
        self._run05_format_axis()
        self._run06_budget()
        self._run07_anomaly()
        self._run08_payout_gate()
        self._run09_exacta_manshu()
        self._run10_finalize()
        return self.out

    def _normalize_boat_field(self):
        lane_map = {b.lane: b for b in self.boats if 1 <= b.lane <= 6}
        if len(lane_map) < 6:
            self.out.insufficient_boats = True
            missing = [lane for lane in range(1, 7) if lane not in lane_map]
            self.out.notes.append(
                f"艇不足：{len(lane_map)}艇のみ取得（欠番 {missing}）→不足艇を安全なダミーで補完")
            for lane in missing:
                lane_map[lane] = BoatEntry(
                    lane=lane,
                    course=lane,
                    name=f"欠番{lane}",
                    rank="B2",
                    avg_st=0.25,
                    standard_st=0.25,
                )
        self.boats = [lane_map[lane] for lane in range(1, 7)]
        seen_courses = set()
        for b in self.boats:
            if not 1 <= b.course <= 6 or b.course in seen_courses:
                b.course = b.lane
            seen_courses.add(b.course)

    def _recompute_attack_rates(self):
        attackers = [b for b in self.boats if b.course >= 2]
        total_attack = 0.0
        for b in attackers:
            attack_score = _prob(b.course_win_rates.get(b.course, 0))
            attack_score += _prob(b.course_place2_rates.get(b.course, 0)) * 0.35
            attack_score += min(0.25, max(0.0, b.ei) / 100.0) * 0.25
            attack_score += min(0.20, b.completion_power * 0.03)
            b.gen_rate = max(b.gen_rate, attack_score)
            total_attack += max(0.0, b.gen_rate)
        if total_attack > 0:
            for b in attackers:
                b.gen_rate = max(0.0, b.gen_rate) / total_attack

        boat1 = self._boat_by_course(1)
        if boat1 is not None:
            hit_base = 1.0 - boat1.p1
            inside_pressure = sum(
                max(0.0, b.gen_rate) for b in attackers if b.course in (2, 3, 4)
            )
            boat1.hit_rate = max(boat1.hit_rate, min(1.0, hit_base * 0.6 + inside_pressure * 0.4))

    # ────────────────────────────────────
    # RUN-00 進入・初日・SINK適用可否
    # ────────────────────────────────────
    def _run00_entry(self):
        for b in self.boats:
            if b.lane == b.course:
                b.entry_type = "P0"
            elif b.lane < b.course:
                b.entry_type = "P2"
            else:
                b.entry_type = "P3"
        self.is_first_day = (self.race.day_no or 1) <= 1
        if self.is_first_day:
            self.out.notes.append("初日：ST正本＝平均ST（今節ST不使用・改正29）")

    def _st_value(self, b: BoatEntry) -> float:
        """ST正本：初日は平均ST、2日目以降は今節ST(あれば)"""
        if self.is_first_day:
            return b.avg_st or 0.18
        return b.today_st or b.avg_st or 0.18

    # ────────────────────────────────────
    # RUN-01 直接読み
    # ────────────────────────────────────
    def _run01_read(self):
        exhibition_times = [b.exhibition_time for b in self.boats if b.exhibition_time > 0]
        exhibition_sts = [b.exhibition_st for b in self.boats if b.exhibition_st != 0]
        best_exhibition_time = min(exhibition_times) if exhibition_times else None
        best_exhibition_st = min(exhibition_sts) if exhibition_sts else None

        for b in self.boats:
            c = b.course
            # P(1着)生値：コース別1着率を主、無ければ全国/当地から推定
            cw = b.course_win_rates.get(c)
            if cw is None:
                cw = b.local5y_win_rate or b.win_rate_1st
            b.p1_raw = max(0.0, _prob(cw))
            b.ti = b.p1_raw

            # 攻撃型（⑤b）
            tot = b.sashi + b.makuri + b.makurizashi
            if tot > 0:
                if b.makuri > b.sashi and b.makuri >= b.makurizashi:
                    b.attack_type = "捲り"
                elif b.sashi > b.makuri:
                    b.attack_type = "差し"
                else:
                    b.attack_type = "捲差"
            else:
                b.attack_type = "差し" if c <= 2 else "捲り"

            b.ei = self._compute_ei(b)
            b.ei = round(max(0.0, b.ei + self._season_st_adjustment(b)), 1)
            b.ei = self._apply_exhibition_adjustment(
                b, b.ei, best_exhibition_time, best_exhibition_st)

        # ── D-KAN（完遂力）5項目（改正65）：フィールド横断順位を用いる ──
        # モーター順位（2連率降順）上位2
        motor_order = sorted(
            self.boats, key=lambda x: _prob(x.motor_place2_rate), reverse=True)
        motor_top2 = {b.lane for b in motor_order[:2]}
        # EI上位3
        ei_order = sorted(self.boats, key=lambda x: (x.ei or 0), reverse=True)
        ei_top3 = {b.lane for b in ei_order[:3]}
        # 基準ST上位3（初日=平均ST／2日目以降=今節ST正本）昇順
        st_order = sorted(self.boats, key=lambda x: self._st_value(x))
        st_top3 = {b.lane for b in st_order[:3]}

        for b in self.boats:
            b.completion_power = self._completion_power(
                b, motor_top2, ei_top3, st_top3)
        self.out.dkan_counts = {b.lane: b.completion_power for b in self.boats}
        self._recompute_attack_rates()

    def _compute_ei(self, b: BoatEntry) -> float:
        motor = _motor_grade(b.motor_eval)
        st = self._st_value(b)
        st_factor = max(0.5, 1.5 - st * 5)
        return round(b.p1_raw * 100 * (motor / 3.0 + 0.3) * st_factor, 1)

    def _season_st_adjustment(self, b: BoatEntry) -> float:
        season_st = b.season_st or 0.0
        baseline_st = b.standard_st or b.avg_st or 0.15
        if season_st <= 0 or baseline_st <= 0:
            return 0.0
        st_delta = baseline_st - season_st
        return max(-6.0, min(6.0, st_delta * 60.0))

    def _apply_exhibition_adjustment(
        self,
        b: BoatEntry,
        base_ei: float,
        best_exhibition_time: Optional[float],
        best_exhibition_st: Optional[float],
    ) -> float:
        adjusted = base_ei

        if b.exhibition_time > 0 and best_exhibition_time is not None:
            diff = b.exhibition_time - best_exhibition_time
            adjusted += max(-8.0, min(8.0, -diff * 40.0))

        baseline_st = b.standard_st or b.avg_st or 0.15
        if b.exhibition_st != 0:
            st_delta = baseline_st - b.exhibition_st
            adjusted += max(-6.0, min(6.0, st_delta * 60.0))
            if best_exhibition_st is not None:
                adjusted += max(-3.0, min(3.0, (best_exhibition_st - b.exhibition_st) * 30.0))

        return round(max(0.0, adjusted), 1)

    def _completion_power(self, b: BoatEntry, motor_top2: set,
                          ei_top3: set, st_top3: set) -> int:
        """D-KAN充足数（0-5・改正65）"""
        count = 0
        # ① モーターB以上
        if _motor_grade(b.motor_eval) >= 2:
            count += 1
        elif b.lane in motor_top2 and _prob(b.motor_place2_rate) > 0:
            count += 1
        # ② EI上位3
        if b.lane in ei_top3:
            count += 1
        # ③ 基準ST上位3（初日=平均ST）
        if b.lane in st_top3:
            count += 1
        # ④ 捲り・捲差の実績
        if (b.makuri + b.makurizashi) > 0 or b.attack_type in ("捲り", "捲差"):
            count += 1
        # ⑤ 級A（A1/A2）
        if (b.rank or "").upper() in ("A1", "A2"):
            count += 1
        return count

    # ────────────────────────────────────
    # RUN-02 D-NAMIBA + D-REGIME + 逃げ成立度較正 + 再正規化
    # ────────────────────────────────────
    def _run02_namiba_regime_calibration(self):
        self.out.surface_type = VENUE_SURFACE_TYPE.get(self.race.venue, "標準")

        # ① ΣP1=1へ正規化（生値）
        p1map = {b.lane: b.p1_raw for b in self.boats}
        p1map = _normalize(p1map)

        boat1 = self._boat_by_course(1)
        prior = VENUE_IN_PRIOR.get(self.race.venue, 0.52)
        factor = 1.0
        self.out.cal_applied = False

        # ② 逃げ成立度の当節較正（改正46/48）
        if boat1 is not None and self.race.cal_r is not None and self.race.cal_n >= N_CAL:
            R = self.race.cal_r
            P0 = prior
            if R < P0 - 0.20:
                factor = DEC2
            elif R < P0 - 0.10:
                factor = DEC1
            if factor < 1.0:
                self.out.cal_applied = True
                self.out.cal_factor = factor
                self.out.notes.append(
                    f"逃げ成立度較正：実1号頭率R={R:.2f} < 場平均P0={P0:.2f} "
                    f"→ 1号P1×{factor}（標本{self.race.cal_n}R・改正46/48）")
        elif self.race.cal_n and self.race.cal_n < N_CAL:
            self.out.notes.append(
                f"較正標本{self.race.cal_n}R < N_cal({N_CAL})→prior据え置き（改正48）")

        # ③ 減衰＋再正規化（改正53）：ΔPを非1号へ比例配分しΣP1=1を回復
        if boat1 is not None and factor < 1.0:
            old = p1map[boat1.lane]
            new = old * factor
            delta = old - new
            others = {ln: v for ln, v in p1map.items() if ln != boat1.lane}
            os = sum(others.values())
            p1map[boat1.lane] = new
            if os > 0:
                for ln in others:
                    p1map[ln] += delta * (others[ln] / os)

        # 検算（ΣP1=1）
        ssum = sum(p1map.values())
        if ssum > 0 and abs(ssum - 1.0) > 1e-6:
            p1map = {ln: v / ssum for ln, v in p1map.items()}

        for b in self.boats:
            b.p1 = p1map.get(b.lane, 0.0)

        # D-NAMIBA：較正後1号P1でイン強/中/弱
        in_p1 = p1map.get(boat1.lane, prior) if boat1 else prior
        self.out.in_win_rate = round(in_p1, 3)
        self.out.s_in = "イン強" if in_p1 >= 0.55 else ("中" if in_p1 >= 0.42 else "イン弱")

        # D-REGIME（分散・被弾・攻め密度）
        ps = sorted((b.p1 for b in self.boats), reverse=True)
        dispersion = (ps[0] - ps[1]) * 100 if len(ps) >= 2 else 0
        top = max(self.boats, key=lambda b: b.p1)
        hit = sum(b.p1 * 100 for b in self.boats
                  if b.course in (2, 3, 4) and b.lane != top.lane)
        density = sum(1 for b in self.boats
                      if b.completion_power >= 3
                      or (b.rank == "A1" and _prob(b.place_rate) >= 0.55))
        self.out.regime_dispersion = round(dispersion, 1)
        self.out.regime_hit_rate = round(hit, 1)
        self.out.regime_attack_density = density
        if dispersion >= 15 and hit < 30 and density <= 1:
            self.out.regime = "順当"
        elif hit >= 30 or density >= 2:
            self.out.regime = "隠れ混戦"
        else:
            self.out.regime = "明白混戦"

    # ────────────────────────────────────
    # RUN-03b 攻めの主体A ＆ 攻撃型（2-2b）
    # ────────────────────────────────────
    def _run03b_main_attack(self):
        boat1 = self._boat_by_course(1)
        top = max(self.boats, key=lambda b: b.p1)

        # 外攻め発生率 ≒ 1 - 1号逃げ成立度
        in_p1 = boat1.p1 if boat1 else 0.0
        gen = (1.0 - in_p1) * 100
        self.out.gen_rate = round(gen, 1)

        # 最強攻め艇（非1号）
        attackers = [b for b in self.boats if b.course >= 2]
        strongest = max(attackers, key=lambda b: b.p1) if attackers else None

        # ── 発動艇認定（改正65）──
        # 発生率がフィールド最大 ∧ ≥5% ∧ D-KAN2項目以上
        fire = None
        if attackers:
            gmax_val = max(b.gen_rate for b in attackers)
            cand = max(attackers, key=lambda b: (b.gen_rate, b.completion_power))
            if (gmax_val >= GEN_FIRE
                    and cand.gen_rate >= gmax_val - 1e-9
                    and cand.completion_power >= DKAN_FIRE):
                fire = cand
        if fire is not None:
            self.out.fire_boat_lane = fire.lane
            self.out.fire_boat_gen = round(fire.gen_rate, 3)

        a_lane, a_course, a_type = (boat1.lane if boat1 else 1), 1, "1逃げ"

        if boat1 and in_p1 >= 0.50 and self.out.s_in == "イン強":
            # イン強：1逃げを主体。発動艇は第2頭候補として記録のみ（進入双方向再評価）
            a_lane, a_course, a_type = boat1.lane, 1, "1逃げ"
        elif fire is not None:
            # 発動艇優先：認定艇を攻めの主体に
            a_lane, a_course = fire.lane, fire.course
            a_type = self._attack_label(fire)
        elif gen >= 60 and strongest:
            a_lane, a_course = strongest.lane, strongest.course
            a_type = self._attack_label(strongest)
        elif top.course != 1 and in_p1 < 0.50:
            a_lane, a_course = top.lane, top.course
            a_type = self._attack_label(top)
        elif boat1:
            a_lane, a_course, a_type = boat1.lane, 1, "1逃げ"

        self.out.main_attack_lane = a_lane
        self.out.main_attack_course = a_course
        self.out.attack_type = a_type

        # 進入双方向再評価（P2前付け／P3深進入）：受益方向の補正注記
        amain = self._boat_by_lane(a_lane)
        if amain and amain.entry_type == "P3":
            self.out.notes.append(
                f"進入再評価：{a_course}号はダッシュ深進入(P3)→受益は外側へシフト")
        elif amain and amain.entry_type == "P2":
            self.out.notes.append(
                f"進入再評価：{a_course}号は前付け(P2)→内側受益を強める")

        if fire is not None:
            self.out.notes.append(
                f"発動艇認定＝{fire.course}号（発生率{fire.gen_rate*100:.0f}%・"
                f"D-KAN{fire.completion_power}/5・改正65）")
        self.out.notes.append(
            f"攻めの主体＝{a_course}号（{a_type}）／発生率{gen:.0f}%／"
            f"イン{self.out.s_in}")

    def _attack_label(self, b: BoatEntry) -> str:
        c = b.course
        if c == 2:
            return "2捲り" if b.attack_type == "捲り" else "2差し"
        if c == 3:
            return "3主体"
        if c == 4:
            return "4捲り"
        if c == 5:
            return "5単独捲り差し"
        if c == 6:
            return "6単独大外"
        return "1逃げ"

    # ────────────────────────────────────
    # RUN-04 筋目エンジン（2-3）：着順テンプレ→受益ラダー
    # ────────────────────────────────────
    def _run04_suji(self):
        # ── 捲り屋降格則（v58.7）──
        # 攻め主体が捲り系でも、認定発動艇でなく完遂力D-KAN<2なら主体降格→本命逃げへ復帰
        amain = self._boat_by_lane(self.out.main_attack_lane)
        is_makuri_main = ("捲" in (self.out.attack_type or "")) \
            and self.out.main_attack_course >= 2
        if (is_makuri_main and amain is not None
                and self.out.fire_boat_lane != amain.lane
                and amain.completion_power < DKAN_FIRE):
            boat1 = self._boat_by_course(1)
            if boat1:
                self.out.notes.append(
                    f"捲り屋降格則：{self.out.main_attack_course}号は成立条件不足"
                    f"（D-KAN{amain.completion_power}/5）→本命1逃げへ復帰")
                self.out.main_attack_lane = boat1.lane
                self.out.main_attack_course = 1
                self.out.attack_type = "1逃げ"

        c = self.out.main_attack_course
        a_lane = self.out.main_attack_lane

        def lane(course):
            b = self._boat_by_course(course)
            return b.lane if b else None

        # 攻めの主体・型 → 着順テンプレ（号艇=枠番へ）
        # 受益マップ原則：差し系=遠い外を切る／捲り系=通り道(内寄り)を切る
        templates: List[Tuple[int, List[int], List[int]]] = []  # (頭, 2着候補, 3着候補)
        L = {co: lane(co) for co in range(1, 7)}

        if c == 1:
            # 1逃げ：1-23系。番手筆頭＝2、一次受益＝カド外5
            templates.append((L[1], [L[2], L[3], L[5]], [L[2], L[3], L[4], L[5]]))
        elif c == 2:
            if self.out.attack_type == "2捲り":
                # 2捲り：1沈み・3以下便乗（2-3456）／通り道=1を切る
                templates.append((L[2], [L[3], L[4], L[5]], [L[3], L[4], L[5], L[6]]))
            else:
                # 2差し：1残る（2-1系）／遠い外(56)を切る
                templates.append((L[2], [L[1], L[3], L[4]], [L[1], L[3], L[4]]))
        elif c == 3:
            # 3主体・捲り：3-4-1 / 3-456／通り道=12を切る
            templates.append((L[3], [L[4], L[1], L[5]], [L[1], L[4], L[5], L[6]]))
        elif c == 4:
            # 4捲り（ダッシュ・役割交代）：4-1256（新4=1差し・新5=2連れ）
            templates.append((L[4], [L[1], L[2], L[5]], [L[1], L[2], L[5], L[6]]))
        elif c == 5:
            # 5単独捲り差し：5-12-1234／遠い外(6)を切る
            templates.append((L[5], [L[1], L[2], L[3]], [L[1], L[2], L[3], L[4]]))
        elif c == 6:
            # 6単独大外捲り：6-12系
            templates.append((L[6], [L[1], L[2]], [L[1], L[2], L[3]]))

        # 受益ラダー（0-7）：一次受益=カド外5・二次=6。anchor確定。
        if c == 1:
            ladder = [L[2], L[5], L[3]]            # 番手筆頭→一次受益→便乗
        else:
            ladder = [L[5], L[1], L[4]]            # 一次受益→差され残り本命→カド
        self.benefit_ladder = [x for x in ladder if x and x != a_lane]
        self.suji_templates = templates

        # ── 被弾率⑤f（1号評価専用：A型禁止判定・崩壊枝厚み）──
        self._no_a_format = False
        boat1 = self._boat_by_course(1)
        if boat1 and boat1.hit_rate >= HIT_HIGH:
            self._no_a_format = True
            self.out.notes.append(
                f"被弾率⑤f：1号の被弾率{boat1.hit_rate*100:.0f}%（高）→"
                f"A型(本命厚張り)禁止・崩壊枝を厚く")
            # 崩壊枝の厚み：1号を頭から外した攻め主体頭の枝を補強
            if c == 1 and templates:
                head, p2, p3 = templates[0]
                col = self._boat_by_course(2)
                if col:
                    templates.append((col.lane,
                                      [x for x in (L[3], L[4], L[5]) if x],
                                      [x for x in (L[1], L[3], L[4], L[5], L[6]) if x]))

        # 沈み候補（S4）：攻めが外ほど内が washed → SINK対象
        self._mark_sink(c)

    def _mark_sink(self, attack_course: int):
        for b in self.boats:
            b.is_sink = False
        if attack_course >= 4:
            # 外攻め：内の番手以外（2,3）が締められる
            for co in (2, 3):
                b = self._boat_by_course(co)
                if b and b.lane != self.out.main_attack_lane:
                    b.is_sink = True
        elif attack_course == 3:
            b = self._boat_by_course(2)
            if b:
                b.is_sink = True
        elif attack_course == 2 and self.out.attack_type == "2捲り":
            b = self._boat_by_course(1)
            if b:
                b.is_sink = True

    # ────────────────────────────────────
    # RUN-05 本線フォーマット選択 ＆ 軸確定（0.2）
    # ────────────────────────────────────
    def _run05_format_axis(self):
        ranked = sorted(self.boats, key=lambda b: b.p1, reverse=True)
        top1, top2 = ranked[0], (ranked[1] if len(ranked) > 1 else ranked[0])

        a_lane = self.out.main_attack_lane
        head_boat = self._boat_by_lane(a_lane) or top1

        # フォーマット選択（0.2）
        gap_ok = top2.p1 > 0 and (top1.p1 / max(top2.p1, 1e-6)) >= GAP
        if head_boat.p1 >= 0.50 and gap_ok:
            fmt = "A"
        elif (top1.p1 / max(top2.p1, 1e-6)) < GAP:
            fmt = "B"
        else:
            fmt = "A"
        # 被弾率⑤f：1号被弾率が高い場合A型禁止→B型へ強制（v58.7）
        if getattr(self, "_no_a_format", False) and fmt == "A":
            fmt = "B"
        self.out.fmt = fmt

        # 軸（受益ラダー優先・geometry最優先）
        axis_src = self.benefit_ladder[:]
        # テンプレ2着候補を補完
        for _, seconds, _ in self.suji_templates:
            for ln in seconds:
                if ln and ln not in axis_src and ln != a_lane:
                    axis_src.append(ln)
        # 紐（3着）
        hus_src = []
        for _, _, thirds in self.suji_templates:
            for ln in thirds:
                if ln and ln not in hus_src:
                    hus_src.append(ln)
        # A級・着内ありの深枠艇を残す（0-10：レーンだけで切らない）
        for b in sorted(self.boats, key=lambda b: b.p1, reverse=True):
            if b.lane == a_lane:
                continue
            if b.rank in ("A1", "A2") or _prob(b.course_tricast_rates.get(b.course, 0)) >= 0.40:
                if b.lane not in axis_src:
                    axis_src.append(b.lane)
                if b.lane not in hus_src:
                    hus_src.append(b.lane)

        if fmt == "A":
            self.out.head_boats = [a_lane]
            self.out.head_type = "A"
            self.out.axis_boats = axis_src[:3]
            self.out.hus_boats = (axis_src[:3] + [x for x in hus_src if x not in axis_src[:3]])[:4]
        else:
            # B型：頭2枚（本命逃げ or 発動艇）
            second_head = top1.lane if top1.lane != a_lane else top2.lane
            self.out.head_boats = [a_lane, second_head]
            self.out.head_type = "AB"
            axis4 = list(dict.fromkeys([a_lane, second_head] + axis_src))[:4]
            self.out.axis_boats = axis4
            # 3着側に攻め成立側の外艇6を必ず1枚（改正42）
            hus4 = list(dict.fromkeys(axis4 + hus_src))
            l6 = self._lane_of_course(6)
            if l6 and l6 not in hus4:
                hus4.append(l6)
            self.out.hus_boats = hus4[:4]

        # 弱頭判定（改正54）
        if fmt == "A":
            self.out.weak_head = head_boat.p1 < WEAK_HEAD_TH
        else:
            hsum = sum(self._boat_by_lane(h).p1 for h in self.out.head_boats
                       if self._boat_by_lane(h))
            self.out.weak_head = hsum < WEAK_HEAD_TH
        if self.out.weak_head:
            self.out.notes.append("弱頭：頭1着率<50%→高オッズでも勝負禁止（改正54）")

    # ────────────────────────────────────
    # RUN-06 資金枠取り（オッズ前）
    # ────────────────────────────────────
    def _run06_budget(self):
        self.out.budget_main = 14000
        self.out.budget_exacta = 3000
        self.out.budget_manshu = 3000

    # ────────────────────────────────────
    # RUN-07 データ違和感停止
    # ────────────────────────────────────
    def _run07_anomaly(self):
        a = self._boat_by_lane(self.out.main_attack_lane)
        if a and a.course >= 2:
            st = self._st_value(a)
            base = sum(self._st_value(b) for b in self.boats) / max(1, len(self.boats))
            if not self.is_first_day and st > base + 0.05:
                self.out.notes.append(
                    f"攻め艇ST遅（{st:.2f}>基準{base:.2f}+0.05）→崩壊枝（本命逃げ復帰）確保")

    # ────────────────────────────────────
    # RUN-08 合成オッズ反比例配分 → 戻り額ゲート（改正60・v58.7）
    # ────────────────────────────────────
    def _run08_payout_gate(self):
        odds3 = self.race.odds_3t or {}
        self.out.odds_available = bool(odds3)

        # 本線の組番生成
        combos = self._gen_honsen_combos()

        if not odds3:
            # 改正56：ODDS_T取得不能 → 全枝見送り
            self.out.race_verdict = "見送り"
            self.out.payout_grade = "見送り"
            self.out.honsen = [
                BuyPoint(c, round(self._trifecta_p(c), 5), 0.0, 0.0, "見送り", "本線")
                for c in combos]
            self.out.notes.append("ODDS_T未取得→戻り額判定不能・全枝見送り（改正56）")
            return

        points: List[BuyPoint] = []
        inv_sum = 0.0
        for c in combos:
            p = self._trifecta_p(c)
            od = float(odds3.get(c, 0) or 0)
            ev = p * od   # EVは内部参考値として保持（v58.7）
            points.append(BuyPoint(c, round(p, 5), round(od, 1), round(ev, 3),
                                   "通常", "本線"))
            if od > 0:
                inv_sum += 1.0 / od

        # 合成オッズ（全点均一戻りとなる反比例配分）と戻り額
        syn = (1.0 / inv_sum) if inv_sum > 0 else 0.0
        budget = float(self.out.budget_main or 0)
        payout = syn * budget
        self.out.synthetic_odds = round(syn, 1)
        self.out.payout = round(payout, 0)

        # 戻り額ゲート（改正60）：≤30,000=見送り / 30,000〜50,000=通常 / ≥50,000=勝負
        if payout >= PAYOUT_BET:
            verdict = "勝負"
        elif payout > PAYOUT_SKIP:
            verdict = "通常"
        else:
            verdict = "見送り"
        # 弱頭は勝負禁止（改正54）
        if self.out.weak_head and verdict == "勝負":
            verdict = "通常"
            self.out.notes.append("弱頭につき勝負→通常へ降格（改正54）")

        self.out.race_verdict = verdict
        self.out.payout_grade = verdict

        # 各点へ判定とuniform戻り額を反映
        for bp in points:
            if bp.odds <= 0:
                bp.grade = "見送り"
                bp.payout = 0.0
            else:
                bp.grade = verdict
                bp.payout = round(payout, 0)
        self.out.honsen = points
        self.out.notes.append(
            f"戻り額ゲート：合成オッズ{syn:.1f}倍×投資{budget:,.0f}円="
            f"戻り額{payout:,.0f}円→{verdict}（改正60）")

    def _gen_honsen_combos(self) -> List[str]:
        heads = self.out.head_boats
        seconds = self.out.axis_boats
        thirds = self.out.hus_boats
        combos: List[str] = []
        for h in heads:
            for s in seconds:
                if s == h:
                    continue
                for t in thirds:
                    if t in (h, s):
                        continue
                    if self._combo_matches_story(h, s, t):
                        combos.append(f"{h}-{s}-{t}")
        return list(dict.fromkeys(combos))

    def _combo_matches_story(self, head: int, second: int, third: int) -> bool:
        for tpl_head, tpl_seconds, tpl_thirds in self.suji_templates:
            if head != tpl_head:
                continue
            if second in tpl_seconds and third in tpl_thirds:
                return True
        return False

    def _trifecta_p(self, combo: str) -> float:
        """P(A-B-C)=P(A1着)×P(B2着|A)×P(C3着|A,B)"""
        try:
            h, s, t = (int(x) for x in combo.split("-"))
        except ValueError:
            return 0.0
        bh = self._boat_by_lane(h)
        bs = self._boat_by_lane(s)
        bt = self._boat_by_lane(t)
        if not (bh and bs and bt):
            return 0.0
        p1 = bh.p1
        # P(B2着|A)：⑤g優先→欠損時 コース別2連率-1着率
        base2 = {b.lane: self._second_base(b, h) for b in self.boats if b.lane != h}
        base2 = _normalize(base2)
        p2 = base2.get(s, 0.0)
        # P(C3着|A,B)：残存=3連率-2連率、沈み候補はSINK
        base3 = {}
        for b in self.boats:
            if b.lane in (h, s):
                continue
            res = max(0.0, _prob(b.course_tricast_rates.get(b.course, 0))
                      - _prob(b.course_place2_rates.get(b.course, 0)))
            if res <= 0:
                res = max(0.0, _prob(b.course_tricast_rates.get(b.course, 0)) * 0.3)
            if b.is_sink:
                res *= SINK
            base3[b.lane] = res
        base3 = _normalize(base3)
        p3 = base3.get(t, 0.0)
        return p1 * p2 * p3

    def _second_base(self, b: BoatEntry, head_lane: int) -> float:
        head_course = head_lane
        head_boat = self._boat_by_lane(head_lane)
        if head_boat is not None:
            head_course = head_boat.course or head_lane
        if head_lane in b.p2_link and b.p2_link[head_lane] > 0:
            return _prob(b.p2_link[head_lane])
        if head_course in b.p2_link and b.p2_link[head_course] > 0:
            return _prob(b.p2_link[head_course])
        place2 = _prob(b.course_place2_rates.get(b.course, 0))
        win = _prob(b.course_win_rates.get(b.course, 0))
        v = place2 - win
        if v <= 0:
            v = place2 * 0.5 or b.p1 * 0.5
        return max(0.0, v)

    # ────────────────────────────────────
    # RUN-09 二連単（独立世界線）＋ 万舟（6〜8点抽出）
    # ────────────────────────────────────
    def _run09_exacta_manshu(self):
        odds2 = self.race.odds_2t or {}
        odds3 = self.race.odds_3t or {}
        a_lane = self.out.main_attack_lane
        boat1 = self._boat_by_course(1)
        l1 = boat1.lane if boat1 else 1

        # ── 二連単：別頭世界線（1号が沈み攻め艇が頭）──
        exacta_pts: List[BuyPoint] = []
        if odds2:
            cand_heads = [b.lane for b in sorted(self.boats, key=lambda b: b.p1, reverse=True)
                          if b.lane not in self.out.head_boats][:3]
            raw = []
            for h in cand_heads:
                base2 = _normalize({b.lane: self._second_base(b, h)
                                    for b in self.boats if b.lane != h})
                # 2着は受益/便乗艇 or 差され残り1号
                seconds = [x for x in (self.benefit_ladder + [l1]) if x and x != h]
                for s in seconds[:2]:
                    combo = f"{h}-{s}"
                    od = float(odds2.get(combo, 0) or 0)
                    p = self._boat_by_lane(h).p1 * base2.get(s, 0.0) if self._boat_by_lane(h) else 0
                    ev = p * od
                    if od > 0:
                        raw.append((combo, p, od, ev))
            # ガミ禁止：Σ(1/オッズ)<1.0 ＋ EV≥EV_min
            raw.sort(key=lambda x: x[3], reverse=True)
            sel = []
            for combo, p, od, ev in raw:
                if ev < EV_MIN:
                    continue
                trial = sel + [(combo, p, od, ev)]
                if sum(1.0 / o for _, _, o, _ in trial) < 1.0 and len(trial) <= 3:
                    sel = trial
            exacta_pts = [BuyPoint(c, round(p, 5), round(o, 1), round(e, 3),
                                   "勝負" if e >= EV_BAT else "通常", "2連単(別頭)")
                          for c, p, o, e in sel]
        self.out.exacta = exacta_pts
        exacta_prefix = {p.combo for p in exacta_pts}

        # ── 万舟：6〜8点抽出義務（改正59）──
        manshu_raw: List[Tuple[str, str]] = []  # (combo, branch)
        l4 = self._lane_of_course(4)
        l5 = self._lane_of_course(5)
        l3 = self._lane_of_course(3)
        l6 = self._lane_of_course(6)

        def add(combo, branch):
            if combo and all(combo.split("-")):
                manshu_raw.append((combo, branch))

        # (A) 折り返し頭（核）：受益・便乗が発動艇を差し抜く 5-4 / 3-4
        if l5 and l4:
            add(f"{l5}-{l4}-{l1}", "折返(5-4)")
            add(f"{l5}-{l4}-{l3}", "折返(5-4)")
        if l3 and l4:
            add(f"{l3}-{l4}-{l1}", "折返(3-4)")
        # (B) 発動艇押し切り：主攻め/外強襲艇頭で2着人気薄
        for s in self.benefit_ladder[:2]:
            add(f"{a_lane}-{s}-{l6}", "押切")
            add(f"{a_lane}-{s}-{l1}", "押切")
        # (C) 攻め不発・本命残り：1-受益-X
        for s in self.benefit_ladder[:2]:
            add(f"{l1}-{s}-{l4}", "不発(本命残)")

        # フィルタ：100倍以上・本線/2連単と非被り・重複禁止
        honsen_combos = {p.combo for p in self.out.honsen}
        manshu_pts: List[BuyPoint] = []
        seen = set()
        for combo, branch in manshu_raw:
            if combo in seen:
                continue
            seen.add(combo)
            parts = combo.split("-")
            if len(set(parts)) != 3:
                continue
            if combo in honsen_combos:  # 改正55 本線重複禁止
                continue
            prefix = "-".join(parts[:2])
            if prefix in exacta_prefix:  # 改正49 (頭-2着)完全一致禁止
                continue
            od = float(odds3.get(combo, 0) or 0)
            p = self._trifecta_p(combo)
            ev = p * od
            if odds3 and od > 0 and od < MANSHU_MIN_ODDS:
                continue  # 100倍未満は万舟対象外
            grade = "通常" if (od > 0 and ev >= EV_MIN) else "見送り"
            manshu_pts.append(BuyPoint(combo, round(p, 5), round(od, 1),
                                       round(ev, 3), grade, branch))

        # 保険枠（改正45/52）：主攻め/外強襲頭は各1点をEV例外で最小単位確保
        ins_heads = {a_lane}
        if l4:
            ins_heads.add(l4)
        if l6 and self.out.main_attack_course >= 4:
            ins_heads.add(l6)
        for p in manshu_pts:
            if int(p.combo.split("-")[0]) in ins_heads and p.grade == "見送り" and p.odds >= MANSHU_MIN_ODDS:
                p.grade = "保険"

        # 6〜8点抽出義務
        manshu_pts.sort(key=lambda p: (p.grade != "保険", -(p.ev if p.ev > 0 else -1)))
        self.out.manshu = manshu_pts[:8]
        if len(self.out.manshu) < 6:
            self.out.notes.append(
                f"万舟抽出{len(self.out.manshu)}点（6点未満：100倍候補不足・要オッズ）")

    # ────────────────────────────────────
    # RUN-10 整合チェック → 出力
    # ────────────────────────────────────
    def _run10_finalize(self):
        # 自信度・波乱度
        regime_score = {"順当": 75, "隠れ混戦": 55, "明白混戦": 40}.get(self.out.regime, 50)
        if self.out.race_verdict == "勝負":
            regime_score += 10
        elif self.out.race_verdict == "見送り":
            regime_score -= 15
        self.out.confidence = max(10.0, min(95.0, float(regime_score)))
        self.out.wave_score = round(self.out.regime_hit_rate, 1)

        # 各艇評価（1〜6号艇すべて）
        # 優勢順位(EI降順)・基準ST順位(平均ST昇順)を算出
        _ei_order = sorted(self.boats, key=lambda x: (x.ei if x.ei is not None else -1.0), reverse=True)
        _ei_rank = {b.lane: i + 1 for i, b in enumerate(_ei_order)}
        _st_order = sorted(self.boats, key=lambda x: (x.avg_st if getattr(x, "avg_st", None) else 9.9))
        _st_rank = {b.lane: i + 1 for i, b in enumerate(_st_order)}
        _heads = set(self.out.head_boats or [])
        _axis = set(self.out.axis_boats or []) | set(self.benefit_ladder or [])
        evals = []
        for b in sorted(self.boats, key=lambda b: b.lane):
            if b.lane in _heads:
                role = "頭"
            elif b.lane in _axis:
                role = "2着候補"
            elif b.is_sink:
                role = "沈み候補"
            elif b.lane == self.out.main_attack_lane:
                role = "攻めの主体"
            else:
                role = "—"
            evals.append({
                "lane": b.lane, "course": b.course, "name": b.name, "rank": b.rank,
                "p1": round(b.p1, 3), "ei": b.ei, "attack_type": b.attack_type,
                "completion_power": b.completion_power, "role": role,
                "is_sink": b.is_sink,
                "ei_rank": _ei_rank.get(b.lane),
                "st_rank": _st_rank.get(b.lane),
                "dkan": b.completion_power,
                "gen_rate": round(b.gen_rate, 3),
                "hit_rate": round(b.hit_rate, 3),
                "is_fire": (b.lane == self.out.fire_boat_lane and self.out.fire_boat_lane > 0),
            })
        self.out.boat_evals = evals

        if self.out.insufficient_boats:
            self.out.race_verdict = "見送り"
            self.out.payout_grade = "見送り"
            for points in (self.out.honsen, self.out.exacta, self.out.manshu):
                for bp in points:
                    bp.grade = "見送り"

        adopted_h = [p.combo for p in self.out.honsen if p.grade in ("勝負", "通常")]
        fire_txt = (f"／発動艇{self._boat_by_lane(self.out.fire_boat_lane).course}号"
                    if self.out.fire_boat_lane else "")
        payout_txt = (f"／合成{self.out.synthetic_odds:.1f}倍・戻り額{self.out.payout:,.0f}円"
                      if self.out.odds_available else "")
        self.out.reasoning = (
            f"攻めの主体={self.out.main_attack_course}号({self.out.attack_type})／"
            f"フォーマット{self.out.fmt}／レジーム{self.out.regime}／"
            f"判定{self.out.race_verdict}"
            + fire_txt
            + payout_txt
            + ("／弱頭" if self.out.weak_head else "")
            + ("／較正適用" if self.out.cal_applied else "")
            + f"／本線採用{len(adopted_h)}点・万舟{len(self.out.manshu)}点（v59.0）")
        self.out.race_type = self.out.regime

    # ── ユーティリティ ──
    def _boat_by_course(self, course: int) -> Optional[BoatEntry]:
        for b in self.boats:
            if b.course == course:
                return b
        return None

    def _boat_by_lane(self, lane: int) -> Optional[BoatEntry]:
        for b in self.boats:
            if b.lane == lane:
                return b
        return None

    def _lane_of_course(self, course: int) -> Optional[int]:
        b = self._boat_by_course(course)
        return b.lane if b else None


# ═══════════════════════════════════════════════════════════
# DB/API データ変換
# ═══════════════════════════════════════════════════════════

def race_dict_to_input(race: dict) -> RaceInput:
    boats_raw = race.get("boats", [])
    boats: List[BoatEntry] = []
    for i, b in enumerate(boats_raw):
        lane = _safe_int(b.get("lane", i + 1), i + 1)
        course = _safe_int(b.get("entry_course", lane), lane)

        cw, cp2, ctri = {}, {}, {}
        sashi = makuri = makurizashi = 0
        p2_link = {}
        for c in range(1, 7):
            if b.get(f"c{c}_win_rate") is not None:
                cw[c] = _safe_float(b[f"c{c}_win_rate"])
            if b.get(f"c{c}_place2_rate") is not None:
                cp2[c] = _safe_float(b[f"c{c}_place2_rate"])
            if b.get(f"c{c}_tricast_rate") is not None:
                ctri[c] = _safe_float(b[f"c{c}_tricast_rate"])
            if b.get(f"p2_link_{c}") is not None:
                p2_link[c] = _safe_float(b.get(f"p2_link_{c}"))
        # 進入コースの決まり手だけ集計
        sashi = _safe_int(b.get(f"c{course}_sashi", 0))
        makuri = _safe_int(b.get(f"c{course}_makuri", 0))
        makurizashi = _safe_int(b.get(f"c{course}_makurizashi", 0))

        boats.append(BoatEntry(
            lane=lane,
            course=course,
            name=b.get("name", ""),
            rank=b.get("rank", ""),
            f_count=_safe_int(b.get("f_count", 0)),
            win_rate_1st=_safe_float(b.get("national_win_rate")),
            win_rate_2nd=_safe_float(b.get("national_place2_rate")),
            place_rate=_safe_float(b.get("national_place2_rate")),
            course_win_rates=cw,
            course_place2_rates=cp2,
            course_tricast_rates=ctri,
            sashi=sashi, makuri=makuri, makurizashi=makurizashi,
            nigiri_rate=_safe_float(b.get("nigiri_rate")),
            motor_eval=b.get("motor_eval", "") or "",
            motor_place2_rate=_safe_float(b.get("motor_place2_rate")),
            avg_st=_safe_float(b.get("avg_st"), 0.15),
            today_st=_safe_float(b.get("today_st") or b.get("season_st") or b.get("exhibition_st")),
            season_st=_safe_float(b.get("season_st")),
            standard_st=_safe_float(b.get("standard_st") or b.get("avg_st"), 0.15),
            st_rank=_safe_int(b.get("st_advantage_rank") or b.get("today_st_rank"), 3),
            exhibition_time=_safe_float(b.get("exhibition_time")),
            exhibition_st=_safe_float(b.get("exhibition_st")),
            local5y_win_rate=_safe_float(b.get("local5y_win_rate")),
            local5y_tricast_rate=_safe_float(b.get("local5y_tricast_rate")),
            gen_rate=_safe_float(b.get("gen_rate")),
            hit_rate=_safe_float(b.get("hit_rate")),
            p2_link=p2_link,
        ))

    if len(set(b.course for b in boats if b.course)) <= 1:
        for b in boats:
            b.course = b.lane

    cal = race.get("escape_calibration") or {}
    return RaceInput(
        race_id=race.get("id", 0),
        venue=race.get("venue", ""),
        race_no=race.get("race_no", 0),
        day_no=_safe_int(race.get("day_no", 1), 1),
        date=race.get("date", ""),
        weather=race.get("weather", "") or "",
        wind_speed=_safe_float(race.get("wind_speed")),
        wind_direction=race.get("wind_direction", "") or "",
        wave_height=_safe_float(race.get("wave_height")),
        boats=boats,
        odds_3t=race.get("odds_3t") or {},
        odds_2t=race.get("odds_2t") or {},
        odds_win=race.get("odds_win") or {},
        odds_updated_at=race.get("odds_updated_at") or "",
        cal_r=cal.get("r"),
        cal_n=_safe_int(cal.get("n")),
    )


def _bp_list(points: List[BuyPoint]) -> List[Dict]:
    return [{"combo": p.combo, "p": p.p, "odds": p.odds, "ev": p.ev,
             "grade": p.grade, "branch": p.branch, "payout": p.payout}
            for p in points]


def output_to_prediction_dict(out: PredictionOutput) -> dict:
    adopted_honsen = [p.combo for p in out.honsen if p.grade in ("勝負", "通常")]
    adopted_exacta = [p.combo for p in out.exacta if p.grade in ("勝負", "通常")]
    adopted_manshu = [p.combo for p in out.manshu if p.grade in ("勝負", "通常", "保険")]
    trifecta_str = ",".join(adopted_honsen)
    exacta_str = ",".join(adopted_exacta)

    # ── フロント(SystemPredictionPanel)互換: 本線をF1(第1頭)/F2(第2頭)に分割 ──
    def _head_of(combo: str) -> int:
        try:
            return int(combo.split("-")[0])
        except (ValueError, IndexError):
            return 0
    _heads_order = list(out.head_boats or [])
    _f1_head = _heads_order[0] if _heads_order else (_head_of(adopted_honsen[0]) if adopted_honsen else 0)
    _f2_head = _heads_order[1] if len(_heads_order) > 1 else None
    _trifecta_f1 = [c for c in adopted_honsen if _head_of(c) == _f1_head]
    _trifecta_f2 = [c for c in adopted_honsen if _f2_head is not None and _head_of(c) == _f2_head]
    # F1/F2いずれにも振り分けられない採用本線はF1へ寄せる(取りこぼし防止)
    _assigned = set(_trifecta_f1) | set(_trifecta_f2)
    for c in adopted_honsen:
        if c not in _assigned:
            _trifecta_f1.append(c)

    return {
        "source": "system_v58",
        "predicted_trifecta": trifecta_str,
        "predicted_exacta": exacta_str,
        "confidence": out.confidence,
        "reasoning": out.reasoning,
        "pattern": out.regime,
        "main_attack": f"{out.main_attack_course}号({out.attack_type})",
        "classification": out.race_type,
        "trifecta": trifecta_str,
        "exacta": exacta_str,
        "is_correct": None,
        "detail": {
            "version": "v59.0",
            "regime": out.regime,
            "s_in": out.s_in,
            "in_win_rate": out.in_win_rate,
            "surface_type": out.surface_type,
            "main_attack_course": out.main_attack_course,
            "main_attack_lane": out.main_attack_lane,
            "attack_type": out.attack_type,
            "gen_rate": out.gen_rate,
            "fmt": out.fmt,
            "head_boats": out.head_boats,
            "head_type": out.head_type,
            "axis_boats": out.axis_boats,
            "hus_boats": out.hus_boats,
            "weak_head": out.weak_head,
            "cal_applied": out.cal_applied,
            "cal_factor": out.cal_factor,
            "odds_available": out.odds_available,
            "race_verdict": out.race_verdict,
            # ── v58.7 改正60：戻り額ゲート ──
            "synthetic_odds": out.synthetic_odds,
            "payout": out.payout,
            "payout_grade": out.payout_grade,
            # ── v58.7 改正65：発動艇認定／D-KAN ──
            "fire_boat_lane": out.fire_boat_lane,
            "fire_boat_gen": out.fire_boat_gen,
            "dkan_counts": out.dkan_counts,
            "honsen": _bp_list(out.honsen),
            "honsen_adopted": adopted_honsen,
            # ── フロント(SystemPredictionPanel)互換キー ──
            "f1_head": _f1_head,
            "trifecta_f1": _trifecta_f1,
            "f2_head": _f2_head,
            "trifecta_f2": _trifecta_f2,
            "exacta": adopted_exacta,
            "manshu": adopted_manshu,
            "exacta_detail": _bp_list(out.exacta),
            "manshu_detail": _bp_list(out.manshu),
            "manshu_adopted": adopted_manshu,
            "budget_main": out.budget_main,
            "budget_exacta": out.budget_exacta,
            "budget_manshu": out.budget_manshu,
            "confidence": out.confidence,
            "wave_score": out.wave_score,
            "regime_dispersion": out.regime_dispersion,
            "regime_hit_rate": out.regime_hit_rate,
            "regime_attack_density": out.regime_attack_density,
            "notes": out.notes,
            "boat_evals": out.boat_evals,
        }
    }


def run_system_prediction(race: dict) -> dict:
    """レースdictを受け取り、v59.0システム予測を実行して結果dictを返す"""
    race_input = race_dict_to_input(race)
    predictor = BoatracePredictor()
    output = predictor.predict(race_input)
    return output_to_prediction_dict(output)
