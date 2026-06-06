-- 会場固有設定テーブル
-- 各競艇場のPDF解析プロンプトから抽出したパラメータを管理

CREATE TABLE IF NOT EXISTS venue_configs (
    id SERIAL PRIMARY KEY,
    venue_name VARCHAR(50) UNIQUE NOT NULL,
    prompt_version VARCHAR(30),              -- e.g. "v14.6-Gamagori"
    
    -- 水面・環境
    water_type VARCHAR(20),                  -- 淡水/海水/汽水/海水プール型
    has_tide_correction BOOLEAN DEFAULT FALSE,
    tide_max_m FLOAT,                        -- 最大干満差(m)
    altitude_m FLOAT,                        -- 標高(m) ※びわこ等
    back_width_m FLOAT,                      -- バック幅(m) ※蒲郡156.7m
    home_width_m FLOAT,                      -- 1Mホーム幅(m)
    
    -- コース別1着率（デフォルト・通年）
    c1_rate_default FLOAT,
    c2_rate FLOAT,
    c3_rate FLOAT,
    c4_rate FLOAT,
    c5_rate FLOAT,
    c6_rate FLOAT,
    
    -- 1コース季節別1着率
    c1_rate_spring FLOAT,    -- 春 3-5月
    c1_rate_summer FLOAT,    -- 夏 6-8月
    c1_rate_autumn FLOAT,    -- 秋 9-11月
    c1_rate_winter FLOAT,    -- 冬 12-2月
    
    -- 水面特性・攻めスタイル
    surface_type VARCHAR(20),                -- 差し/捲り/標準/二面性
    pattern_a_threshold FLOAT DEFAULT 0.45, -- パターンA閾値
    main_attack_description TEXT,            -- 主要スジ説明
    main_attack_patterns JSONB,              -- 主要スジ配列 ["4-1まくり(52.2%)", ...]
    
    -- カド係数（コース別攻め成立係数）
    kad_c2 FLOAT DEFAULT 1.00,
    kad_c3 FLOAT DEFAULT 1.10,
    kad_c4 FLOAT DEFAULT 1.20,
    kad_c5 FLOAT DEFAULT 1.05,
    kad_c6 FLOAT DEFAULT 1.00,
    
    -- 地元支部優位
    home_branch VARCHAR(50),                 -- 香川/広島(安芸)/愛知 等
    home_n_upper FLOAT DEFAULT 1.30,        -- N上限
    home_n_lower FLOAT DEFAULT 0.75,        -- N下限
    home_min_races INT DEFAULT 10,           -- 地元判定最低出走数
    
    -- モーター交換
    motor_exchange_months JSONB,             -- [9] / [3,4] など
    motor_exchange_f_weight FLOAT DEFAULT 0.85,
    motor_exchange_n_upper FLOAT DEFAULT 1.20,
    
    -- 企画レース（レース番号別特別設定）
    scheduled_races JSONB,
    -- 例: [{"race_no": 8, "name": "ガチ勝ち8", "c1_rate": 78.8, "c2_rate": 10.0}]
    
    -- 環境補正
    body_weight_correction BOOLEAN DEFAULT FALSE,  -- 体重係数(海水のみ)
    exhibit_public BOOLEAN DEFAULT TRUE,            -- 展示タイム公開
    is_nighter BOOLEAN DEFAULT FALSE,               -- ナイター
    is_morning BOOLEAN DEFAULT FALSE,               -- モーニング
    is_midnight BOOLEAN DEFAULT FALSE,              -- ミッドナイト
    
    -- 潮汐効果（JSON）
    tide_effects JSONB,
    -- 例: {"rising":"まくり有利","falling":"差し有利","high":"ざわつき","low":"静水面"}
    
    -- 風・特殊条件（JSON）
    wind_effects JSONB,
    seasonal_notes JSONB,
    
    -- レース番号別補正係数（蒲郡の「12R 1C×1.30」等）
    race_no_corrections JSONB,
    -- 例: [{"race_no": 12, "c1_multiplier": 1.30}]
    
    -- F補正（会場固有調整値）
    f_l_f2 FLOAT DEFAULT 0.78,
    f_l_f1_pending FLOAT DEFAULT 0.86,
    f_l_f1_served FLOAT DEFAULT 0.93,
    f_attack_f2 FLOAT DEFAULT 0.70,
    f_attack_f1_pending FLOAT DEFAULT 0.80,
    f_attack_f1_served FLOAT DEFAULT 0.93,
    
    -- 備考・特記事項
    notes TEXT,
    
    -- 生プロンプトテキスト（参照用）
    raw_prompt_text TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 更新日時自動更新トリガー
CREATE OR REPLACE FUNCTION update_venue_configs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER venue_configs_updated_at
    BEFORE UPDATE ON venue_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_venue_configs_updated_at();

-- RLS（認証なしでも読み書き可能にする）
ALTER TABLE venue_configs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_venue_configs" ON venue_configs FOR ALL USING (true);
