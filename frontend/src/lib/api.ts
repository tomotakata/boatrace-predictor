import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface Boat {
  id?: number
  race_id?: number
  lane: number
  entry_course?: number
  name?: string
  age?: number
  weight?: number
  rank?: string
  f_count?: number
  branch?: string
  is_local?: boolean
  national_win_rate?: number
  national_place2_rate?: number
  local_win_rate?: number
  local_place2_rate?: number
  motor_no?: number
  motor_dashfoot?: number
  motor_extfoot?: number
  motor_eval?: string
  motor_rank?: number
  motor_rank_letter?: string
  motor_place2_rate?: number
  avg_st?: number
  gen_rate?: number
  today_st?: number
  today_st_rank?: number
  exhibition_st?: number
  standard_st?: number
  st_advantage_rank?: number
  exhibition_time?: number
  exhibition_1lap?: number
  exhibition_turning?: number
  exhibition_straight?: number
  c1_races?: number; c1_win_rate?: number; c1_tricast_rate?: number
  c2_races?: number; c2_win_rate?: number; c2_tricast_rate?: number
  c3_races?: number; c3_win_rate?: number; c3_tricast_rate?: number
  c4_races?: number; c4_win_rate?: number; c4_tricast_rate?: number
  c5_races?: number; c5_win_rate?: number; c5_tricast_rate?: number
  c6_races?: number; c6_win_rate?: number; c6_tricast_rate?: number
  local5y_races?: number
  local5y_win_rate?: number
  local5y_tricast_rate?: number
  local5y_place2_rate?: number
  local5y_sashi?: number; local5y_makuri?: number; local5y_makurizashi?: number
  // 直近1年コース別 平均ST/平均ST順（自コース・boatfrontier）
  course1y_st?: number
  course1y_st_rank?: number
  // 一般戦(G2,G3含む)直近1年（自コース・boatfrontier プレミアム）
  general1y_races?: number
  general1y_win_rate?: number
  general1y_place2_rate?: number
  general1y_tricast_rate?: number
  c2_rate?: number
  general1y_sashi?: number; general1y_makuri?: number; general1y_makurizashi?: number
  // イン逃げ時直近1年（自コース・boatfrontier プレミアム）
  escape1y_place2_rate?: number
  escape1y_tricast_rate?: number
  // コース別決まり手（boatrace.jp scrape_profile）
  c1_nige?: number; c1_sashi?: number; c1_makuri?: number; c1_makurizashi?: number; c1_place2_rate?: number
  c2_nige?: number; c2_sashi?: number; c2_makuri?: number; c2_makurizashi?: number; c2_place2_rate?: number
  c3_nige?: number; c3_sashi?: number; c3_makuri?: number; c3_makurizashi?: number; c3_place2_rate?: number
  c4_nige?: number; c4_sashi?: number; c4_makuri?: number; c4_makurizashi?: number; c4_place2_rate?: number
  c5_nige?: number; c5_sashi?: number; c5_makuri?: number; c5_makurizashi?: number; c5_place2_rate?: number
  c6_nige?: number; c6_sashi?: number; c6_makuri?: number; c6_makurizashi?: number; c6_place2_rate?: number
  // 握り・抜き
  nigiri_rate?: number
  nigiri_occurrence?: number
  nige_count?: number; sashi_count?: number; makuri_count?: number; makurisashi_count?: number
  // raceinfo_time (今節ST・1周T・回り足・出足・伸び足)
  season_st?: number
  lap1_time?: number
  turn_time?: number
  deashi?: number
  nobashi?: number
  created_at?: string
}

export interface SystemPredictionDetail {
  version?: string
  regime: string
  s_in: string
  surface_type: string
  head_boats: number[]
  head_type: string
  mech1e_active: boolean
  f1_head: number
  f2_head?: number
  benefit_2nd: Record<string, number[]>
  trifecta_f1: string[]
  trifecta_f2: string[]
  exacta: string[]
  manshu: string[]
  budget_main: number
  budget_exacta: number
  budget_manshu: number
  confidence: number
  wave_score: number
  regime_dispersion: number
  regime_hit_rate: number
  regime_attack_density: number
  notes: string[]
  boat_evals?: BoatEval[]
  // v58.7
  main_attack_course?: number
  attack_type?: string
  race_verdict?: string
  odds_available?: boolean
  synthetic_odds?: number
  payout?: number
  payout_grade?: string
  fire_boat_lane?: number
  fire_boat_gen?: number
  in_win_rate?: number
  sink_boat_lane?: number
  dkan_counts?: Record<string, number>
  cal_factor?: number
}

export interface BoatEval {
  lane: number
  course?: number
  name: string
  rank?: string
  p1?: number
  ei: number | null
  ti?: number | null
  st_rank: number | null
  ei_rank: number | null
  role: string
  attack_type?: string
  completion_power?: number
  dkan?: number
  gen_rate?: number
  hit_rate?: number
  is_fire?: boolean
  confidence_runs?: number
}

export interface Prediction {
  id?: number
  race_id?: number
  source: 'claude' | 'gemini' | 'ensemble' | 'system_v56'
  created_at?: string
  ei?: number[]
  ti?: number[]
  judgement?: string[]
  pattern?: string
  main_attack?: string
  sink_candidate?: string
  suji?: string
  exacta?: string
  trifecta?: string
  honmei_exacta?: string[]
  honmei_trifecta?: string[]
  ana_exacta?: string[]
  ana_trifecta?: string[]
  classification?: string
  confidence?: number
  kyotei_data_raw?: boolean
  is_correct?: boolean | null
}

export interface Race {
  id?: number
  race_no: number
  race_name?: string
  date: string
  venue: string
  day_no?: number
  status?: 'scheduled' | 'running' | 'finished'
  weather?: string
  temperature?: number
  wind_speed?: number
  wind_direction?: string
  wave_height?: number
  boats?: Boat[]
  predictions?: Prediction[]
  predictions_count?: number
  result?: { trifecta: string }
  created_at?: string
  odds_3t?: Record<string, number> | null
  odds_2t?: Record<string, number> | null
  odds_win?: Record<string, number> | null
  odds_updated_at?: string | null
}

export interface GradeStats {
  grade: string
  total: number
  trifecta_rate: number
  exacta_rate: number
}

export interface VenueStats {
  venue: string
  total: number
  evaluated: number
  trifecta_rate: number
  exacta_rate: number
}

export interface AccuracyData {
  total_predictions: number
  evaluated: number
  trifecta_rate: number
  exacta_rate: number
  by_source: Array<{ source: string; total: number; trifecta_rate: number; exacta_rate: number }>
  by_grade: GradeStats[]
}

export interface RecentPrediction {
  id: number
  date: string
  race: string
  venue: string
  race_no: number | null
  source: string
  trifecta: string
  confidence: number | null
  is_correct: boolean | null
  is_correct_exacta: boolean | null
  actual_trifecta: string | null
  payout_grade: string | null
}

export interface TimelinePoint {
  date: string
  total: number
  trifecta_rate: number | null
}

// Races API
export const getLatestDate = () =>
  api.get<{ date: string }>('/races/latest-date')

export const getRaces = (date?: string) =>
  api.get<Race[]>('/races/', { params: date ? { target_date: date } : {} })

export const getRace = (id: number) =>
  api.get<Race>(`/races/${id}`)

export const predictRace = (id: number, source: 'ensemble' | 'claude' | 'gemini' = 'ensemble') =>
  api.post<Race>(`/races/${id}/predict`, null, { params: { source } })

export const predictRaceSystem = (id: number) =>
  api.post<Race & { system_prediction_detail?: SystemPredictionDetail }>(`/races/${id}/predict-system`)

export const scrapeRaces = (date?: string) =>
  api.post('/races/scrape', null, { params: date ? { target_date: date } : {} })

// Analytics API
export const getAccuracy = (params?: { from_date?: string; to_date?: string }) =>
  api.get<AccuracyData>('/analytics/accuracy', { params })

export const getAccuracyByVenue = (params?: { from_date?: string; to_date?: string }) =>
  api.get<VenueStats[]>('/analytics/accuracy/by_venue', { params })

export const getAccuracyTimeline = (days = 30) =>
  api.get<TimelinePoint[]>('/analytics/accuracy/timeline', { params: { days } })

export const getRecentPredictions = (limit = 30) =>
  api.get<RecentPrediction[]>('/analytics/recent', { params: { limit } })

export const triggerEvaluate = (fromDate: string, toDate: string) =>
  api.post<{ status: string; updated: number; skipped: number; total: number }>(
    '/scrape/evaluate',
    { from_date: fromDate, to_date: toDate }
  )

export const triggerScrapeHistory = (fromDate: string, toDate: string, venues?: string[]) =>
  api.post<{ summary: string; from_date: string; to_date: string }>(
    '/scrape/scrape_history',
    { from_date: fromDate, to_date: toDate, venues: venues || [] }
  )

export const importClaudeChat = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<{ imported: number; skipped: number }>('/analytics/import/claude', formData)
}

export const importGeminiChat = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<{ imported: number; skipped: number }>('/analytics/import/gemini', formData)
}

// Scraping API
export const getVenues = () =>
  api.get<{ venues: string[] }>('/scrape/venues')

export const runScraping = (data: { date: string; venues: string[]; items: string[] }) =>
  api.post<{ results: Array<{ venue: string; item: string; status: string; message?: string }> }>('/scrape/run', data)

export const scrapeRaceResult = (data: { date: string; venue: string }) =>
  api.post<{ date: string; results: Array<{ venue: string; item: string; status: string; saved?: number; message?: string }>; summary?: string }>('/scrape/results', data)

export const setTeleboadCookies = (cookies: string) =>
  api.post<{ status: string; cookie_count?: number; message?: string }>('/scrape/set_teleboat_cookies', { cookies })

export const checkTeleboadCookies = () =>
  api.get<{ status: string; cookie_count?: number; names?: string[]; message?: string }>('/scrape/check_teleboat_cookies')

// Venue Config API
export interface VenueConfig {
  id?: number
  venue_name: string
  prompt_version?: string
  water_type?: string
  has_tide_correction?: boolean
  tide_max_m?: number
  altitude_m?: number
  back_width_m?: number
  home_width_m?: number
  c1_rate_default?: number
  c2_rate?: number; c3_rate?: number; c4_rate?: number; c5_rate?: number; c6_rate?: number
  c1_rate_spring?: number; c1_rate_summer?: number; c1_rate_autumn?: number; c1_rate_winter?: number
  surface_type?: string
  pattern_a_threshold?: number
  main_attack_description?: string
  main_attack_patterns?: string[]
  kad_c2?: number; kad_c3?: number; kad_c4?: number; kad_c5?: number; kad_c6?: number
  home_branch?: string; home_n_upper?: number; home_n_lower?: number; home_min_races?: number
  motor_exchange_months?: number[]
  motor_exchange_f_weight?: number; motor_exchange_n_upper?: number
  scheduled_races?: Array<{ race_no: number; name: string; c1_rate?: number; c2_rate?: number }>
  body_weight_correction?: boolean; exhibit_public?: boolean
  is_nighter?: boolean; is_morning?: boolean; is_midnight?: boolean
  tide_effects?: Record<string, string>
  wind_effects?: Record<string, string>
  seasonal_notes?: Record<string, string>
  race_no_corrections?: Array<{ race_no: number; c1_multiplier?: number }>
  notes?: string
  raw_prompt_text?: string
  created_at?: string; updated_at?: string
}

export const listVenueConfigs = () =>
  api.get<VenueConfig[]>('/venues/')

export const getVenueConfig = (venueName: string) =>
  api.get<VenueConfig>(`/venues/${encodeURIComponent(venueName)}`)

export const createVenueConfig = (data: VenueConfig) =>
  api.post<VenueConfig>('/venues/', data)

export const updateVenueConfig = (venueName: string, data: VenueConfig) =>
  api.put<VenueConfig>(`/venues/${encodeURIComponent(venueName)}`, data)

export const deleteVenueConfig = (venueName: string) =>
  api.delete(`/venues/${encodeURIComponent(venueName)}`)

// Race Result API
export interface RaceResult {
  race_key?: string
  winner_lane?: number | null
  winner_course?: number | null
  place2_lane?: number | null
  place3_lane?: number | null
  trifecta_result?: string | null
  exacta_result?: string | null
  trifecta_payout?: number | null
  exacta_payout?: number | null
  trifecta_place_payout?: number | null
  result_all?: Record<string, number> | null
}

export const getRaceResult = (raceId: number) =>
  api.get<RaceResult>(`/races/${raceId}/result`)

export const savePredictionMemo = (raceId: number, memo: string) =>
  api.patch<{ status: string }>(`/races/${raceId}/prediction/memo`, { memo })

// Shishido Predict API
export interface ShishidoPrediction {
  venue: string
  date: string
  race_no: number
  status: string
  error?: string
  prediction?: {
    venue?: string
    date?: string
    race_no?: number
    analysis?: {
      attack_subject?: { course: number; type: string; attack_type: string }
      head?: number[]
      box?: number[]
      honsen_12?: string[]
      race_class?: string
      exacta_top?: string[]
      suichi?: string[]
      dashboard?: Record<string, { EI: number; TI: number; P1: number; nige: number; place: number; second: number }>
    }
    reasoning?: string
  }
  raw_response?: string
}

export const getShishidoVenues = (date: string) =>
  api.get<{ date: string; venues: string[] }>('/shishido/venues', { params: { date } })

export const runShishidoPredict = (date: string, venue: string, raceNo?: number) =>
  api.post<{ date: string; venue: string; results: ShishidoPrediction[] }>(
    '/shishido/predict',
    { date, venue, race_no: raceNo || null },
    { timeout: 600000 }  // 10分タイムアウト（全12レース分）
  )
