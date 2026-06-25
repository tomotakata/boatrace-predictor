-- 会場イベント情報テーブル（永続保存）
-- boatrace.jpから取得したイベント名・グレード・開催期間・日次を蓄積

CREATE TABLE IF NOT EXISTS venue_events (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    venue TEXT NOT NULL,
    event_name TEXT NOT NULL,
    grade TEXT,
    period TEXT,
    day TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, venue)
);

CREATE INDEX IF NOT EXISTS idx_venue_events_date ON venue_events(date);

-- RLS（認証なしでも読み書き可能にする）
ALTER TABLE venue_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_venue_events" ON venue_events FOR ALL USING (true);
