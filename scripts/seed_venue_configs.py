"""
会場設定サンプルデータ投入スクリプト
PDFプロンプト（びわこ・芦屋・下関・蒲郡・丸亀・宮島）から抽出したデータをSupabaseに登録

実行方法:
  cd boatrace-predictor
  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python3 scripts/seed_venue_configs.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import get_supabase

VENUE_DATA = [
    {
        "venue_name": "びわこ",
        "prompt_version": "v14.6-Biwako",
        "water_type": "淡水",
        "has_tide_correction": False,
        "altitude_m": 84.0,
        "c1_rate_default": 53.5,
        "c2_rate": 15.0,
        "c3_rate": 12.5,
        "c4_rate": 10.5,
        "c5_rate": 6.5,
        "c6_rate": 2.0,
        "c1_rate_spring": 52.0,
        "c1_rate_summer": 53.0,
        "c1_rate_autumn": 55.0,
        "c1_rate_winter": 55.0,
        "surface_type": "差し",
        "pattern_a_threshold": 0.45,
        "main_attack_description": "差し水面・2C差し有効・気圧補正あり(標高84m)",
        "main_attack_patterns": [
            "2-1差し",
            "3-1まくり差し",
            "4-1まくり",
            "5-1まくり差し",
        ],
        "kad_c3": 1.10,
        "kad_c4": 1.20,
        "kad_c5": 1.05,
        "home_branch": "滋賀",
        "home_n_upper": 1.30,
        "home_n_lower": 0.75,
        "motor_exchange_months": [3],
        "motor_exchange_f_weight": 0.85,
        "body_weight_correction": False,
        "exhibit_public": True,
        "is_nighter": False,
        "notes": "淡水・標高84m気圧補正あり。差し水面だが季節変動小。モーター3月交換。",
        "seasonal_notes": {
            "spring": "春: 1C成立率やや低め(52%)",
            "summer": "夏: 安定(53%)",
            "autumn": "秋: イン強(55%)",
            "winter": "冬: イン強(55%)"
        },
    },
    {
        "venue_name": "芦屋",
        "prompt_version": "v14.6-Ashiya",
        "water_type": "淡水",
        "has_tide_correction": False,
        "c1_rate_default": 45.0,   # 通常レース
        "c2_rate": 14.0,
        "c3_rate": 11.5,
        "c4_rate": 12.5,
        "c5_rate": 8.5,
        "c6_rate": 3.5,
        "c1_rate_spring": 43.0,
        "c1_rate_summer": 44.0,
        "c1_rate_autumn": 47.0,
        "c1_rate_winter": 46.0,
        "surface_type": "捲り",
        "pattern_a_threshold": 0.40,
        "main_attack_description": "4C最強・まくり水面。企画レース多数(1C62.3%含む)。モーター4月交換",
        "main_attack_patterns": [
            "4-1まくり(59-67%)",
            "3-1まくり差し",
            "5-1まくり差し",
            "2-1差し(2C強ST)",
        ],
        "kad_c3": 1.10,
        "kad_c4": 1.30,
        "kad_c5": 1.10,
        "kad_c6": 1.00,
        "home_branch": "福岡(遠賀)",
        "home_n_upper": 1.30,
        "home_n_lower": 0.75,
        "motor_exchange_months": [4],
        "motor_exchange_f_weight": 0.85,
        "body_weight_correction": False,
        "exhibit_public": True,
        "is_nighter": False,
        "scheduled_races": [
            {"race_no": 1, "name": "企画レース1R", "c1_rate": 62.3},
            {"race_no": 2, "name": "企画レース2R", "c1_rate": 62.3},
            {"race_no": 12, "name": "企画レース12R", "c1_rate": 62.3},
        ],
        "notes": "隠れ混戦の典型場(芦屋型)。見た目順当でも被弾率36.5%+攻め2枚の実は混戦が多い。4Cが最強カド。",
    },
    {
        "venue_name": "下関",
        "prompt_version": "v14.6-Shimonoseki",
        "water_type": "海水プール型",
        "has_tide_correction": False,
        "tide_max_m": 0.3,
        "back_width_m": 91.0,
        "c1_rate_default": 60.5,
        "c2_rate": 13.5,
        "c3_rate": 11.0,
        "c4_rate": 8.5,
        "c5_rate": 5.0,
        "c6_rate": 1.5,
        "c1_rate_spring": 61.0,
        "c1_rate_summer": 60.0,
        "c1_rate_autumn": 61.0,
        "c1_rate_winter": 60.0,
        "surface_type": "標準",
        "pattern_a_threshold": 0.50,
        "main_attack_description": "海水プール型・イン有利。バック幅91m広い。2C差し66.8%。8R進入固定72.5%",
        "main_attack_patterns": [
            "2-1差し(66.8%)",
            "3-1まくり差し",
            "4-1まくり",
        ],
        "kad_c3": 1.10,
        "kad_c4": 1.15,
        "kad_c5": 1.05,
        "home_branch": "山口",
        "home_n_upper": 1.30,
        "home_n_lower": 0.75,
        "motor_exchange_months": [11],
        "motor_exchange_f_weight": 0.85,
        "body_weight_correction": True,
        "exhibit_public": True,
        "is_nighter": True,
        "scheduled_races": [
            {"race_no": 8, "name": "進入固定8R", "c1_rate": 72.5},
        ],
        "notes": "海水プール型・イン有利。バック幅広くダッシュ艇有利。ナイター開催。",
    },
    {
        "venue_name": "蒲郡",
        "prompt_version": "v14.6-Gamagori",
        "water_type": "汽水",
        "has_tide_correction": False,
        "back_width_m": 156.7,
        "c1_rate_default": 55.3,
        "c2_rate": 12.1,
        "c3_rate": 12.7,
        "c4_rate": 12.2,
        "c5_rate": 6.0,
        "c6_rate": 1.6,
        "surface_type": "捲り",
        "pattern_a_threshold": 0.45,
        "main_attack_description": "4Cまくり主体・バック幅156.7m(全場最長)。展示タイム非公開",
        "main_attack_patterns": [
            "4-1まくり(52.2%)",
            "3-1まくり差し(43.9%)",
            "5-1まくり差し",
        ],
        "kad_c3": 1.10,
        "kad_c4": 1.25,
        "kad_c5": 1.10,
        "home_branch": "愛知",
        "home_n_upper": 1.30,
        "home_n_lower": 0.75,
        "motor_exchange_months": [7],
        "motor_exchange_f_weight": 0.85,
        "motor_exchange_n_upper": 1.20,
        "body_weight_correction": False,
        "exhibit_public": False,
        "is_nighter": False,
        "race_no_corrections": [
            {"race_no": 12, "c1_multiplier": 1.30},
        ],
        "notes": "バック幅全場最長(156.7m)。展示タイム非公開。汽水(実質プール)。7月モーター交換。12Rは1C×1.30補正。",
    },
    {
        "venue_name": "丸亀",
        "prompt_version": "v14.6-Marugame",
        "water_type": "海水",
        "has_tide_correction": True,
        "tide_max_m": 2.0,
        "home_width_m": 42.0,
        "c1_rate_default": 56.1,
        "c2_rate": 15.1,
        "c3_rate": 11.9,
        "c4_rate": 9.0,
        "c5_rate": 7.3,
        "c6_rate": 2.4,
        "c1_rate_spring": 61.4,
        "c1_rate_summer": 58.3,
        "c1_rate_autumn": 55.3,
        "c1_rate_winter": 53.6,
        "surface_type": "捲り",
        "pattern_a_threshold": 0.45,
        "main_attack_description": "3Cまくり差し50.7%・5Cまくり差し57.5%(全国2位)・季節変動最大(春61.4%→冬53.6%)",
        "main_attack_patterns": [
            "3-1まくり差し(50.7%)",
            "5-1まくり差し(57.5%全国2位)",
            "4-1まくり",
            "2-1差し",
        ],
        "kad_c3": 1.15,
        "kad_c4": 1.20,
        "kad_c5": 1.20,
        "home_branch": "香川",
        "home_n_upper": 1.30,
        "home_n_lower": 0.75,
        "motor_exchange_months": [9],
        "motor_exchange_f_weight": 0.85,
        "motor_exchange_n_upper": 1.20,
        "body_weight_correction": True,
        "exhibit_public": True,
        "is_nighter": True,
        "scheduled_races": [
            {"race_no": 8, "name": "ガチ勝ち8", "c1_rate": 78.8},
        ],
        "tide_effects": {
            "rising": "まくり・まくり差し決まりやすい",
            "falling": "スタート遅め・差し有利",
            "high": "水面ざわつき差し有利",
            "low": "静水面・モーターパワー重要"
        },
        "seasonal_notes": {
            "spring": "春(3-5月): 1C=61.4%・最高イン成立",
            "summer": "夏(6-8月): 1C=58.3%・強風注意",
            "autumn": "秋(9-11月): 1C=55.3%・標準",
            "winter": "冬(12-2月): 1C=53.6%・イン最弱"
        },
        "notes": "全場最大季節変動(春61.4%→冬53.6%)。ブルーナイター。9月モーター交換。8Rガチ勝ち8(1C78.8%)。",
    },
    {
        "venue_name": "宮島",
        "prompt_version": "v14.6-Miyajima",
        "water_type": "海水",
        "has_tide_correction": True,
        "tide_max_m": 3.5,
        "c1_rate_default": 53.0,
        "c2_rate": 15.0,
        "c3_rate": 12.0,
        "c4_rate": 11.0,
        "c5_rate": 6.0,
        "c6_rate": 3.0,
        "surface_type": "差し",
        "pattern_a_threshold": 0.45,
        "main_attack_description": "宮島ターン(4Cまくり差し)が特徴。干満差最大3.5m超。広島(安芸支部)地元優遇",
        "main_attack_patterns": [
            "4-1まくり差し(宮島ターン)",
            "2-1差し",
            "4-5-6(高配当外絡み)",
            "6-1(高配当)",
        ],
        "kad_c3": 1.10,
        "kad_c4": 1.25,
        "kad_c5": 1.05,
        "home_branch": "広島(安芸支部)",
        "home_n_upper": 1.35,
        "home_n_lower": 0.70,
        "home_min_races": 8,
        "motor_exchange_months": [2, 3],
        "motor_exchange_f_weight": 0.85,
        "body_weight_correction": True,
        "exhibit_public": True,
        "is_nighter": False,
        "tide_effects": {
            "rising": "4Cまくり差し有利(宮島ターン)",
            "falling": "差し水面・2C差し有利",
            "high_tide": "外艇有利・高配当出やすい",
            "low_tide": "イン安定"
        },
        "notes": "干満差全場最大(3.5m超)。宮島ターン=4Cまくり差しが決まり手。安芸支部地元優遇N上限1.35。",
    },
]


def main():
    sb = get_supabase()
    
    # テーブル存在確認
    try:
        sb.table("venue_configs").select("id").limit(1).execute()
    except Exception as e:
        print(f"テーブルが存在しません: {e}")
        print("supabase/migrations/002_venue_configs.sql を先に実行してください")
        return
    
    success = 0
    for venue in VENUE_DATA:
        try:
            # upsert (on conflict update)
            sb.table("venue_configs").upsert(venue, on_conflict="venue_name").execute()
            print(f"✓ {venue['venue_name']}")
            success += 1
        except Exception as e:
            print(f"✗ {venue['venue_name']}: {e}")
    
    print(f"\n完了: {success}/{len(VENUE_DATA)} 件登録")


if __name__ == "__main__":
    main()
