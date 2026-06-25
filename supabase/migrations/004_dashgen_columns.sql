-- ダッシュボード生成ロジック(dashgen)に必要な不足カラムの追加
-- 参照: data/dashgen_logic_full.md, tmp/dashgen_logic_review.md

-- ============================================================
-- 1. boats テーブル: コース別決まり手カウント (n=1-6)
--    握り率④、捲り負け率⑮に必須
--    NOTE: c{n}_makuri, c{n}_sashi, c{n}_makurizashi は既存マイグレーション
--          (server.py /migrate) で追加済み。ここでは c{n}_nige のみ追加。
--          dashgenロジックでは既存カラム名 c{n}_makurizashi を使用すること。
-- ============================================================
-- 既存カラム（IF NOT EXISTS で安全に再実行可能）:
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c1_makuri INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c1_sashi INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c1_makurizashi INTEGER;

ALTER TABLE boats ADD COLUMN IF NOT EXISTS c2_makuri INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c2_sashi INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c2_makurizashi INTEGER;

ALTER TABLE boats ADD COLUMN IF NOT EXISTS c3_makuri INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c3_sashi INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c3_makurizashi INTEGER;

ALTER TABLE boats ADD COLUMN IF NOT EXISTS c4_makuri INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c4_sashi INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c4_makurizashi INTEGER;

ALTER TABLE boats ADD COLUMN IF NOT EXISTS c5_makuri INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c5_sashi INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c5_makurizashi INTEGER;

ALTER TABLE boats ADD COLUMN IF NOT EXISTS c6_makuri INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c6_sashi INTEGER;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c6_makurizashi INTEGER;

-- ============================================================
-- 2. boats テーブル: コース別2連率 (n=1-6)
--    TI⑬、着内率⑭に必須
--    NOTE: 既存カラム名は c{n}_place2_rate（server.py で使用中）。
--          dashgenロジックでは c{n}_place2_rate を使用すること。
-- ============================================================
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c1_place2_rate FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c2_place2_rate FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c3_place2_rate FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c4_place2_rate FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c5_place2_rate FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c6_place2_rate FLOAT;

-- ============================================================
-- 3. boats テーブル: コース別平均ST (n=1-6)
--    基準ST①に必須
-- ============================================================
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c1_avg_st FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c2_avg_st FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c3_avg_st FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c4_avg_st FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c5_avg_st FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS c6_avg_st FLOAT;

-- ============================================================
-- 4. boats テーブル: 支部
--    EIの地元補正(Il)に必要
-- ============================================================
ALTER TABLE boats ADD COLUMN IF NOT EXISTS branch TEXT;

-- ============================================================
-- 5. boats テーブル: 一般戦成績
--    EI成分Cに必要
-- ============================================================
ALTER TABLE boats ADD COLUMN IF NOT EXISTS ippan_top3_rate FLOAT;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS ippan_starts INTEGER;

-- ============================================================
-- 6. 新テーブル: racer_course_others（他艇対戦成績）
--    被弾分析⑩、P2マトリクス⑬に必須
-- ============================================================
CREATE TABLE IF NOT EXISTS racer_course_others (
    id BIGSERIAL PRIMARY KEY,
    race_date DATE NOT NULL,
    venue TEXT NOT NULL,
    race_no INTEGER NOT NULL,
    course INTEGER NOT NULL CHECK (course BETWEEN 1 AND 6),
    other_course INTEGER NOT NULL CHECK (other_course BETWEEN 1 AND 6),
    win_rate FLOAT,
    top2_rate FLOAT,
    top3_rate FLOAT,
    starts INTEGER,
    sashi INTEGER,
    makuri INTEGER,
    makuri_sashi INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (race_date, venue, race_no, course, other_course)
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_racer_course_others_lookup
    ON racer_course_others(race_date, venue, race_no);
CREATE INDEX IF NOT EXISTS idx_racer_course_others_course
    ON racer_course_others(race_date, venue, race_no, course);

-- RLS（既存テーブルのパターンに合わせる）
ALTER TABLE racer_course_others ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_racer_course_others"
    ON racer_course_others FOR ALL USING (true);
