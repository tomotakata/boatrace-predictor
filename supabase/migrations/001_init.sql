-- Boatrace Predictor Database Schema

-- Races table
CREATE TABLE IF NOT EXISTS races (
    id BIGSERIAL PRIMARY KEY,
    race_no INTEGER NOT NULL,
    race_name TEXT,
    date DATE NOT NULL,
    venue TEXT NOT NULL,
    day_no INTEGER,
    status TEXT DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'running', 'finished')),
    weather TEXT,
    temperature FLOAT,
    wind_speed FLOAT,
    wind_direction TEXT,
    wave_height FLOAT,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, venue, race_no)
);

-- Boats table
CREATE TABLE IF NOT EXISTS boats (
    id BIGSERIAL PRIMARY KEY,
    race_id BIGINT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    lane INTEGER NOT NULL CHECK (lane BETWEEN 1 AND 6),
    name TEXT,
    age INTEGER,
    weight FLOAT,
    rank TEXT,
    f_count INTEGER DEFAULT 0,
    is_local BOOLEAN DEFAULT FALSE,

    -- National stats
    national_win_rate FLOAT,
    national_place2_rate FLOAT,
    local_win_rate FLOAT,
    local_place2_rate FLOAT,

    -- Motor stats
    motor_no INTEGER,
    motor_dashfoot FLOAT,
    motor_extfoot FLOAT,
    motor_eval TEXT,
    motor_rank_letter TEXT,
    motor_place2_rate FLOAT,

    -- Start timing
    avg_st FLOAT,
    today_st FLOAT,
    today_st_rank INTEGER,
    exhibition_st FLOAT,
    standard_st FLOAT,
    st_advantage_rank INTEGER,

    -- Exhibition
    exhibition_time FLOAT,
    exhibition_1lap FLOAT,
    exhibition_turning FLOAT,
    exhibition_straight FLOAT,

    -- Course stats
    c1_races INTEGER, c1_win_rate FLOAT, c1_tricast_rate FLOAT,
    c2_races INTEGER, c2_win_rate FLOAT, c2_tricast_rate FLOAT,
    c3_races INTEGER, c3_win_rate FLOAT, c3_tricast_rate FLOAT,
    c4_races INTEGER, c4_win_rate FLOAT, c4_tricast_rate FLOAT,
    c5_races INTEGER, c5_win_rate FLOAT, c5_tricast_rate FLOAT,
    c6_races INTEGER, c6_win_rate FLOAT, c6_tricast_rate FLOAT,

    -- Local 5-year stats
    local5y_races INTEGER,
    local5y_win_rate FLOAT,
    local5y_tricast_rate FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (race_id, lane)
);

-- Predictions table
CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    race_id BIGINT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('claude', 'gemini', 'ensemble')),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Index scores (arrays of 6 values, one per lane)
    ei FLOAT[],
    ti FLOAT[],
    judgement TEXT[],

    -- Race pattern analysis
    pattern TEXT,
    main_attack TEXT,
    sink_candidate TEXT,
    suji TEXT,

    -- Betting recommendations
    exacta TEXT,
    trifecta TEXT,
    honmei_exacta TEXT[],
    honmei_trifecta TEXT[],
    ana_exacta TEXT[],
    ana_trifecta TEXT[],

    -- Classification
    classification TEXT,
    confidence FLOAT CHECK (confidence BETWEEN 0.0 AND 1.0),
    kyotei_data_raw BOOLEAN DEFAULT FALSE,
    is_correct BOOLEAN
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_races_date ON races(date);
CREATE INDEX IF NOT EXISTS idx_races_venue_date ON races(venue, date);
CREATE INDEX IF NOT EXISTS idx_boats_race_id ON boats(race_id);
CREATE INDEX IF NOT EXISTS idx_predictions_race_id ON predictions(race_id);
CREATE INDEX IF NOT EXISTS idx_predictions_source ON predictions(source);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at DESC);
