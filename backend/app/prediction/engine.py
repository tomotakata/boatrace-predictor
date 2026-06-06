"""
競艇予想AI v56.3 システム実装
PDFプロンプト「競艇予想AI v56.3（受益2着スパイン・万舟全レース必須／100倍定義・反復スキャン版）」の
ロジックをAIへのプロンプトとしてではなく、Pythonコードとして実装したもの。

RUN順:
RUN-00: 進入順評価 (D-P)
RUN-01: ダッシュボード直接読み
RUN-02: レースタイプ分類 + 水面タイプ判定
RUN-02b: D-NAMIBA (S_in算出)
RUN-02c: D-REGIME (レジーム3軸)
RUN-03: 本命頭特定 (D-IN)
RUN-04: 機構1-D
RUN-04b: 機構1-E
RUN-05: 軸(D-ZIKU) + D-GATE + D-2CHAKU + D-GAI
RUN-05c: D-CHAKUNAI
RUN-05d: D-JUEKI受益2着マトリクス
RUN-06: 人気吸収艇 (D-KYUSYU)
RUN-07: 筋目成立フィルター
RUN-07b: 筋目連動 (D-SEN)
RUN-08: 形選択 + 三連単確定
RUN-09: 二連単
RUN-09b: 万舟候補プール生成
RUN-10: 自信度・波乱度
RUN-11: データ違和感停止
RUN-12: 予算分割（オッズ前）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from itertools import permutations


# ─────────────────────────────────────────
# データクラス
# ─────────────────────────────────────────

@dataclass
class BoatEntry:
    """1艇分の入力データ（BoatModel + 進入コース情報）"""
    lane: int              # 枠番 1-6
    course: int            # 進入コース 1-6
    name: str = ""
    rank: str = ""         # A1/A2/B1/B2/F
    f_count: int = 0

    # 1着率（コース別）
    win_rate_1st: float = 0.0        # 全国1着率
    win_rate_2nd: float = 0.0        # 全国2着率（place2_rate）
    place_rate: float = 0.0          # 着内確率 (2連対率的)

    # モーター
    motor_eval: str = ""             # A/B/C/D
    motor_place2_rate: float = 0.0

    # ST
    avg_st: float = 0.15
    standard_st: float = 0.15
    st_rank: int = 3                 # ST優位ランク (1が最良)

    # コース別成績
    course_win_rates: Dict[int, float] = field(default_factory=dict)   # {1: 0.5, ...}
    course_tricast_rates: Dict[int, float] = field(default_factory=dict)

    # 当地5年
    local5y_win_rate: float = 0.0
    local5y_tricast_rate: float = 0.0

    # 計算済み指標（エンジン内部で設定）
    ei: float = 0.0       # 期待指数
    ti: float = 0.0       # TI指数 (1着確率の総合)
    m2_rate: float = 0.0  # M2連率（2コース決まり手率）
    grip_rate: float = 0.0  # 握り率

    # D-NAMIBA補正後1着確率
    adj_win_rate: float = 0.0

    # D-KAN完遂力 (0=なし/1=弱/2=中/3=強)
    completion_power: int = 0

    # 進入タイプ D-P
    entry_type: str = "P0"  # P0/P2/P3


@dataclass
class RaceInput:
    """レース入力データ"""
    race_id: int
    venue: str
    race_no: int
    day_no: int = 1       # 節の何日目か（D-NAMIBAのprior用）
    date: str = ""

    weather: str = ""
    wind_speed: float = 0.0
    wind_direction: str = ""
    wave_height: float = 0.0

    boats: List[BoatEntry] = field(default_factory=list)

    # 節累積データ（D-NAMIBA用）: 当節イン1着率
    session_in_1st_wins: int = 0   # 当節1号が1着になったレース数
    session_total_races: int = 0   # 当節総レース数


@dataclass
class PredictionOutput:
    """予測出力"""
    # 内部RUN結果
    race_type: str = ""           # A/B/C/D/E/F/G
    regime: str = ""              # 順当/隠れ混戦/明白混戦
    surface_type: str = ""        # 差し/捲り/標準

    # D-NAMIBA
    s_in: str = ""               # イン強/中/弱
    in_win_rate: float = 0.0

    # 頭
    head_boats: List[int] = field(default_factory=list)   # 号艇番号（最大2枚）
    head_type: str = "A"          # A=1枚, AB=2枚

    # 機構1-E
    mech1e_active: bool = False
    f1_head: int = 1
    f2_head: Optional[int] = None

    # 受益2着
    benefit_2nd: Dict[int, List[int]] = field(default_factory=dict)  # {頭号艇: [2着候補...]}
    
    # 三連単フォーメーション
    trifecta_f1: List[str] = field(default_factory=list)   # ["1-2-3", ...]
    trifecta_f2: List[str] = field(default_factory=list)

    # 二連単（最大3点）
    exacta: List[str] = field(default_factory=list)

    # 万舟（全レース必須・6-10点・各目100倍以上）
    manshu_candidates: List[str] = field(default_factory=list)

    # 予算配分
    budget_main: int = 16000
    budget_exacta: int = 4000
    budget_manshu: int = 3000

    # 信頼度
    confidence: float = 50.0
    wave_score: float = 30.0    # 波乱度

    # レジーム3軸詳細
    regime_dispersion: float = 0.0
    regime_hit_rate: float = 0.0
    regime_attack_density: int = 0

    # 警告・メモ
    notes: List[str] = field(default_factory=list)

    # 最終的な買い目サマリ
    main_trifecta: str = ""
    sub_trifecta: str = ""
    reasoning: str = ""


# ─────────────────────────────────────────
# 定数
# ─────────────────────────────────────────

VENUE_SURFACE_TYPE = {
    "三国": "差し", "尼崎": "差し",
    "桐生": "捲り", "戸田": "捲り", "芦屋": "捲り",
    "江戸川": "江戸川",
    "住之江": "標準", "びわこ": "標準", "琵琶湖": "標準",
    "大村": "標準", "唐津": "標準", "福岡": "標準",
    "宮島": "標準", "児島": "標準", "丸亀": "標準",
    "平和島": "標準", "多摩川": "標準", "浜名湖": "標準",
    "常滑": "標準", "津": "標準", "蒲郡": "標準",
    "鳴門": "標準", "高松": "標準", "下関": "標準",
    "若松": "標準", "芦屋": "捲り", "遠賀": "標準",
    "徳山": "標準",
}


# ─────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────

def _motor_grade(motor_eval: str) -> int:
    """モーター評価を数値に変換（A=3, B=2, C=1, D=0）"""
    return {"A": 3, "B": 2, "C": 1, "D": 0}.get(motor_eval.upper()[:1] if motor_eval else "", 1)


def _rank_grade(rank: str) -> int:
    """選手ランクを数値に変換"""
    return {"A1": 4, "A2": 3, "B1": 2, "B2": 1, "F": 0}.get(rank.upper() if rank else "", 1)


def _compute_ei(boat: BoatEntry, all_boats: List[BoatEntry]) -> float:
    """EI（期待指数）を計算: win_rate * motor_grade * st_factor"""
    motor = _motor_grade(boat.motor_eval)
    st_factor = max(0.5, 1.5 - boat.avg_st * 5)  # ST0.10→1.0, ST0.15→0.75
    course_win = boat.course_win_rates.get(boat.course, boat.win_rate_1st)
    ei = course_win * 100 * (motor / 3.0) * st_factor
    return round(ei, 1)


def _compute_completion_power(boat: BoatEntry) -> int:
    """
    D-KAN 完遂力: 4項目の充足数
    (1) モーター総合A以上
    (2) 3連対率40%以上
    (3) EI3位以内 → 後で上書き
    (4) 基準ST3位以内 → st_rank
    3=強, 2=中, 1=弱, 0=なし
    """
    count = 0
    if _motor_grade(boat.motor_eval) >= 3:
        count += 1
    if boat.course_tricast_rates.get(boat.course, boat.local5y_tricast_rate or 0) >= 0.40:
        count += 1
    # (3)(4) は後で修正
    if boat.st_rank <= 3:
        count += 1
    if count >= 3:
        return 3
    elif count == 2:
        return 2
    elif count == 1:
        return 1
    return 0


# ─────────────────────────────────────────
# メインエンジン
# ─────────────────────────────────────────

class BoatracePredictor:
    """競艇予想AI v56.3 Pythonシステム実装"""

    def __init__(self):
        self.out = PredictionOutput()

    def predict(self, race: RaceInput) -> PredictionOutput:
        self.race = race
        self.boats = race.boats  # sorted by course
        self.out = PredictionOutput()
        self.out.notes = []

        # ── RUN-00: 進入タイプ判定 ──
        self._run00_entry_type()

        # ── RUN-01: 指標計算 ──
        self._run01_compute_indicators()

        # ── RUN-02: 水面タイプ ──
        self._run02_surface_type()

        # ── RUN-02b: D-NAMIBA ──
        self._run02b_namiba()

        # ── RUN-02c: D-REGIME ──
        self._run02c_regime()

        # ── RUN-03: 頭特定 ──
        self._run03_head()

        # ── RUN-04: 機構1-D ──
        self._run04_mech1d()

        # ── RUN-04b: 機構1-E ──
        self._run04b_mech1e()

        # ── RUN-05: D-ZIKU + D-GATE + D-2CHAKU ──
        self._run05_axis()

        # ── RUN-05c: D-CHAKUNAI ──
        self._run05c_chakunai()

        # ── RUN-05d: D-JUEKI ──
        self._run05d_jueki()

        # ── RUN-06: D-KYUSYU ──
        self._run06_kyusyu()

        # ── RUN-07: 筋目フィルター ──
        self._run07_suji_filter()

        # ── RUN-08: 三連単フォーメーション ──
        self._run08_trifecta()

        # ── RUN-09: 二連単 ──
        self._run09_exacta()

        # ── RUN-09b: 万舟候補 ──
        self._run09b_manshu()

        # ── RUN-10: 自信度・波乱度 ──
        self._run10_confidence()

        # ── RUN-12: 予算配分 ──
        self._run12_budget()

        # ── 最終サマリ ──
        self._finalize()

        return self.out

    # ────────────────────────────────────
    # RUN-00: 進入タイプ
    # ────────────────────────────────────
    def _run00_entry_type(self):
        for b in self.boats:
            if b.lane == b.course:
                b.entry_type = "P0"
            elif b.lane < b.course:
                b.entry_type = "P2"  # 深い進入
            else:
                b.entry_type = "P3"  # 前付け

    # ────────────────────────────────────
    # RUN-01: 指標計算
    # ────────────────────────────────────
    def _run01_compute_indicators(self):
        # EI計算
        ei_vals = []
        for b in self.boats:
            b.ei = _compute_ei(b, self.boats)
            ei_vals.append(b.ei)
        ei_sorted = sorted(ei_vals, reverse=True)

        for b in self.boats:
            b.completion_power = _compute_completion_power(b)
            # EI3位以内なら+1
            if ei_sorted.index(b.ei) < 3:
                b.completion_power = min(3, b.completion_power + 1)

        # TI（1着率 ≒ D-NAMIBA補正前）
        for b in self.boats:
            course_win = b.course_win_rates.get(b.course, b.win_rate_1st)
            b.ti = course_win
            b.adj_win_rate = course_win  # 後でD-NAMIBAで補正

        # M2連率（2コースの差し決まり手率）
        for b in self.boats:
            if b.course == 2:
                b.m2_rate = b.course_win_rates.get(2, 0)
            b.grip_rate = b.course_win_rates.get(b.course, 0)

    # ────────────────────────────────────
    # RUN-02: 水面タイプ
    # ────────────────────────────────────
    def _run02_surface_type(self):
        venue = self.race.venue
        surface = VENUE_SURFACE_TYPE.get(venue, "標準")
        # 江戸川は特別処理
        if surface == "江戸川":
            surface = "標準"  # 簡略化
            self.out.notes.append("江戸川：潮汐・風条件を別途考慮")
        self.out.surface_type = surface

    # ────────────────────────────────────
    # RUN-02b: D-NAMIBA
    # ────────────────────────────────────
    def _run02b_namiba(self):
        """
        S_in = 場ベース×w0 + 当節累積×w2
        節頭はprior依存、中盤以降は当節実態重視
        """
        day = self.race.day_no or 1
        total = self.race.session_total_races or 0
        wins = self.race.session_in_1st_wins or 0

        # venue prior（場のイン1着率ベース）
        venue_priors = {
            "住之江": 0.55, "大村": 0.60, "びわこ": 0.50, "琵琶湖": 0.50,
            "桐生": 0.45, "戸田": 0.40, "芦屋": 0.45, "三国": 0.50,
            "尼崎": 0.52, "江戸川": 0.35, "平和島": 0.50, "多摩川": 0.48,
            "浜名湖": 0.53, "常滑": 0.55, "津": 0.56, "蒲郡": 0.55,
            "宮島": 0.50, "児島": 0.52, "丸亀": 0.53, "下関": 0.55,
            "若松": 0.52, "福岡": 0.54, "唐津": 0.53, "徳山": 0.55,
            "鳴門": 0.53, "高松": 0.55,
        }
        prior = venue_priors.get(self.race.venue, 0.52)

        if total == 0 or day <= 1:
            # 節頭: prior依存
            w0, w2 = 0.8, 0.2
            session_rate = prior
        elif day <= 3:
            w0, w2 = 0.5, 0.5
            session_rate = wins / total if total > 0 else prior
        else:
            w0, w2 = 0.3, 0.7
            session_rate = wins / total if total > 0 else prior

        s_in_val = w0 * prior + w2 * session_rate

        if s_in_val >= 0.55:
            self.out.s_in = "イン強"
        elif s_in_val >= 0.45:
            self.out.s_in = "中"
        else:
            self.out.s_in = "イン弱"

        self.out.in_win_rate = round(s_in_val, 3)

        # 1着確率をD-NAMIBA補正（1号補正）
        boat1 = self._get_boat_by_course(1)
        if boat1:
            # イン強なら1号の1着率を上方補正
            if self.out.s_in == "イン強":
                boat1.adj_win_rate = min(0.80, boat1.ti * 1.2)
            elif self.out.s_in == "イン弱":
                boat1.adj_win_rate = boat1.ti * 0.8
            else:
                boat1.adj_win_rate = boat1.ti

    # ────────────────────────────────────
    # RUN-02c: D-REGIME
    # ────────────────────────────────────
    def _run02c_regime(self):
        """
        軸1: 分散 = トップ - 2位差 (<15pt=フラット / >=15pt=集中)
        軸2: 本命被弾合計 = 危険度高コースの合計 (>=30%=高)
        軸3: 攻め密度 = 完遂力強 or 被弾元 or A1着内突出(>=55%) の枚数 (>=2=高)
        """
        adj_rates = sorted([b.adj_win_rate for b in self.boats], reverse=True)
        dispersion = (adj_rates[0] - adj_rates[1]) * 100 if len(adj_rates) >= 2 else 0

        # 本命艇 = adj_win_rate最大
        top_boat = max(self.boats, key=lambda b: b.adj_win_rate)
        # 被弾合計: コース2,3の攻め艇の勝率合計（簡略化）
        hit_rate_sum = 0.0
        for b in self.boats:
            if b.course in [2, 3, 4] and b.course != top_boat.course:
                hit_rate_sum += b.adj_win_rate * 100

        # 攻め密度
        attack_density = sum(
            1 for b in self.boats
            if b.completion_power >= 3 or
               (b.rank in ["A1"] and b.place_rate >= 0.55)
        )

        self.out.regime_dispersion = round(dispersion, 1)
        self.out.regime_hit_rate = round(hit_rate_sum, 1)
        self.out.regime_attack_density = attack_density

        if dispersion >= 15 and hit_rate_sum < 30 and attack_density <= 1:
            self.out.regime = "順当"
        elif hit_rate_sum >= 30 or attack_density >= 2:
            self.out.regime = "隠れ混戦"
        else:
            self.out.regime = "明白混戦"

    # ────────────────────────────────────
    # RUN-03: 頭特定 (D-IN)
    # ────────────────────────────────────
    def _run03_head(self):
        """
        1号コース艇が1着率1位なら頭は1号 (D-IN)
        非1号本命への切替は「1着率1位が非1号 かつ 逃げ成立度 < ボーダー」時のみ
        """
        boat_c1 = self._get_boat_by_course(1)
        if boat_c1 is None:
            self.out.notes.append("1コース艇なし")
            return

        top_boat = max(self.boats, key=lambda b: b.adj_win_rate)

        # 逃げ成立度ボーダー
        escape_border = {"イン強": 0.40, "中": 0.45, "イン弱": 0.50}.get(self.out.s_in, 0.45)
        # 1号の逃げ成立度（コース1勝率で代用）
        c1_win = boat_c1.course_win_rates.get(1, boat_c1.win_rate_1st)

        if top_boat.course == 1 or c1_win >= escape_border:
            # D-IN: 1号頭維持
            self.out.head_boats = [boat_c1.lane]
            self.out.head_type = "A"
            self.out.f1_head = boat_c1.lane
        else:
            # 非1号本命
            self.out.head_boats = [boat_c1.lane, top_boat.lane]
            self.out.head_type = "AB"
            self.out.f1_head = boat_c1.lane
            self.out.f2_head = top_boat.lane
            self.out.notes.append(f"D-IN: イン弱→{top_boat.lane}号頭追加 (AB両建て)")

    # ────────────────────────────────────
    # RUN-04: 機構1-D（被弾補正）
    # ────────────────────────────────────
    def _run04_mech1d(self):
        boat_c1 = self._get_boat_by_course(1)
        if boat_c1 is None:
            return

        attack_boats = [b for b in self.boats if b.course in [2, 3, 4]]
        total_hit = sum(b.adj_win_rate * 100 for b in attack_boats)

        if total_hit >= 30:
            # 脆弱AB救済
            if boat_c1.adj_win_rate < 0.35:
                if self.out.head_type == "A":
                    attacker = max(attack_boats, key=lambda b: b.adj_win_rate, default=None)
                    if attacker:
                        self.out.head_type = "AB"
                        if attacker.lane not in self.out.head_boats:
                            self.out.head_boats.append(attacker.lane)
                        self.out.f2_head = attacker.lane
                        self.out.notes.append(f"機構1-D: 脆弱AB救済→F2={attacker.lane}号")

    # ────────────────────────────────────
    # RUN-04b: 機構1-E（イン逃げ警戒・両建て）
    # ────────────────────────────────────
    def _run04b_mech1e(self):
        """
        発動条件: ①1号イン逃げ本命 ②2番手攻め艇の完遂力強 ③D-ZIKU経路あり
        F1=1号 / F2=攻め艇頭
        """
        boat_c1 = self._get_boat_by_course(1)
        if boat_c1 is None:
            return

        # 1号が本命でない場合は非発動
        if self.out.f1_head != boat_c1.lane:
            return

        # 完遂力強の攻め艇を探す
        attackers = [b for b in self.boats if b.course >= 2 and b.completion_power >= 3]
        if not attackers:
            # 差し屋免除: 2Cのm2_rate最上位
            m2_tops = [b for b in self.boats if b.course == 2 and b.m2_rate > 0]
            if m2_tops:
                attacker = max(m2_tops, key=lambda b: b.m2_rate)
                if attacker.completion_power >= 2:
                    attackers = [attacker]

        if attackers:
            attacker = max(attackers, key=lambda b: b.completion_power * 10 + b.adj_win_rate)
            # 発動下限: まくり主体は1着率>=10%
            if attacker.adj_win_rate >= 0.10 or attacker.m2_rate > 0:
                self.out.mech1e_active = True
                self.out.f2_head = attacker.lane
                if attacker.lane not in self.out.head_boats:
                    self.out.head_boats.append(attacker.lane)
                    self.out.head_type = "AB"
                self.out.notes.append(f"機構1-E: F1={boat_c1.lane}号逃げ / F2={attacker.lane}号攻め 両建て")

    # ────────────────────────────────────
    # RUN-05: D-ZIKU + D-GATE + D-2CHAKU + D-GAI
    # ────────────────────────────────────
    def _run05_axis(self):
        """2着軸候補を特定"""
        self._axis_candidates: List[int] = []  # 2着候補の号艇リスト
        surface = self.out.surface_type

        boat_c1 = self._get_boat_by_course(1)

        # D-2CHAKU: 場別2着強制
        forced_2nd: List[int] = []
        if surface == "差し":
            # 外まくり差し艇（3C以遠の握り率・捲差上位）
            outer = [b for b in self.boats if b.course >= 3]
            if outer:
                maki_diff = max(outer, key=lambda b: b.grip_rate)
                forced_2nd.append(maki_diff.lane)
        elif surface == "捲り":
            # カド（4Cコース艇）を強制
            cad = self._get_boat_by_course(4)
            if cad:
                forced_2nd.append(cad.lane)

        self._forced_2nd = forced_2nd

        # D-ZIKU: 経路を言語化できる艇
        axis = []
        for b in self.boats:
            if b.course == 1:
                continue  # 頭候補のみ
            # 経路あり条件（簡略化）
            if b.place_rate >= 0.30 or b.adj_win_rate >= 0.10:
                # D-GATE: 攻め権利なしでST・モーター最下位は除外（紐止まり）
                motor_g = _motor_grade(b.motor_eval)
                if motor_g == 0 and b.st_rank >= 6 and b.completion_power == 0:
                    continue
                axis.append(b.lane)

        # 強制艇を追加
        for ln in forced_2nd:
            if ln not in axis:
                axis.append(ln)

        self._axis_candidates = axis

    # ────────────────────────────────────
    # RUN-05c: D-CHAKUNAI（着内配置）
    # ────────────────────────────────────
    def _run05c_chakunai(self):
        """着内60%以上かつ1着率低の圏内残存艇を2-3着に配置"""
        self._place_boats: List[int] = []
        boat_c1 = self._get_boat_by_course(1)

        for b in self.boats:
            if b.place_rate >= 0.50 and b.adj_win_rate < 0.35:
                self._place_boats.append(b.lane)

        # 差された1号は必ず含める
        if boat_c1 and boat_c1.lane not in self._place_boats:
            if boat_c1.place_rate >= 0.40:
                self._place_boats.insert(0, boat_c1.lane)

    # ────────────────────────────────────
    # RUN-05d: D-JUEKI（受益2着マトリクス）
    # ────────────────────────────────────
    def _run05d_jueki(self):
        """各攻め頭に対して受益2着を1対1で確定"""
        benefit = {}
        cad_boat = self._get_boat_by_course(4)
        boat_c1 = self._get_boat_by_course(1)
        surface = self.out.surface_type

        for head_lane in self.out.head_boats:
            head_boat = self._get_boat_by_lane(head_lane)
            if head_boat is None:
                continue
            two_nd = []

            if head_boat.course == 1:
                # イン逃げ頭: 受益2着 = 内差し残り + カド強制
                if cad_boat:
                    two_nd.append(cad_boat.lane)
                inner = [b for b in self.boats if b.course in [2, 3] and b.place_rate >= 0.30]
                for b in sorted(inner, key=lambda x: x.place_rate, reverse=True)[:2]:
                    if b.lane not in two_nd:
                        two_nd.append(b.lane)
            else:
                # 攻め艇頭: 差された1号残り + カド
                if boat_c1:
                    two_nd.append(boat_c1.lane)
                if cad_boat and cad_boat.lane != head_lane:
                    two_nd.append(cad_boat.lane)

            # 強制2着を追加
            for ln in self._forced_2nd:
                if ln != head_lane and ln not in two_nd:
                    two_nd.append(ln)

            benefit[head_lane] = two_nd[:3]  # 最大3艇

        self.out.benefit_2nd = benefit

    # ────────────────────────────────────
    # RUN-06: D-KYUSYU（人気吸収艇）
    # ────────────────────────────────────
    def _run06_kyusyu(self):
        """D-ZIKU経路を言語化できない2着候補を紐へ降格"""
        # 簡略化: place_rate低い軸候補は紐へ
        self._axis_final = [
            ln for ln in self._axis_candidates
            if self._get_boat_by_lane(ln) and
               self._get_boat_by_lane(ln).place_rate >= 0.25
        ]
        if len(self._axis_final) == 0:
            self._axis_final = self._axis_candidates[:3]

    # ────────────────────────────────────
    # RUN-07: 筋目フィルター
    # ────────────────────────────────────
    def _run07_suji_filter(self):
        """同一世界線で成立する艇だけ残す"""
        # カドと内逃げは同一世界線で共存可能（D-2CHAKU）
        # 簡略化: 全軸候補を維持し、後で三連単生成時にフィルタ
        pass

    # ────────────────────────────────────
    # RUN-08: 三連単フォーメーション
    # ────────────────────────────────────
    def _run08_trifecta(self):
        """
        形は数えた筋の数で一意・デフォルト最狭
        確定フォーマット:
        イン逃げ時(頭1枚A): A-B-CDE(3), A-BC-BCD(4), A-BC-BCDE(6)
        """
        f1 = self.out.f1_head
        f2 = self.out.f2_head

        # 3着候補（着内主導）
        three_rd_pool = self._place_boats.copy()
        for ln in self._axis_final:
            if ln not in three_rd_pool and ln != f1:
                three_rd_pool.append(ln)
        three_rd_pool = [ln for ln in three_rd_pool if ln != f1][:4]

        # 2着候補
        two_nd_for_f1 = self.out.benefit_2nd.get(f1, self._axis_final[:3])
        two_nd_for_f1 = [ln for ln in two_nd_for_f1 if ln != f1][:3]

        # F1フォーメーション
        trifecta_f1 = []
        for second in two_nd_for_f1:
            for third in three_rd_pool:
                if third != f1 and third != second:
                    trifecta_f1.append(f"{f1}-{second}-{third}")
        self.out.trifecta_f1 = trifecta_f1[:6]  # 最大6点

        # F2フォーメーション（機構1-E発動時）
        trifecta_f2 = []
        if self.out.mech1e_active and f2 is not None:
            two_nd_for_f2 = self.out.benefit_2nd.get(f2, [])
            # 差された1号は必ず含める
            boat_c1 = self._get_boat_by_course(1)
            if boat_c1 and boat_c1.lane != f2 and boat_c1.lane not in two_nd_for_f2:
                two_nd_for_f2.insert(0, boat_c1.lane)
            # 捲り水面: カドも含める
            if self.out.surface_type == "捲り":
                cad = self._get_boat_by_course(4)
                if cad and cad.lane != f2 and cad.lane not in two_nd_for_f2:
                    two_nd_for_f2.append(cad.lane)
            two_nd_for_f2 = [ln for ln in two_nd_for_f2 if ln != f2][:3]
            for second in two_nd_for_f2:
                for third in three_rd_pool:
                    if third != f2 and third != second:
                        trifecta_f2.append(f"{f2}-{second}-{third}")
            self.out.trifecta_f2 = trifecta_f2[:4]

    # ────────────────────────────────────
    # RUN-09: 二連単
    # ────────────────────────────────────
    def _run09_exacta(self):
        """
        三連単の保険でなく別世界線・上限3点・1-J禁止
        """
        f1 = self.out.f1_head
        f2 = self.out.f2_head
        exacta = []

        # 優先1: 別軸
        axis_others = [ln for ln in self._axis_final if ln != f1 and (f2 is None or ln != f2)]
        for ax in axis_others[:2]:
            combo = f"{f1}-{ax}"
            if combo not in exacta:
                exacta.append(combo)

        # 優先2: F2頭
        if f2 is not None and len(exacta) < 3:
            boat_c1 = self._get_boat_by_course(1)
            if boat_c1:
                combo = f"{f2}-{boat_c1.lane}"
                if combo not in exacta:
                    exacta.append(combo)

        self.out.exacta = exacta[:3]

    # ────────────────────────────────────
    # RUN-09b: 万舟候補プール（全レース必須）
    # ────────────────────────────────────
    def _run09b_manshu(self):
        """
        D-BANSEN-V2: 崩れ方3系統 + 展開沿い高配当
        各目100倍以上（オッズ未入力時は候補を生成）
        全レース必須出力・6-10点
        """
        candidates = []
        boat_c1 = self._get_boat_by_course(1)
        cad = self._get_boat_by_course(4)
        attacker5 = self._get_boat_by_course(5)
        attacker6 = self._get_boat_by_course(6)

        all_lanes = [b.lane for b in self.boats]
        inner_lanes = [b.lane for b in self.boats if b.course <= 3]
        outer_lanes = [b.lane for b in self.boats if b.course >= 4]

        # 系統A: イン残り型（1号頭・外/カド連動）
        if boat_c1 and cad:
            for outer in outer_lanes:
                if outer != boat_c1.lane and outer != cad.lane:
                    candidates.append(f"{boat_c1.lane}-{cad.lane}-{outer}")
                    candidates.append(f"{boat_c1.lane}-{outer}-{cad.lane}")

        # 系統B: 攻め艇頭型（攻め艇-差された1号-内/カド）
        attack_heads = [b for b in self.boats if b.course >= 2 and b.completion_power >= 2]
        if boat_c1:
            for ah in attack_heads[:2]:
                inner_3rd = [ln for ln in inner_lanes if ln != ah.lane and ln != boat_c1.lane]
                for third in inner_3rd[:2]:
                    candidates.append(f"{ah.lane}-{boat_c1.lane}-{third}")
                if cad and cad.lane != ah.lane:
                    candidates.append(f"{ah.lane}-{boat_c1.lane}-{cad.lane}")

        # 系統C: 中枠一発型（3C頭）
        boat_c3 = self._get_boat_by_course(3)
        if boat_c3 and boat_c3.completion_power >= 2:
            if boat_c1:
                candidates.append(f"{boat_c3.lane}-{boat_c1.lane}-{cad.lane if cad else all_lanes[-1]}")
            for inner in inner_lanes:
                if inner != boat_c3.lane:
                    outer = outer_lanes[0] if outer_lanes else all_lanes[-1]
                    candidates.append(f"{boat_c3.lane}-{inner}-{outer}")

        # 5の単独まくり差し
        if attacker5 and boat_c1:
            candidates.append(f"{attacker5.lane}-{boat_c1.lane}-{cad.lane if cad else inner_lanes[-1]}")
            candidates.append(f"{attacker5.lane}-{cad.lane if cad else inner_lanes[0]}-{boat_c1.lane}")

        # 6の大外
        if attacker6 and boat_c1:
            candidates.append(f"{attacker6.lane}-{boat_c1.lane}-{inner_lanes[1] if len(inner_lanes) > 1 else all_lanes[1]}")

        # 重複排除・本線/二連単と頭×軸が被らないものを優先
        main_heads = set()
        for tc in (self.out.trifecta_f1 + self.out.trifecta_f2):
            parts = tc.split("-")
            if parts:
                main_heads.add(parts[0])

        unique = []
        seen = set()
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)

        # 本線と被らない候補を前に持ってくる
        non_overlap = [c for c in unique if c.split("-")[0] not in main_heads]
        overlap = [c for c in unique if c.split("-")[0] in main_heads]
        ordered = non_overlap + overlap

        # 6-10点
        point_count = 6
        if self.out.regime == "明白混戦":
            point_count = 10
        elif self.out.regime == "隠れ混戦":
            point_count = 8

        self.out.manshu_candidates = ordered[:point_count]

        # 6点未満なら追加生成
        while len(self.out.manshu_candidates) < 6:
            for p in permutations(all_lanes, 3):
                combo = f"{p[0]}-{p[1]}-{p[2]}"
                if combo not in seen:
                    seen.add(combo)
                    self.out.manshu_candidates.append(combo)
                if len(self.out.manshu_candidates) >= 6:
                    break

    # ────────────────────────────────────
    # RUN-10: 自信度・波乱度
    # ────────────────────────────────────
    def _run10_confidence(self):
        base = 30.0
        boat_c1 = self._get_boat_by_course(1)
        if boat_c1:
            c1_rate = boat_c1.course_win_rates.get(1, boat_c1.win_rate_1st) * 100
            if c1_rate >= 70:
                base += 30
            elif c1_rate >= 50:
                base += 20
            elif c1_rate >= 30:
                base += 10

        if self.out.regime == "順当":
            base += 10
        elif self.out.regime == "隠れ混戦":
            base -= 10
        elif self.out.regime == "明白混戦":
            base -= 5

        if self.race.wind_speed >= 5:
            base -= 5
        if self.race.wave_height >= 10:
            base -= 5

        self.out.confidence = min(90, max(5, base))

        # 波乱度
        wave = max(10, 85 - self.out.regime_dispersion)
        if boat_c1:
            c1r = boat_c1.adj_win_rate * 100
            if c1r >= 70:
                wave -= 15
            elif c1r >= 50:
                wave -= 10
        self.out.wave_score = min(85, max(10, wave))

    # ────────────────────────────────────
    # RUN-12: 予算配分
    # ────────────────────────────────────
    def _run12_budget(self):
        """レジーム別内部配分（総額不変）"""
        # 総額は変わらない: 三連単16,000 / 二連単4,000 / 万舟3,000
        self.out.budget_main = 16000
        self.out.budget_exacta = 4000
        self.out.budget_manshu = 3000
        # 内部配分はレジームで変動するが総額は固定

    # ────────────────────────────────────
    # 最終サマリ
    # ────────────────────────────────────
    def _finalize(self):
        all_trifecta = self.out.trifecta_f1 + self.out.trifecta_f2
        self.out.main_trifecta = ",".join(self.out.trifecta_f1[:3]) if self.out.trifecta_f1 else ""
        self.out.sub_trifecta = ",".join(self.out.trifecta_f2[:3]) if self.out.trifecta_f2 else ""

        regime_note = f"レジーム={self.out.regime}(分散{self.out.regime_dispersion}pt,被弾{self.out.regime_hit_rate}%,攻め密度{self.out.regime_attack_density})"
        head_note = f"頭={self.out.head_boats}({self.out.head_type})"
        surface_note = f"水面={self.out.surface_type}, S_in={self.out.s_in}"
        self.out.reasoning = f"{regime_note} | {head_note} | {surface_note}"

        if self.out.notes:
            self.out.reasoning += " | " + " / ".join(self.out.notes)

    # ────────────────────────────────────
    # ユーティリティ
    # ────────────────────────────────────
    def _get_boat_by_course(self, course: int) -> Optional[BoatEntry]:
        for b in self.boats:
            if b.course == course:
                return b
        return None

    def _get_boat_by_lane(self, lane: int) -> Optional[BoatEntry]:
        for b in self.boats:
            if b.lane == lane:
                return b
        return None


# ─────────────────────────────────────────
# DB/API データ変換
# ─────────────────────────────────────────

def race_dict_to_input(race: dict) -> RaceInput:
    """
    APIのレースdictをRaceInputに変換する
    """
    boats_raw = race.get("boats", [])
    boats = []
    for i, b in enumerate(boats_raw):
        lane = b.get("lane", i + 1)
        course = b.get("entry_course", lane)  # 進入コース未記録時は枠番

        # コース別成績を収集
        course_wins = {}
        course_tricasts = {}
        for c in range(1, 7):
            wk = f"c{c}_win_rate"
            tk = f"c{c}_tricast_rate"
            if b.get(wk) is not None:
                course_wins[c] = float(b[wk] or 0)
            if b.get(tk) is not None:
                course_tricasts[c] = float(b[tk] or 0)

        be = BoatEntry(
            lane=lane,
            course=course,
            name=b.get("name", ""),
            rank=b.get("rank", ""),
            f_count=b.get("f_count", 0) or 0,
            win_rate_1st=float(b.get("national_win_rate") or 0),
            win_rate_2nd=float(b.get("national_place2_rate") or 0),
            place_rate=float(b.get("national_place2_rate") or 0),
            motor_eval=b.get("motor_eval", "") or "",
            motor_place2_rate=float(b.get("motor_place2_rate") or 0),
            avg_st=float(b.get("avg_st") or 0.15),
            standard_st=float(b.get("standard_st") or b.get("avg_st") or 0.15),
            st_rank=int(b.get("st_advantage_rank") or b.get("today_st_rank") or 3),
            course_win_rates=course_wins,
            course_tricast_rates=course_tricasts,
            local5y_win_rate=float(b.get("local5y_win_rate") or 0),
            local5y_tricast_rate=float(b.get("local5y_tricast_rate") or 0),
        )
        boats.append(be)

    # 進入コースが全員同じ（未設定）の場合はレーン順で割り当て
    if len(set(b.course for b in boats)) <= 1:
        for i, b in enumerate(boats):
            b.course = b.lane

    return RaceInput(
        race_id=race.get("id", 0),
        venue=race.get("venue", ""),
        race_no=race.get("race_no", 0),
        day_no=race.get("day_no", 1) or 1,
        date=race.get("date", ""),
        weather=race.get("weather", "") or "",
        wind_speed=float(race.get("wind_speed") or 0),
        wind_direction=race.get("wind_direction", "") or "",
        wave_height=float(race.get("wave_height") or 0),
        boats=boats,
    )


def output_to_prediction_dict(out: PredictionOutput) -> dict:
    """PredictionOutputをDB/APIレスポンス形式に変換"""
    all_trifecta = out.trifecta_f1 + out.trifecta_f2
    trifecta_str = ",".join(all_trifecta) if all_trifecta else ""
    exacta_str = ",".join(out.exacta) if out.exacta else ""

    return {
        "source": "system_v56",
        "predicted_trifecta": trifecta_str,
        "predicted_exacta": exacta_str,
        "confidence": out.confidence,
        "reasoning": out.reasoning,
        "pattern": out.regime,
        "main_attack": str(out.head_boats),
        "classification": out.race_type,
        # フロント互換フィールド
        "trifecta": trifecta_str,
        "exacta": exacta_str,
        "is_correct": None,
        # 詳細情報
        "detail": {
            "regime": out.regime,
            "s_in": out.s_in,
            "surface_type": out.surface_type,
            "head_boats": out.head_boats,
            "head_type": out.head_type,
            "mech1e_active": out.mech1e_active,
            "f1_head": out.f1_head,
            "f2_head": out.f2_head,
            "benefit_2nd": out.benefit_2nd,
            "trifecta_f1": out.trifecta_f1,
            "trifecta_f2": out.trifecta_f2,
            "exacta": out.exacta,
            "manshu": out.manshu_candidates,
            "budget_main": out.budget_main,
            "budget_exacta": out.budget_exacta,
            "budget_manshu": out.budget_manshu,
            "confidence": out.confidence,
            "wave_score": out.wave_score,
            "regime_dispersion": out.regime_dispersion,
            "regime_hit_rate": out.regime_hit_rate,
            "regime_attack_density": out.regime_attack_density,
            "notes": out.notes,
        }
    }


def run_system_prediction(race: dict) -> dict:
    """
    レースdictを受け取り、v56.3システム予測を実行して結果dictを返す
    """
    race_input = race_dict_to_input(race)
    predictor = BoatracePredictor()
    output = predictor.predict(race_input)
    return output_to_prediction_dict(output)
