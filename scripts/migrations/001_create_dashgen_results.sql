-- dashgen_results テーブル作成マイグレーション
-- Supabase Dashboard > SQL Editor で実行してください
-- URL: https://supabase.com/dashboard/project/zotskrheypxrfsiyvwtl/sql/new

-- 1. テーブル作成
CREATE TABLE IF NOT EXISTS dashgen_results (
    id BIGSERIAL PRIMARY KEY,
    race_id BIGINT NOT NULL UNIQUE,
    result JSONB NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. インデックス作成
CREATE INDEX IF NOT EXISTS idx_dashgen_results_race_id
    ON dashgen_results (race_id);

-- 3. service_role にアクセス権限を付与
GRANT ALL ON TABLE dashgen_results TO service_role;
GRANT USAGE, SELECT ON SEQUENCE dashgen_results_id_seq TO service_role;

-- 4. RLS を有効化（service_role は bypass するので影響なし）
ALTER TABLE dashgen_results ENABLE ROW LEVEL SECURITY;

-- 5. 確認
SELECT 'dashgen_results table created successfully' AS status;
