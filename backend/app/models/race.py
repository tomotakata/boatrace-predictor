from typing import Optional, List
from pydantic import BaseModel


class BoatModel(BaseModel):
    id: Optional[int] = None
    race_id: Optional[int] = None
    lane: int
    name: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    rank: Optional[str] = None
    f_count: Optional[int] = None
    is_local: Optional[bool] = None

    national_win_rate: Optional[float] = None
    national_place2_rate: Optional[float] = None
    local_win_rate: Optional[float] = None
    local_place2_rate: Optional[float] = None

    motor_no: Optional[int] = None
    motor_dashfoot: Optional[float] = None
    motor_extfoot: Optional[float] = None
    motor_eval: Optional[str] = None
    motor_rank_letter: Optional[str] = None
    motor_place2_rate: Optional[float] = None

    avg_st: Optional[float] = None
    today_st: Optional[float] = None
    today_st_rank: Optional[int] = None
    exhibition_st: Optional[float] = None
    standard_st: Optional[float] = None
    st_advantage_rank: Optional[int] = None

    exhibition_time: Optional[float] = None
    exhibition_1lap: Optional[float] = None
    exhibition_turning: Optional[float] = None
    exhibition_straight: Optional[float] = None

    c1_races: Optional[int] = None
    c1_win_rate: Optional[float] = None
    c1_tricast_rate: Optional[float] = None
    c2_races: Optional[int] = None
    c2_win_rate: Optional[float] = None
    c2_tricast_rate: Optional[float] = None
    c3_races: Optional[int] = None
    c3_win_rate: Optional[float] = None
    c3_tricast_rate: Optional[float] = None
    c4_races: Optional[int] = None
    c4_win_rate: Optional[float] = None
    c4_tricast_rate: Optional[float] = None
    c5_races: Optional[int] = None
    c5_win_rate: Optional[float] = None
    c5_tricast_rate: Optional[float] = None
    c6_races: Optional[int] = None
    c6_win_rate: Optional[float] = None
    c6_tricast_rate: Optional[float] = None

    local5y_races: Optional[int] = None
    local5y_win_rate: Optional[float] = None
    local5y_tricast_rate: Optional[float] = None

    created_at: Optional[str] = None


class PredictionModel(BaseModel):
    id: Optional[int] = None
    race_id: Optional[int] = None
    source: str  # "claude" | "gemini" | "ensemble"
    created_at: Optional[str] = None

    ei: Optional[List[float]] = None
    ti: Optional[List[float]] = None
    judgement: Optional[List[str]] = None

    pattern: Optional[str] = None
    main_attack: Optional[str] = None
    sink_candidate: Optional[str] = None
    suji: Optional[str] = None

    exacta: Optional[str] = None
    trifecta: Optional[str] = None
    honmei_exacta: Optional[List[str]] = None
    honmei_trifecta: Optional[List[str]] = None
    ana_exacta: Optional[List[str]] = None
    ana_trifecta: Optional[List[str]] = None

    classification: Optional[str] = None
    confidence: Optional[float] = None
    kyotei_data_raw: Optional[bool] = None
    is_correct: Optional[bool] = None


class RaceModel(BaseModel):
    id: Optional[int] = None
    race_no: int
    race_name: Optional[str] = None
    date: str
    venue: str
    day_no: Optional[int] = None
    status: Optional[str] = "scheduled"
    weather: Optional[str] = None
    temperature: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[str] = None
    wave_height: Optional[float] = None
    boats: Optional[List[BoatModel]] = []
    predictions: Optional[List[PredictionModel]] = []
    predictions_count: Optional[int] = 0
    result: Optional[dict] = None
    created_at: Optional[str] = None
