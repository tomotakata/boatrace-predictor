"""
競艇予想AI v58.7 — ダッシュボード生成ロジック（決定論的Python実装）

data/dashgen_logic_full.md の計算ロジックを忠実に実装。
同じ出走表からは毎回同一のダッシュボードが出る（乱数・時刻依存なし）。

Step 1-1: 基盤モジュール + ステップ①-⑤
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════
# 共通定数
# ═══════════════════════════════════════════════════════════

CLASS_VAL: Dict[str, int] = {"A1": 4, "A2": 3, "B1": 2, "B2": 1}
SCORE_MAP: List[int] = [100, 80, 60, 40, 20, 0]


# ═══════════════════════════════════════════════════════════
# ユーティリティ関数
# ═══════════════════════════════════════════════════════════

def desc_score(values: List[float]) -> List[int]:
    """値が大きいほど上位。順位=(自分より大きい個数)+1 → SCORE_MAP に変換。

    同点タイ・次順位スキップ。6要素前提。
    """
    n = len(values)
    scores: List[int] = []
    for i in range(n):
        rank = sum(1 for j in range(n) if values[j] > values[i]) + 1
        idx = min(rank - 1, len(SCORE_MAP) - 1)
        scores.append(SCORE_MAP[idx])
    return scores


def asc_rank(values: List[float]) -> List[int]:
    """小さいほど1位。順位=(自分より小さい個数)+1。"""
    n = len(values)
    ranks: List[int] = []
    for i in range(n):
        rank = sum(1 for j in range(n) if values[j] < values[i]) + 1
        ranks.append(rank)
    return ranks


def _shrink(rate: float, n: int) -> float:
    """ベイズ的シュリンク: 標本数 n が小さい率を平均(2000/20=100%相当)へ縮小。"""
    return (rate * n + 2000) / (n + 20)


def f_keisu1(f_status: Optional[str]) -> float:
    """事故F補正。

    F2(未未)→0.78 / F1未→0.86 / F1済→0.93 / 無→1.00
    f_status: "F2" / "F1未" / "F1済" / None or ""
    """
    if not f_status:
        return 1.00
    s = str(f_status).upper().strip()
    if s == "F2" or s == "F2未未":
        return 0.78
    if "F1" in s and "未" in s and "済" not in s:
        return 0.86
    if "F1" in s and "済" in s:
        return 0.93
    if s.startswith("F"):
        return 0.86
    return 1.00


def season_of(month: int) -> str:
    """季節判定: 6-8月=summer / 9-11月=autumn / 12,1,2月=winter / それ以外=spring。"""
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    if month in (12, 1, 2):
        return "winter"
    return "spring"


def rnum_band(r: int) -> str:
    """R番号帯判定: 1-4 / 5-6 / 7 / 8 / 9-11 / 12。"""
    if 1 <= r <= 4:
        return "1-4"
    if 5 <= r <= 6:
        return "5-6"
    if r == 7:
        return "7"
    if r == 8:
        return "8"
    if 9 <= r <= 11:
        return "9-11"
    if r == 12:
        return "12"
    return "_"


# ═══════════════════════════════════════════════════════════
# 会場別設定 VENUES（全24会場）
# ═══════════════════════════════════════════════════════════

VENUES: Dict[str, Dict[str, Any]] = {
    "蒲郡": {
        "base_wr": {1: 55.3, 2: 12.1, 3: 12.7, 4: 12.2, 5: 6.0, 6: 1.6},
        "base_ei": {1: 55, 2: 49, 3: 51, 4: 53, 5: 45, 6: 38},
        "base_1c_wr": {"_": 55.3},
        "k_b": 0.45,
        "mot_w": (0.45, 0.55),
        "rider_max": 2.0,
        "use_rnum": True,
        "floor_basis": "rnum",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.1, 4: 1.2, 5: 1.1, 6: 1.05},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"1-4": 0.35, "5-6": 0.42, "7": 0.55, "8": 0.52,
                        "9-11": 0.6, "12": 0.72, "_": 0.45},
    },
    "びわこ": {
        "base_wr": {1: 53.5, 2: 14.7, 3: 13.4, 4: 11.1, 5: 5.8, 6: 1.4},
        "base_ei": {1: 65, 2: 62, 3: 58, 4: 55, 5: 44, 6: 36},
        "base_1c_wr": {"spring": 52.0, "summer": 53.0, "autumn": 55.0,
                        "winter": 55.0, "_": 53.5},
        "k_b": 0.55,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.6,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2},
        "nige_floor": {"spring": 0.38, "summer": 0.42, "autumn": 0.52,
                        "winter": 0.52, "_": 0.45},
    },
    "桐生": {
        "base_wr": {1: 52.8, 2: 13.0, 3: 13.0, 4: 13.0, 5: 7.0, 6: 2.0},
        "base_ei": {1: 58, 2: 48.0, 3: 50.0, 4: 52.0, 5: 47.0, 6: 40.0},
        "base_1c_wr": {"_": 52.8},
        "k_b": 0.55,
        "mot_w": (0.5, 0.5),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.1, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "戸田": {
        "base_wr": {1: 44.0, 2: 16.0, 3: 16.0, 4: 15.0, 5: 7.0, 6: 3.0},
        "base_ei": {1: 46.0, 2: 58.0, 3: 62.0, 4: 60.0, 5: 48.0, 6: 42.0},
        "base_1c_wr": {"_": 44.0},
        "k_b": 0.55,
        "mot_w": (0.45, 0.55),
        "rider_max": 1.3,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.1, 3: 1.3, 4: 1.2, 5: 1.1, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "江戸川": {
        "base_wr": {1: 42.0, 2: 15.0, 3: 12.0, 4: 11.0, 5: 7.0, 6: 5.0},
        "base_ei": {1: 50.0, 2: 58.0, 3: 55.0, 4: 48.0, 5: 42.0, 6: 36.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.55,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.35,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "多摩川": {
        "base_wr": {1: 54.3, 2: 14.0, 3: 13.0, 4: 12.0, 5: 5.0, 6: 3.0},
        "base_ei": {1: 60.0, 2: 50.0, 3: 50.0, 4: 53.0, 5: 45.0, 6: 40.0},
        "base_1c_wr": {"_": 54.6},
        "k_b": 0.45,
        "mot_w": (0.45, 0.55),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "浜名湖": {
        "base_wr": {1: 52.6, 2: 14.9, 3: 13.7, 4: 10.6, 5: 6.4, 6: 1.8},
        "base_ei": {1: 53.0, 2: 50.0, 3: 53.0, 4: 50.0, 5: 47.0, 6: 39.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.55,
        "mot_w": (0.55, 0.45),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "常滑": {
        "base_wr": {1: 57.0, 2: 12.0, 3: 9.0, 4: 11.0, 5: 6.0, 6: 2.0},
        "base_ei": {1: 62, 2: 48.0, 3: 45.0, 4: 52.0, 5: 45.0, 6: 38.0},
        "base_1c_wr": {"_": 57.0},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.1, 5: 1.05, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "津": {
        "base_wr": {1: 57.1, 2: 14.1, 3: 11.8, 4: 9.9, 5: 5.4, 6: 1.6},
        "base_ei": {1: 58.0, 2: 52.0, 3: 48.0, 4: 50.0, 5: 43.0, 6: 37.0},
        "base_1c_wr": {"_": 45.0},
        "k_b": 0.5,
        "mot_w": (0.5, 0.5),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.05, 4: 1.2, 5: 1.05, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "三国": {
        "base_wr": {1: 53.0, 2: 17.3, 3: 14.3, 4: 10.0, 5: 5.0, 6: 1.0},
        "base_ei": {1: 53.0, 2: 54.0, 3: 50.0, 4: 47.0, 5: 42.0, 6: 36.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.5,
        "mot_w": (0.55, 0.45),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 0.85, 3: 0.85, 4: 1.0, 5: 0.9, 6: 0.9},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "住之江": {
        "base_wr": {1: 60.7, 2: 13.0, 3: 11.0, 4: 9.0, 5: 5.0, 6: 2.0},
        "base_ei": {1: 62.0, 2: 55.0, 3: 51.0, 4: 49.0, 5: 44.0, 6: 38.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.35,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "尼崎": {
        "base_wr": {1: 60.0, 2: 9.0, 3: 11.0, 4: 8.0, 5: 7.0, 6: 3.0},
        "base_ei": {1: 63.0, 2: 48.0, 3: 50.0, 4: 50.0, 5: 46.0, 6: 40.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.35,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "丸亀": {
        "base_wr": {1: 56.1, 2: 15.1, 3: 11.9, 4: 9.0, 5: 7.3, 6: 2.4},
        "base_ei": {1: 56.0, 2: 60.0, 3: 58.0, 4: 52.0, 5: 50.0, 6: 40.0},
        "base_1c_wr": {"_": 56.0},
        "k_b": 0.45,
        "mot_w": (0.55, 0.45),
        "rider_max": 1.3,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.15, 4: 1.05, 5: 1.2, 6: 1.05},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "児島": {
        "base_wr": {1: 57.7, 2: 13.0, 3: 14.0, 4: 9.0, 5: 5.0, 6: 3.0},
        "base_ei": {1: 63, 2: 50.0, 3: 53.0, 4: 47.0, 5: 42.0, 6: 38.0},
        "base_1c_wr": {"_": 57.7},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 0.9, 5: 1.05, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "宮島": {
        "base_wr": {1: 53.0, 2: 15.0, 3: 12.0, 4: 11.0, 5: 6.0, 6: 3.0},
        "base_ei": {1: 56.0, 2: 50.0, 3: 50.0, 4: 52.0, 5: 45.0, 6: 40.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.5,
        "mot_w": (0.55, 0.45),
        "rider_max": 1.35,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "徳山": {
        "base_wr": {1: 63.0, 2: 14.3, 3: 9.1, 4: 8.3, 5: 4.2, 6: 0.9},
        "base_ei": {1: 63.0, 2: 51.0, 3: 47.0, 4: 47.0, 5: 43.0, 6: 35.0},
        "base_1c_wr": {"_": 63.0},
        "k_b": 0.4,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.3,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 0.85, 3: 1.0, 4: 1.05, 5: 1.05},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "下関": {
        "base_wr": {1: 60.5, 2: 11.6, 3: 10.5, 4: 9.5, 5: 5.6, 6: 2.2},
        "base_ei": {1: 62.0, 2: 58.0, 3: 52.0, 4: 48.0, 5: 44.0, 6: 38.0},
        "base_1c_wr": {"_": 60.5},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.6,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "若松": {
        "base_wr": {1: 57.3, 2: 12.0, 3: 12.0, 4: 10.0, 5: 7.0, 6: 2.0},
        "base_ei": {1: 57.0, 2: 55.0, 3: 52.0, 4: 48.0, 5: 42.0, 6: 36.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.5,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.6,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 0.95, 3: 1.15, 4: 0.95, 5: 0.95, 6: 0.95},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "芦屋": {
        "base_wr": {1: 62.0, 2: 11.0, 3: 11.0, 4: 10.0, 5: 5.0, 6: 1.4},
        "base_ei": {1: 65.0, 2: 47.0, 3: 50.0, 4: 53.0, 5: 44.0, 6: 38.0},
        "base_1c_wr": {"_": 45.0},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {3: 1.1, 4: 1.15, 5: 1.05, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "福岡": {
        "base_wr": {1: 55.0, 2: 15.4, 3: 14.9, 4: 9.4, 5: 4.1, 6: 1.0},
        "base_ei": {1: 58.0, 2: 52.0, 3: 54.0, 4: 46.0, 5: 40.0, 6: 35.0},
        "base_1c_wr": {"_": 55.0},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.35,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.1, 3: 1.1, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "大村": {
        "base_wr": {1: 63.1, 2: 12.0, 3: 12.0, 4: 7.0, 5: 5.0, 6: 1.0},
        "base_ei": {1: 64.0, 2: 52.0, 3: 48.0, 4: 42.0, 5: 38.0, 6: 32.0},
        "base_1c_wr": {"_": 53.0},
        "k_b": 0.4,
        "mot_w": (0.6, 0.4),
        "rider_max": 1.6,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "鳴門": {
        "base_wr": {1: 49.0, 2: 15.1, 3: 14.7, 4: 11.9, 5: 7.5, 6: 2.0},
        "base_ei": {1: 52.0, 2: 52.0, 3: 52.0, 4: 50.0, 5: 46.0, 6: 38.0},
        "base_1c_wr": {"_": 49.0},
        "k_b": 0.55,
        "mot_w": (0.45, 0.55),
        "rider_max": 1.3,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.08, 3: 1.1, 4: 1.1, 5: 1.1, 6: 1.05},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "平和島": {
        "base_wr": {1: 45.0, 2: 17.0, 3: 14.0, 4: 13.0, 5: 8.0, 6: 3.0},
        "base_ei": {1: 50, 2: 50.0, 3: 50.0, 4: 48.0, 5: 45.0, 6: 40.0},
        "base_1c_wr": {"_": 45.0},
        "k_b": 0.55,
        "mot_w": (5.0, 3.0),
        "rider_max": 2.0,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
    "唐津": {
        "base_wr": {1: 55.0, 2: 14.0, 3: 13.0, 4: 9.0, 5: 6.0, 6: 2.0},
        "base_ei": {1: 58.0, 2: 53.0, 3: 52.0, 4: 48.0, 5: 44.0, 6: 38.0},
        "base_1c_wr": {"_": 55.0},
        "k_b": 0.45,
        "mot_w": (0.5, 0.5),
        "rider_max": 1.6,
        "use_rnum": False,
        "floor_basis": "season",
        "kado": {3: 1.15, 4: 1.2, 5: 1.1},
        "core_mult": {2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0},
        "exploit_kado": {3: 1.1, 4: 1.2, 5: 1.1},
        "nige_floor": {"_": 0.45},
    },
}

# 未登録会場は蒲郡をデフォルトにする
DEFAULT_VENUE = "蒲郡"


def get_venue(venue_name: str) -> Dict[str, Any]:
    """会場設定を取得。未登録会場は蒲郡をデフォルトとする。"""
    return VENUES.get(venue_name, VENUES[DEFAULT_VENUE])


# ═══════════════════════════════════════════════════════════
# ① 基準ST (kijun_st)
# ═══════════════════════════════════════════════════════════

def kijun_st(
    average_st: float,
    course_average_st: float,
    current_st: float,
    day_no: int,
) -> float:
    """各艇の代表STを合成する。

    初日・2日目: avg*0.5 + course_avg*0.5
    3日目以降:   avg*0.4 + course_avg*0.3 + current*0.3
    小数3桁丸め。
    """
    if day_no <= 2:
        base = average_st * 0.5 + course_average_st * 0.5
    else:
        base = average_st * 0.4 + course_average_st * 0.3 + current_st * 0.3
    return round(base, 3)


# ═══════════════════════════════════════════════════════════
# ② 優勢順位D (yusei_rank)
# ═══════════════════════════════════════════════════════════

def yusei_rank(
    current_sts: List[float],
    average_sts: List[float],
    current_results: List[float],
    f_statuses: List[Optional[str]],
) -> List[int]:
    """STの強さ順位を算出する。

    Args:
        current_sts: 各艇(6)の今節ST
        average_sts: 各艇(6)の平均ST
        current_results: 各艇(6)の今節着順（平均着順）
        f_statuses: 各艇(6)のF事故ステータス

    Returns:
        各艇(6)の優勢順位D（1=最上位）
    """
    r_cur = asc_rank(current_sts)
    r_avg = asc_rank(average_sts)

    raw_scores: List[float] = []
    for i in range(6):
        stability = 1.0 - (current_results[i] - 1) * 0.05
        f_coef = f_keisu1(f_statuses[i])
        raw = (r_cur[i] * 0.40 + r_avg[i] * 0.35 + current_results[i] * 0.25)
        raw = raw * stability * f_coef
        raw_scores.append(raw)

    return asc_rank(raw_scores)


# ═══════════════════════════════════════════════════════════
# ③ モーター順位 (motor_rank)
# ═══════════════════════════════════════════════════════════

def motor_rank(
    deashi_list: List[float],
    nobi_list: List[float],
) -> Tuple[List[int], List[str]]:
    """モーター順位とランクを算出する。

    Args:
        deashi_list: 各艇(6)の出足評価値
        nobi_list: 各艇(6)の伸び足評価値

    Returns:
        (ranks, labels):
            ranks: 各艇(6)の降順順位（大きい=1位）
            labels: 各艇(6)のランク文字列 S/A/B/C/D
    """
    totals = [deashi_list[i] + nobi_list[i] for i in range(6)]

    # 降順順位: 大きいほど1位 → desc_scoreの順位付けロジックを使う
    n = len(totals)
    ranks: List[int] = []
    for i in range(n):
        rank = sum(1 for j in range(n) if totals[j] > totals[i]) + 1
        ranks.append(rank)

    labels: List[str] = []
    for t in totals:
        if t >= 11:
            labels.append("S")
        elif t >= 9:
            labels.append("A")
        elif t == 8:
            labels.append("B")
        elif t >= 6:
            labels.append("C")
        else:
            labels.append("D")

    return ranks, labels


# ═══════════════════════════════════════════════════════════
# ④ 握り率 (nigiri_rate)
# ═══════════════════════════════════════════════════════════

def nigiri_rate(
    course: int,
    makuri: int,
    makurizashi: int,
    race_count: int,
) -> Optional[float]:
    """握り率を算出する。

    1号はNone。出走数<5は50.0固定。
    DBカラム名: makurizashi → c{n}_makurizashi

    Args:
        course: コース番号 (1-6)
        makuri: まくり回数
        makurizashi: まくり差し回数
        race_count: 出走数

    Returns:
        握り率(%) or None (1号の場合)
    """
    if course == 1:
        return None
    if race_count < 5:
        return 50.0
    return (makuri + makurizashi) / race_count * 100


# ═══════════════════════════════════════════════════════════
# ⑤ 捲り完遂力差 g (makuri_g)
# ═══════════════════════════════════════════════════════════

def makuri_g(
    base_sts: List[float],
    deashi_list: List[float],
    nobi_list: List[float],
    class_labels: List[str],
    mot_w: Tuple[float, float],
    target: int = 0,
) -> List[Optional[float]]:
    """外艇 c が頭(target=1号)を捲り切る力差を算出する。

    Args:
        base_sts: 各艇(6)の基準ST (①の出力)
        deashi_list: 各艇(6)の出足評価値
        nobi_list: 各艇(6)の伸び足評価値
        class_labels: 各艇(6)の級別 ("A1","A2","B1","B2")
        mot_w: (出足重み, 伸び足重み) 会場設定
        target: ターゲット艇のインデックス (0=1号)

    Returns:
        各艇(6)のg値。1号(target)はNone。
    """
    dw, nw = mot_w

    de = desc_score(deashi_list)
    no = desc_score(nobi_list)
    mscore = [de[i] * dw + no[i] * nw for i in range(6)]

    t = target
    result: List[Optional[float]] = []
    for i in range(6):
        if i == t:
            result.append(None)
            continue

        st_diff = (base_sts[t] - base_sts[i]) / 0.03
        mot_diff = (mscore[i] - mscore[t]) / 100
        cls_c = CLASS_VAL.get(class_labels[i], 2)
        cls_t = CLASS_VAL.get(class_labels[t], 2)
        cls_diff = (cls_c - cls_t) / 3

        diff = 0.40 * st_diff + 0.35 * mot_diff + 0.25 * cls_diff
        g = max(0.0, min(1.30, 0.5 + diff))
        result.append(round(g, 4))

    return result
