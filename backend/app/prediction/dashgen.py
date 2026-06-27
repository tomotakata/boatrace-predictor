"""
競艇予想AI v58.7 — ダッシュボード生成ロジック（決定論的Python実装）

data/dashgen_logic_full.md の計算ロジックを忠実に実装。
同じ出走表からは毎回同一のダッシュボードが出る（乱数・時刻依存なし）。

Step 1-1: 基盤モジュール + ステップ①-⑤
Step 1-2: ステップ⑥-⑧ EI計算ロジック
Step 1-3: ステップ⑨-⑫ P1・被弾分析・減衰・逃げ成立度
"""

from __future__ import annotations

import math
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


# ═══════════════════════════════════════════════════════════
# EI 定数
# ═══════════════════════════════════════════════════════════

EI_W: Dict[str, float] = {
    "A": 1.05, "B": 0.95, "C": 0.85,
    "D": 1.55, "F": 1.65, "G": 1.20, "H": 0.90,
}

# コース係数 J (0-indexed: コース1→index 0)
_J_COEF: List[float] = [1.08, 1.04, 1.02, 1.00, 0.95, 0.89]

# 枠補正テーブル I: (級別, コース1-indexed) → 補正値
# 仕様書「級別×枠の枠補正テーブル（例 A1の4枠 −4 / B1の1枠 +12 …）」
# 典型的な競艇EI枠補正テーブルを仕様例から構成
_FRAME_BONUS: Dict[str, Dict[int, int]] = {
    "A1": {1: 8, 2: 2, 3: 0, 4: -4, 5: -6, 6: -8},
    "A2": {1: 10, 2: 3, 3: 0, 4: -3, 5: -5, 6: -7},
    "B1": {1: 12, 2: 4, 3: 1, 4: -2, 5: -4, 6: -6},
    "B2": {1: 10, 2: 3, 3: 0, 4: -2, 5: -4, 6: -5},
}

# 捲り加算 M: コース(1-indexed) → 加算値 (4-6号のみ)
_M_BONUS: Dict[int, int] = {4: 6, 5: 6, 6: 8}


# ═══════════════════════════════════════════════════════════
# f_keisu3: 事故F×ST乖離の追加ペナルティ
# ═══════════════════════════════════════════════════════════
# 仕様書に明示的な段階値定義がないため、以下のように推定実装:
# - F事故なし → 1.00 (ペナルティなし)
# - F事故あり かつ ST乖離(base_st - average_st)が大きい → 追加ペナルティ
#   ST乖離 = base_st - 全艇平均base_st (正=遅い=乖離大)
# 根拠: f_keisu1がF事故の基本ペナルティ、f_keisu3はSTが不安定な
#        F持ち選手への追加減衰。乖離が大きいほどスタート不安定。

def f_keisu3(f_status: Optional[str], st_deviation: float) -> float:
    """事故F×ST乖離の追加ペナルティ係数。

    Args:
        f_status: F事故ステータス ("F2"/"F1未"/"F1済"/None)
        st_deviation: ST乖離 (base_st - 全艇平均base_st)。正=遅い。

    Returns:
        補正係数 (0.80〜1.00)
    """
    if not f_status:
        return 1.00
    s = str(f_status).upper().strip()
    if not s.startswith("F"):
        return 1.00
    # F事故ありの場合、ST乖離に応じた追加ペナルティ
    # 乖離が 0.05秒以上遅い → 0.90、0.10秒以上 → 0.85、0.15秒以上 → 0.80
    # 乖離が小さい/速い → ペナルティ軽微
    if st_deviation >= 0.15:
        return 0.80
    if st_deviation >= 0.10:
        return 0.85
    if st_deviation >= 0.05:
        return 0.90
    if st_deviation >= 0.02:
        return 0.95
    return 1.00


# ═══════════════════════════════════════════════════════════
# ⑥ pre_EI / ei_components
# ═══════════════════════════════════════════════════════════

def ei_components(
    course: int,
    course_top3_rate: float,
    course_race_count: int,
    local_top3_rate: float,
    local_race_count: int,
    general_top3_rate: Optional[float],
    general_race_count: Optional[int],
    yusei_rank_d: int,
    deashi_list: List[float],
    nobi_list: List[float],
    is_seasonal_motor: bool,
    nigiri_rate_val: Optional[float],
    nigiri_hassei_val: Optional[float],
    class_label: str,
    age: int,
) -> Dict[str, float]:
    """EI成分 A-H を算出する。

    Args:
        course: コース番号 (1-6)
        course_top3_rate: コース3連率(%)
        course_race_count: コース出走数
        local_top3_rate: 当地3連率(%)
        local_race_count: 当地出走数
        general_top3_rate: 一般戦3連率(%) (Noneなら A で代替)
        general_race_count: 一般戦出走数
        yusei_rank_d: 優勢順位D (1-6)
        deashi_list: 全6艇の出足評価値
        nobi_list: 全6艇の伸び足評価値
        is_seasonal_motor: 季節モーター時か
        nigiri_rate_val: 握り率(%) (1号はNone)
        nigiri_hassei_val: 握り発生率(%) (1号はNone, pre_EI時はNone)
        class_label: 級別 ("A1"/"A2"/"B1"/"B2")
        age: 年齢

    Returns:
        {"A": ..., "B": ..., ..., "H": ...}
    """
    # A: コース3連率のシュリンク
    a = _shrink(course_top3_rate, course_race_count)

    # B: 当地3連率のシュリンク
    b = _shrink(local_top3_rate, local_race_count)

    # C: 一般戦3連率のシュリンク (無ければAで代替)
    if general_top3_rate is not None and general_race_count is not None:
        c = _shrink(general_top3_rate, general_race_count)
    else:
        c = a

    # D: 優勢順位Dのスコア化
    d_idx = min(yusei_rank_d - 1, len(SCORE_MAP) - 1)
    d = float(SCORE_MAP[d_idx])

    # F: モーター (desc_score)
    de_scores = desc_score(deashi_list)
    no_scores = desc_score(nobi_list)
    idx = course - 1
    f_val = de_scores[idx] * 0.45 + no_scores[idx] * 0.55
    if is_seasonal_motor:
        f_val *= 0.85

    # G: 攻め力
    if course == 1:
        g = 0.0
    else:
        nr = nigiri_rate_val if nigiri_rate_val is not None else 0.0
        nh = nigiri_hassei_val if nigiri_hassei_val is not None else 0.0
        g = min(nr * 0.45 + nh * 0.55, 90.0)

    # H: 級別/年齢
    cl = class_label.upper().strip()
    if cl == "A1":
        h = 95.0
    elif cl == "A2":
        h = 75.0
    elif cl == "B1":
        h = 55.0
    else:  # B2
        h = 45.0 if age <= 30 else 40.0

    return {"A": a, "B": b, "C": c, "D": d, "F": f_val, "G": g, "H": h}


def ei_full(
    components: Dict[str, float],
    include_g: bool,
    course: int,
    current_result: float,
    f_status: Optional[str],
    base_sts: List[float],
    local_top3_rate: float,
    course_top3_rate: float,
    local_race_count: int,
    class_label: str,
    is_local_aichi: bool,
    nobi_desc_score: float,
    nigiri_hassei_val: Optional[float],
) -> int:
    """EI最終値を算出する。

    Args:
        components: ei_components の出力
        include_g: Gを含めるか (False=pre_EI, True=最終EI)
        course: コース番号 (1-6)
        current_result: 今節着順（平均着順）
        f_status: F事故ステータス
        base_sts: 全6艇の基準ST
        local_top3_rate: 当地3連率(%)
        course_top3_rate: コース3連率(%)
        local_race_count: 当地出走数
        class_label: 級別
        is_local_aichi: 地元(愛知)か
        nobi_desc_score: 伸び足のdesc_score値
        nigiri_hassei_val: 握り発生率(%) (pre_EI時はNone)

    Returns:
        EI値 (整数)
    """
    # base = 加重平均
    keys = ["A", "B", "C", "D", "F", "G", "H"]
    if not include_g:
        keys = [k for k in keys if k != "G"]

    numerator = sum(components[k] * EI_W[k] for k in keys)
    denominator = sum(EI_W[k] for k in keys)
    base = numerator / denominator

    # J: コース係数
    j = _J_COEF[course - 1]

    # K: 着順安定
    k = max(0.80, min(1.00, 1.0 - (current_result - 1) * 0.04))

    # L: 事故F補正 (f_keisu1 × f_keisu3)
    avg_st = sum(base_sts) / len(base_sts)
    st_dev = base_sts[course - 1] - avg_st
    l_val = f_keisu1(f_status) * f_keisu3(f_status, st_dev)

    # N: 当地補正
    if local_race_count < 5:
        n = 1.00
    else:
        if course_top3_rate > 0:
            raw_n = local_top3_rate / course_top3_rate
        else:
            raw_n = 1.00
        raw_n = max(0.75, min(1.30, raw_n))
        if local_race_count <= 9:
            # 半量ブレンド: 1.00 と raw_n の中間
            n = 1.00 * 0.5 + raw_n * 0.5
        else:
            n = raw_n

    prod = min(j * k * l_val * n, 1.30)

    # I: 枠補正テーブル
    cl = class_label.upper().strip()
    frame_tbl = _FRAME_BONUS.get(cl, _FRAME_BONUS["B1"])
    i_val = frame_tbl.get(course, 0)

    # Il: 地元(愛知)かつ当地出走≥10で+5
    il = 5 if (is_local_aichi and local_race_count >= 10) else 0

    # M: 4-6号 かつ 伸び足desc≥60 かつ 握り発生率≥10
    m = 0
    if course >= 4 and nobi_desc_score >= 60:
        nh = nigiri_hassei_val if nigiri_hassei_val is not None else 0.0
        if nh >= 10:
            m = _M_BONUS.get(course, 0)

    return round(base * prod + i_val + il + m)


# ═══════════════════════════════════════════════════════════
# ⑦ 握り発生率 hassei (nigiri_hassei)
# ═══════════════════════════════════════════════════════════

def _wind_hassei(wind_dir: str, wind_speed: float) -> float:
    """風係数。

    Args:
        wind_dir: 風向 ("追い風"/"向かい風"/"横風"/"無風" 等)
        wind_speed: 風速(m)

    Returns:
        風係数 w
    """
    if "追" in wind_dir:
        if wind_speed > 5:
            return 1.20
        if wind_speed >= 3:
            return 1.10
        return 1.00
    if "向" in wind_dir or "逆" in wind_dir:
        if wind_speed >= 3:
            return 1.15
        return 1.05
    # 無風・横風
    return 0.95


def _stdom(delta_st: float, scale: str = "normal") -> float:
    """ST優勢度の段階値。

    ΔST = base_自分 - base_相手。負(自分が速い)ほど大きい値。

    Args:
        delta_st: ST差 (自分 - 相手)。負=自分が速い。
        scale: "normal" or "4号" (4号は別スケール)

    Returns:
        段階値 (0.05〜1.00)
    """
    if scale == "4号":
        # 4号スケール: やや緩い段階
        if delta_st <= -0.10:
            return 1.00
        if delta_st <= -0.06:
            return 0.85
        if delta_st <= -0.03:
            return 0.70
        if delta_st <= 0.0:
            return 0.55
        if delta_st <= 0.03:
            return 0.35
        if delta_st <= 0.06:
            return 0.20
        return 0.10

    # normal スケール
    if delta_st <= -0.10:
        return 1.00
    if delta_st <= -0.06:
        return 0.80
    if delta_st <= -0.03:
        return 0.60
    if delta_st <= 0.0:
        return 0.45
    if delta_st <= 0.03:
        return 0.25
    if delta_st <= 0.06:
        return 0.15
    return 0.05


def nigiri_hassei(
    base_sts: List[float],
    nigiri_rates: List[Optional[float]],
    sashi_rate_2: float,
    pre_ranks: List[int],
    current_results: List[float],
    f_statuses: List[Optional[str]],
    race_counts: List[int],
    wind_dir: str,
    wind_speed: float,
    core_mult: Dict[int, float],
) -> List[Optional[float]]:
    """各外艇の握り発生率を算出する。

    Args:
        base_sts: 各艇(6)の基準ST
        nigiri_rates: 各艇(6)の握り率(%) (1号はNone)
        sashi_rate_2: 2号の差し率(%)
        pre_ranks: 各艇(6)のpre_EI降順順位 (1=最高)
        current_results: 各艇(6)の今節着順
        f_statuses: 各艇(6)のF事故ステータス
        race_counts: 各艇(6)のコース出走数
        wind_dir: 風向
        wind_speed: 風速(m)
        core_mult: 会場の核補正 {course(1-indexed): 係数}

    Returns:
        各艇(6)の握り発生率(%)。1号はNone。
    """
    w = _wind_hassei(wind_dir, wind_speed)
    result: List[Optional[float]] = [None]  # 1号

    # --- 2号 ---
    nr2 = (nigiri_rates[1] or 0.0) / 100.0
    stdom2 = _stdom(base_sts[1] - base_sts[0])
    cm2 = core_mult.get(2, 1.0)
    h2 = nr2 * stdom2 * w * 100.0 * cm2
    result.append(max(0.0, h2))

    # --- 3号: 2段階連鎖 ---
    nr3 = (nigiri_rates[2] or 0.0) / 100.0
    hikinami = 1.0 - (sashi_rate_2 / 100.0) * 0.3
    h_a = nr3 * _stdom(base_sts[2] - base_sts[1]) * 1.20  # 2号が握った世界
    h_b = nr3 * _stdom(base_sts[2] - base_sts[0]) * hikinami  # 2号が握らない世界
    nig2 = h2 / 100.0 if h2 > 0 else 0.0
    nig2 = min(nig2, 1.0)
    cm3 = core_mult.get(3, 1.0)
    h3 = (h_a * nig2 + h_b * (1.0 - nig2)) * w * 100.0 * cm3
    result.append(max(0.0, h3))

    # --- 4号: スリット絞り ---
    pr4 = pre_ranks[3]  # 4号のpre_rank
    shibori_map = {1: 1.00, 2: 0.85, 3: 0.70}
    shibori = shibori_map.get(pr4, 0.55)

    # kabe: 2号のpre_rankとbase_stで壁効果
    pr2 = pre_ranks[1]
    # 2号が速い壁(pre_rank上位かつST速い)なら抑制、遅い壁なら増幅
    if pr2 <= 2 and base_sts[1] <= base_sts[0]:
        kabe = 0.75  # 強い壁 → 4号抑制
    elif pr2 <= 3:
        kabe = 0.90
    elif pr2 >= 5 and base_sts[1] > base_sts[0] + 0.03:
        kabe = 1.30  # 弱い壁 → 4号増幅
    elif pr2 >= 4:
        kabe = 1.10
    else:
        kabe = 1.00

    # tenkai: 2号3号の握り発生率合計で展開判定
    h2h3_sum = h2 + h3
    if h2h3_sum > 40:
        tenkai = 1.15
    elif h2h3_sum >= 20:
        tenkai = 1.00
    else:
        tenkai = 0.85

    stdom4 = _stdom(base_sts[3] - base_sts[2], "4号")
    cm4 = core_mult.get(4, 1.0)
    h4 = stdom4 * shibori * kabe * tenkai * w * 0.90 * 100.0 * cm4
    result.append(max(0.0, h4))

    # --- 5号・6号 ---
    for c_idx in (4, 5):  # 0-indexed: 5号=4, 6号=5
        course_1indexed = c_idx + 1
        # hakka: ΔST(base_c - base_{c-1})の段階値
        delta_st = base_sts[c_idx] - base_sts[c_idx - 1]
        if delta_st <= -0.04:
            hakka = 0.85
        elif delta_st <= -0.02:
            hakka = 0.65
        elif delta_st <= 0.0:
            hakka = 0.40
        elif delta_st <= 0.02:
            hakka = 0.20
        else:
            hakka = 0.05

        # teki: min(握り率/30, 1) (出走≥5、未満は0.50)
        nr_c = nigiri_rates[c_idx]
        rc = race_counts[c_idx]
        if rc >= 5 and nr_c is not None:
            teki = min(nr_c / 30.0, 1.0)
        else:
            teki = 0.50

        # antei: 1 - (今節着順-1)*0.05
        antei = 1.0 - (current_results[c_idx] - 1) * 0.05

        f_coef = f_keisu1(f_statuses[c_idx])
        cm_c = core_mult.get(course_1indexed, 1.0)
        h_c = hakka * teki * antei * f_coef * 0.90 * w * 100.0 * cm_c
        result.append(max(0.0, h_c))

    return result


# ═══════════════════════════════════════════════════════════
# ⑧ 最終EI (依存チェーン統合)
# ═══════════════════════════════════════════════════════════

def compute_ei_pipeline(
    entries: List[Dict[str, Any]],
    venue_name: str,
    day_no: int,
    month: int,
    wind_dir: str,
    wind_speed: float,
    is_seasonal_motor: bool,
) -> Dict[str, Any]:
    """⑥⑦⑧の依存チェーンを統合して最終EIを算出する。

    依存チェーン:
        pre_EI(G除外) → pre_rank → hassei → 最終EI(G加算)

    Args:
        entries: 各艇(6)のデータ辞書リスト。各辞書に以下のキーが必要:
            - course: int (1-6)
            - average_st: float
            - course_average_st: float
            - current_st: float
            - current_result: float (今節着順)
            - f_status: Optional[str]
            - class_label: str ("A1"/"A2"/"B1"/"B2")
            - age: int
            - deashi: float (出足評価値)
            - nobi: float (伸び足評価値)
            - course_top3_rate: float (コース3連率%)
            - course_race_count: int
            - local_top3_rate: float (当地3連率%)
            - local_race_count: int
            - general_top3_rate: Optional[float] (一般戦3連率%)
            - general_race_count: Optional[int]
            - makuri: int
            - makurizashi: int
            - race_count: int (コース出走数)
            - sashi_rate: float (差し率%, 2号用)
            - is_local_aichi: bool
            - base_st: float (①の出力)
        venue_name: 会場名
        day_no: 節の日目
        month: 月
        wind_dir: 風向
        wind_speed: 風速(m)
        is_seasonal_motor: 季節モーター時か

    Returns:
        {
            "ei_values": List[int],        # 各艇(6)の最終EI
            "ei_order": List[int],         # 降順順位
            "pre_ei_values": List[int],    # pre_EI値
            "pre_rank": List[int],         # pre_EI降順順位
            "hassei_values": List[Optional[float]],  # 握り発生率
            "components": List[Dict],      # 各艇のEI成分
        }
    """
    venue = get_venue(venue_name)
    cm = venue.get("core_mult", {})

    deashi_list = [e["deashi"] for e in entries]
    nobi_list = [e["nobi"] for e in entries]
    base_sts = [e["base_st"] for e in entries]
    f_statuses = [e.get("f_status") for e in entries]
    current_results = [e["current_result"] for e in entries]
    class_labels = [e["class_label"] for e in entries]

    # 握り率
    nigiri_rates: List[Optional[float]] = []
    for e in entries:
        nr = nigiri_rate(e["course"], e.get("makuri", 0),
                         e.get("makurizashi", 0), e.get("race_count", 0))
        nigiri_rates.append(nr)

    # desc_score for nobi (M判定用)
    nobi_desc = desc_score(nobi_list)

    # ── Phase 1: pre_EI (G除外) ──
    all_components: List[Dict[str, float]] = []
    pre_ei_values: List[int] = []

    # 優勢順位D (②の出力が必要)
    current_sts = [e.get("current_st", e.get("average_st", 0.15)) for e in entries]
    average_sts = [e.get("average_st", 0.15) for e in entries]
    yusei_ranks = yusei_rank(current_sts, average_sts, current_results, f_statuses)

    for i, e in enumerate(entries):
        course = e["course"]
        comp = ei_components(
            course=course,
            course_top3_rate=e["course_top3_rate"],
            course_race_count=e["course_race_count"],
            local_top3_rate=e["local_top3_rate"],
            local_race_count=e["local_race_count"],
            general_top3_rate=e.get("general_top3_rate"),
            general_race_count=e.get("general_race_count"),
            yusei_rank_d=yusei_ranks[i],
            deashi_list=deashi_list,
            nobi_list=nobi_list,
            is_seasonal_motor=is_seasonal_motor,
            nigiri_rate_val=nigiri_rates[i],
            nigiri_hassei_val=None,  # pre_EI時はhassei未算出
            class_label=e["class_label"],
            age=e["age"],
        )
        all_components.append(comp)

        pre_ei = ei_full(
            components=comp,
            include_g=False,  # G除外
            course=course,
            current_result=e["current_result"],
            f_status=e.get("f_status"),
            base_sts=base_sts,
            local_top3_rate=e["local_top3_rate"],
            course_top3_rate=e["course_top3_rate"],
            local_race_count=e["local_race_count"],
            class_label=e["class_label"],
            is_local_aichi=e.get("is_local_aichi", False),
            nobi_desc_score=float(nobi_desc[i]),
            nigiri_hassei_val=None,
        )
        pre_ei_values.append(pre_ei)

    # pre_rank: pre_EIの降順順位 (大きい=1位)
    pre_rank: List[int] = []
    for i in range(6):
        rank = sum(1 for j in range(6) if pre_ei_values[j] > pre_ei_values[i]) + 1
        pre_rank.append(rank)

    # ── Phase 2: 握り発生率 (⑦) ──
    sashi_rate_2 = entries[1].get("sashi_rate", 0.0) if len(entries) > 1 else 0.0
    race_counts = [e.get("race_count", 0) for e in entries]

    hassei_values = nigiri_hassei(
        base_sts=base_sts,
        nigiri_rates=nigiri_rates,
        sashi_rate_2=sashi_rate_2,
        pre_ranks=pre_rank,
        current_results=current_results,
        f_statuses=f_statuses,
        race_counts=race_counts,
        wind_dir=wind_dir,
        wind_speed=wind_speed,
        core_mult=cm,
    )

    # ── Phase 3: 最終EI (G加算, ⑧) ──
    # 成分を再計算 (G にhassei値を反映)
    final_ei_values: List[int] = []
    for i, e in enumerate(entries):
        course = e["course"]
        comp = ei_components(
            course=course,
            course_top3_rate=e["course_top3_rate"],
            course_race_count=e["course_race_count"],
            local_top3_rate=e["local_top3_rate"],
            local_race_count=e["local_race_count"],
            general_top3_rate=e.get("general_top3_rate"),
            general_race_count=e.get("general_race_count"),
            yusei_rank_d=yusei_ranks[i],
            deashi_list=deashi_list,
            nobi_list=nobi_list,
            is_seasonal_motor=is_seasonal_motor,
            nigiri_rate_val=nigiri_rates[i],
            nigiri_hassei_val=hassei_values[i],  # hassei反映
            class_label=e["class_label"],
            age=e["age"],
        )
        all_components[i] = comp  # 更新

        final_ei = ei_full(
            components=comp,
            include_g=True,  # G加算
            course=course,
            current_result=e["current_result"],
            f_status=e.get("f_status"),
            base_sts=base_sts,
            local_top3_rate=e["local_top3_rate"],
            course_top3_rate=e["course_top3_rate"],
            local_race_count=e["local_race_count"],
            class_label=e["class_label"],
            is_local_aichi=e.get("is_local_aichi", False),
            nobi_desc_score=float(nobi_desc[i]),
            nigiri_hassei_val=hassei_values[i],
        )
        final_ei_values.append(final_ei)

    # ei_order: 最終EIの降順順位
    ei_order: List[int] = []
    for i in range(6):
        rank = sum(1 for j in range(6) if final_ei_values[j] > final_ei_values[i]) + 1
        ei_order.append(rank)

    return {
        "ei_values": final_ei_values,
        "ei_order": ei_order,
        "pre_ei_values": pre_ei_values,
        "pre_rank": pre_rank,
        "hassei_values": hassei_values,
        "components": all_components,
    }


# ═══════════════════════════════════════════════════════════
# P1 定数
# ═══════════════════════════════════════════════════════════

MOT_M: Dict[str, float] = {
    "S": 1.10, "A": 1.10, "B": 1.05, "C": 1.00, "D": 0.90,
}

# 季節係数 SEASON（蒲郡核。他会場は全1.00）
# summer: 夏は3-4号↑/1号↓  autumn: 秋は1号↑/外↓  winter: 冬は1号微↑
SEASON: Dict[str, Dict[int, float]] = {
    "summer": {1: 0.92, 2: 1.10, 3: 1.15, 4: 1.18, 5: 0.95, 6: 0.90},
    "autumn": {1: 1.18, 2: 0.95, 3: 0.92, 4: 0.88, 5: 0.85, 6: 0.80},
    "winter": {1: 1.05, 2: 1.00, 3: 0.98, 4: 0.95, 5: 0.92, 6: 0.88},
    "spring": {1: 1.00, 2: 1.00, 3: 1.00, 4: 1.00, 5: 1.00, 6: 1.00},
}

# R番号補正 RNUM（蒲郡核。use_rnum=True の会場のみ適用）
RNUM: Dict[str, Dict[int, float]] = {
    "1-4": {1: 0.82, 3: 1.10, 4: 1.15},
    "12":  {1: 1.30, 3: 0.90, 4: 0.90, 5: 0.85, 6: 0.80},
}

# GENSHU_FLOOR（R帯別の減衰下限。蒲郡核）
GENSHU_FLOOR: Dict[str, float] = {
    "1-4": 0.62,
    "12": 0.85,
    "_": 0.70,
}

# 被弾分析のモーター偏差
MOT_DEV: Dict[str, float] = {
    "S": 1.15, "A": 1.15, "B": 1.05, "C": 0.95, "D": 0.80,
}


# ═══════════════════════════════════════════════════════════
# ⑨ P1（1着率%）— p1_calc
# ═══════════════════════════════════════════════════════════

def _st_hosei(base_st: float, avg_st: float) -> float:
    """ST補正。base_st が平均より速い(小さい)ほど有利。"""
    d = base_st - avg_st
    if d <= -0.03:
        return 1.15
    if d <= -0.01:
        return 1.08
    if d < 0.01:
        return 1.00
    if d < 0.03:
        return 0.90
    return 0.78


def _hidari(course: int, base_sts: List[float], avg_st: float) -> float:
    """内艇(前艇)のSTが速いと自分が有利。1号は1.00。"""
    if course == 1:
        return 1.00
    d = base_sts[course - 2] - avg_st  # 前艇(course-1)のST偏差
    if d <= -0.03:
        return 1.05
    if d <= -0.01:
        return 1.02
    if d < 0.02:
        return 1.00
    return 0.97


def p1_calc(
    base_sts: List[float],
    course_win_rates: List[float],
    local_win_rates: List[float],
    local_race_counts: List[int],
    motor_labels: List[str],
    genshu1: float,
    venue_name: str,
    month: int,
    race_no: int,
) -> List[float]:
    """各艇のP1(1着率%)を算出する。合計100%に正規化。

    Args:
        base_sts: 各艇(6)の基準ST
        course_win_rates: 各艇(6)のコース別勝率(%)
        local_win_rates: 各艇(6)の当地勝率(%)
        local_race_counts: 各艇(6)の当地出走数
        motor_labels: 各艇(6)のモーターランク ("S"/"A"/"B"/"C"/"D")
        genshu1: 1号の減衰係数 (⑪で算出、初期はGENSHU_FLOOR)
        venue_name: 会場名
        month: 月
        race_no: R番号

    Returns:
        各艇(6)のP1(%) — 合計≈100
    """
    venue = get_venue(venue_name)
    use_rnum = venue.get("use_rnum", False)
    season = season_of(month)
    band = rnum_band(race_no)
    avg_st = sum(base_sts) / 6.0

    pres: List[float] = []
    for i in range(6):
        course = i + 1

        # p1raw: コース勝率と当地勝率のブレンド
        lrc = local_race_counts[i]
        if lrc < 5:
            p1raw = course_win_rates[i]
        elif lrc <= 9:
            p1raw = course_win_rates[i] * 0.6 + local_win_rates[i] * 0.4
        else:
            p1raw = course_win_rates[i] * 0.4 + local_win_rates[i] * 0.6

        # 減衰係数 g: 1号のみ genshu1、他は1.0
        g = genshu1 if i == 0 else 1.0

        # ST補正
        st_h = _st_hosei(base_sts[i], avg_st)

        # 左隣補正
        hid = _hidari(course, base_sts, avg_st)

        # モーター乗算
        mm = MOT_M.get(motor_labels[i], 1.00)

        # 季節係数
        season_coef = SEASON.get(season, SEASON["spring"]).get(course, 1.00)

        # wind_mult / wave_mult: 未適用（既定1.0）
        wind_m = 1.00
        wave_m = 1.00

        # R番号補正 (use_rnum時のみ)
        rnum_coef = 1.00
        if use_rnum:
            rnum_coef = RNUM.get(band, {}).get(course, 1.00)

        pre = p1raw * g * st_h * hid * mm * season_coef * wind_m * rnum_coef * wave_m
        pres.append(max(pre, 0.001))  # ゼロ除算防止

    # 正規化: P1[i] = pre[i] / Σpre × 100
    total = sum(pres)
    return [pre / total * 100.0 for pre in pres]


# ═══════════════════════════════════════════════════════════
# ⑩ 1号被弾分析 — higaki_analysis
# ═══════════════════════════════════════════════════════════

def higaki_analysis(
    racer_course_others: Optional[Dict[int, Dict[str, Any]]],
    ei_values: List[int],
    course_win_rates: List[float],
    motor_labels: List[str],
    venue_name: str,
    month: int,
    race_no: int,
    race_count_1: int,
    is_local: List[bool],
) -> Dict[str, Any]:
    """1号がインのとき、他艇がどれだけ食うかを分析する。

    Args:
        racer_course_others: 1号がインのとき各外艇cの成績。
            {c(2-6): {"hit": float, "hit2r": float, "main": str}} or None
        ei_values: 各艇(6)の最終EI
        course_win_rates: 各艇(6)のコース別勝率(%)
        motor_labels: 各艇(6)のモーターランク
        venue_name: 会場名
        month: 月
        race_no: R番号
        race_count_1: 1号のコース出走数
        is_local: 各艇(6)が地元かどうか

    Returns:
        {
            "hit_adj": Dict[int, float],   # コース(2-6) → 補正被弾
            "hit2r_adj": Dict[int, float],  # コース(2-6) → 補正2連
            "coefs": Dict[int, float],      # コース(2-6) → 乗艇係数
        }
    """
    venue = get_venue(venue_name)
    base_ei = venue.get("base_ei", {})
    base_wr = venue.get("base_wr", {})
    rider_max = venue.get("rider_max", 2.0)
    use_rnum = venue.get("use_rnum", False)
    season = season_of(month)
    band = rnum_band(race_no)

    nin = min(race_count_1 / 15.0, 1.0)

    hit_adj: Dict[int, float] = {}
    hit2r_adj: Dict[int, float] = {}
    coefs: Dict[int, float] = {}

    for c in range(2, 7):
        idx = c - 1  # 0-indexed

        # データがない場合のフォールバック
        if racer_course_others is None or c not in racer_course_others:
            # デフォルト: 会場基準勝率をhitに、hit*1.5をhit2rに
            hit = base_wr.get(c, 10.0)
            hit2r = hit * 1.5
            main = "差" if c == 2 else ("捲差" if c in (3, 5) else "捲")
        else:
            others = racer_course_others[c]
            hit = others.get("hit", base_wr.get(c, 10.0))
            hit2r = others.get("hit2r", hit * 1.5)
            main = others.get("main", "差")

        # 乗艇係数 coef
        ei_dev = ei_values[idx] / base_ei.get(c, 50.0) if base_ei.get(c, 50.0) > 0 else 1.0
        wr_dev = course_win_rates[idx] / base_wr.get(c, 10.0) if base_wr.get(c, 10.0) > 0 else 1.0
        mot_dev = MOT_DEV.get(motor_labels[idx], 1.00)

        coef = ei_dev * 0.5 + wr_dev * 0.3 + mot_dev * 0.2

        # 決め手×コースの相性補正
        if c == 4 and main == "捲":
            coef *= 1.20
        elif c == 3 and main == "捲差":
            coef *= 1.12
        elif c == 5 and main == "捲差":
            coef *= 1.08
        elif c == 2 and main == "差":
            coef *= 1.05

        # 季節補正
        if season == "summer" and c in (3, 4):
            coef *= 1.10

        # R帯補正
        if use_rnum:
            if band == "1-4" and c in (3, 4):
                coef *= 1.15
            elif band == "12" and c in (3, 4):
                coef *= 0.85

        # 地元補正
        if is_local[idx]:
            coef *= 1.05

        coef = max(0.50, min(rider_max, coef))
        coefs[c] = coef

        # 補正被弾・補正2連
        hit_adj[c] = hit * coef * nin
        hit2r_adj[c] = hit2r * math.sqrt(coef) * nin

    return {
        "hit_adj": hit_adj,
        "hit2r_adj": hit2r_adj,
        "coefs": coefs,
    }


# ═══════════════════════════════════════════════════════════
# ⑪ 減衰係数 — damping_1c
# ═══════════════════════════════════════════════════════════

def damping_1c(
    hit_adj: Dict[int, float],
    race_no: int,
) -> float:
    """1号の減衰係数 genshu1 を算出する。

    Args:
        hit_adj: コース(2-6) → 補正被弾 (⑩の出力)
        race_no: R番号

    Returns:
        genshu1 (0〜1)
    """
    s = sum(hit_adj.get(c, 0.0) for c in range(2, 7))
    g = 1.0 - (s / 100.0) * 0.5

    # R帯別の下限 GENSHU_FLOOR で底上げ
    band = rnum_band(race_no)
    floor = GENSHU_FLOOR.get(band, GENSHU_FLOOR.get("_", 0.70))
    return max(g, floor)


# ═══════════════════════════════════════════════════════════
# ⑫ 逃げ成立度 — nige_seiritsu
# ═══════════════════════════════════════════════════════════

def nige_seiritsu(
    hassei_values: List[Optional[float]],
    g_values: List[Optional[float]],
    hit_adj: Dict[int, float],
    hit2r_adj: Dict[int, float],
    coefs: Dict[int, float],
    venue_name: str,
    month: int,
    race_no: int,
    race_count_1: int,
    higaki_mains: Optional[Dict[int, str]] = None,
) -> float:
    """1号の逃げ成立度を算出する。

    Args:
        hassei_values: 各艇(6)の握り発生率(%) (1号はNone)
        g_values: 各艇(6)の捲り完遂力差g (1号はNone) — ⑤の出力
        hit_adj: コース(2-6) → 補正被弾
        hit2r_adj: コース(2-6) → 補正2連
        coefs: コース(2-6) → 乗艇係数
        venue_name: 会場名
        month: 月
        race_no: R番号
        race_count_1: 1号のコース出走数
        higaki_mains: コース(2-6) → 決め手 (被弾分析の主決め手)

    Returns:
        逃げ成立度 (0〜1)
    """
    venue = get_venue(venue_name)
    kado_map = venue.get("kado", {})
    nige_floor_map = venue.get("nige_floor", {"_": 0.45})
    floor_basis = venue.get("floor_basis", "season")
    season = season_of(month)
    band = rnum_band(race_no)

    nin = min(race_count_1 / 15.0, 1.0)

    # 攻め圧力 ap_nig
    ap_nig = 0.0

    # 各 c=3,4,5,6 のカド攻め
    for c in (3, 4, 5, 6):
        idx = c - 1
        h2adj_val = hit2r_adj.get(c, 0.0)
        coef_c = coefs.get(c, 1.0)
        # h2adj は既に計算済み（⑩で hit2r × √coef × nin）
        # ここでは threat 判定に使う
        threat = 1.15 if h2adj_val >= 30.0 else 1.00

        g_c = g_values[idx] if g_values[idx] is not None else 0.5
        kado_c = kado_map.get(c, 1.0)

        seiritsu = g_c * kado_c * threat

        hassei_c = hassei_values[idx] if hassei_values[idx] is not None else 0.0
        ap_nig += (hassei_c / 100.0) * seiritsu

    # 2号の差し/まくり圧
    hassei_2 = hassei_values[1] if hassei_values[1] is not None else 0.0
    ap_nig += (hassei_2 / 100.0) * 1.00

    # 場固有脅威 ba
    ba = 0.0
    mains = higaki_mains or {}

    # 4号
    h4 = hit_adj.get(4, 0.0)
    m4 = mains.get(4, "")
    if h4 >= 10.0 and m4 == "捲":
        ba += 0.20
    elif h4 >= 5.0:
        ba += 0.10
    else:
        ba += 0.03

    # 3号
    h3 = hit_adj.get(3, 0.0)
    m3 = mains.get(3, "")
    if h3 >= 10.0 and m3 == "捲":
        ba += 0.10
    elif h3 >= 5.0:
        ba += 0.06
    else:
        ba += 0.02

    # 5号
    h5 = hit_adj.get(5, 0.0)
    m5 = mains.get(5, "")
    if h5 >= 10.0 and m5 == "捲差":
        ba += 0.06
    else:
        ba += 0.02

    # 2号
    h2 = hit_adj.get(2, 0.0)
    m2 = mains.get(2, "")
    if h2 >= 10.0 and m2 == "差":
        ba += 0.08
    elif h2 >= 5.0:
        ba += 0.04
    else:
        ba += 0.02

    # ベース加算
    ba += 0.02

    # 条件加算 cond
    cond = 0.0
    if band == "1-4":
        cond += 0.06
    if season == "summer":
        cond += 0.03

    # 脅威合計
    threat_total = ba + cond
    ap = ap_nig + threat_total

    # 逃げ成立度
    raw_nige = 1.0 - min(ap * 0.5, 0.85)

    # floor 決定
    if floor_basis == "rnum":
        floor = nige_floor_map.get(band, nige_floor_map.get("_", 0.45))
    else:
        floor = nige_floor_map.get(season, nige_floor_map.get("_", 0.45))

    nige = max(floor, min(0.85, raw_nige))
    nige = max(nige, 0.15)  # 最低保証

    return round(nige, 4)


# ═══════════════════════════════════════════════════════════
# P1 + 被弾分析 + 減衰 統合パイプライン
# ═══════════════════════════════════════════════════════════

def compute_p1_pipeline(
    entries: List[Dict[str, Any]],
    venue_name: str,
    month: int,
    race_no: int,
    base_sts: List[float],
    motor_labels: List[str],
    ei_values: List[int],
    g_values: List[Optional[float]],
    hassei_values: List[Optional[float]],
    racer_course_others: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """⑨⑩⑪⑫の依存チェーンを統合する。

    P1は被弾分析→減衰のループがある:
      初期genshu1(GENSHU_FLOOR) → P1計算 → 被弾分析 → genshu1更新 → P1再計算

    Args:
        entries: 各艇(6)のデータ辞書リスト
        venue_name: 会場名
        month: 月
        race_no: R番号
        base_sts: 各艇(6)の基準ST
        motor_labels: 各艇(6)のモーターランク
        ei_values: 各艇(6)の最終EI
        g_values: 各艇(6)の捲り完遂力差g (⑤の出力)
        hassei_values: 各艇(6)の握り発生率(%) (⑦の出力)
        racer_course_others: 1号がインのとき各外艇cの成績 (Noneならフォールバック)

    Returns:
        {
            "p1": List[float],              # 各艇(6)のP1(%) — 合計≈100
            "genshu1": float,               # 1号の減衰係数
            "hit_adj": Dict[int, float],    # 補正被弾
            "hit2r_adj": Dict[int, float],  # 補正2連
            "coefs": Dict[int, float],      # 乗艇係数
            "nige": float,                  # 逃げ成立度
        }
    """
    course_win_rates = [e.get("course_win_rate", 10.0) for e in entries]
    local_win_rates = [e.get("local_win_rate", 10.0) for e in entries]
    local_race_counts = [e.get("local_race_count", 0) for e in entries]
    is_local = [e.get("is_local", False) for e in entries]
    race_count_1 = entries[0].get("race_count", 0)

    # --- Phase 1: 初期 genshu1 (GENSHU_FLOOR) ---
    band = rnum_band(race_no)
    initial_genshu1 = GENSHU_FLOOR.get(band, GENSHU_FLOOR.get("_", 0.70))

    # --- Phase 2: 初期 P1 ---
    p1_initial = p1_calc(
        base_sts=base_sts,
        course_win_rates=course_win_rates,
        local_win_rates=local_win_rates,
        local_race_counts=local_race_counts,
        motor_labels=motor_labels,
        genshu1=initial_genshu1,
        venue_name=venue_name,
        month=month,
        race_no=race_no,
    )

    # --- Phase 3: 被弾分析 (⑩) ---
    higaki = higaki_analysis(
        racer_course_others=racer_course_others,
        ei_values=ei_values,
        course_win_rates=course_win_rates,
        motor_labels=motor_labels,
        venue_name=venue_name,
        month=month,
        race_no=race_no,
        race_count_1=race_count_1,
        is_local=is_local,
    )

    # --- Phase 4: 減衰係数 (⑪) ---
    genshu1 = damping_1c(
        hit_adj=higaki["hit_adj"],
        race_no=race_no,
    )

    # --- Phase 5: P1 再計算 (genshu1 更新後) ---
    p1_final = p1_calc(
        base_sts=base_sts,
        course_win_rates=course_win_rates,
        local_win_rates=local_win_rates,
        local_race_counts=local_race_counts,
        motor_labels=motor_labels,
        genshu1=genshu1,
        venue_name=venue_name,
        month=month,
        race_no=race_no,
    )

    # --- Phase 6: 逃げ成立度 (⑫) ---
    # 決め手情報の取得
    higaki_mains: Optional[Dict[int, str]] = None
    if racer_course_others is not None:
        higaki_mains = {}
        for c in range(2, 7):
            if c in racer_course_others:
                higaki_mains[c] = racer_course_others[c].get("main", "")
            else:
                # フォールバック決め手
                higaki_mains[c] = "差" if c == 2 else ("捲差" if c in (3, 5) else "捲")
    else:
        # フォールバック決め手
        higaki_mains = {
            2: "差", 3: "捲差", 4: "捲", 5: "捲差", 6: "捲",
        }

    nige = nige_seiritsu(
        hassei_values=hassei_values,
        g_values=g_values,
        hit_adj=higaki["hit_adj"],
        hit2r_adj=higaki["hit2r_adj"],
        coefs=higaki["coefs"],
        venue_name=venue_name,
        month=month,
        race_no=race_no,
        race_count_1=race_count_1,
        higaki_mains=higaki_mains,
    )

    return {
        "p1": p1_final,
        "genshu1": genshu1,
        "hit_adj": higaki["hit_adj"],
        "hit2r_adj": higaki["hit2r_adj"],
        "coefs": higaki["coefs"],
        "nige": nige,
    }
