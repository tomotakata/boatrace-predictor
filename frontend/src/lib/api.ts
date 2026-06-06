import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface Boat {
  id?: number
  race_id?: number
  lane: number
  name?: string
  age?: number
  weight?: number
  rank?: string
  f_count?: number
  is_local?: boolean
  national_win_rate?: number
  national_place2_rate?: number
  local_win_rate?: number
  local_place2_rate?: number
  motor_no?: number
  motor_dashfoot?: number
  motor_extfoot?: number
  motor_eval?: string
  motor_rank_letter?: string
  motor_place2_rate?: number
  avg_st?: number
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
  created_at?: string
}

export interface SystemPredictionDetail {
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
}

export interface AccuracyData {
  total_predictions: number
  trifecta_rate: number
  exacta_rate: number
  by_source: Array<{ source: string; rate: number; total: number }>
}

export interface RecentPrediction {
  id: number
  date: string
  race: string
  source: 'claude' | 'gemini' | 'ensemble'
  trifecta: string
  confidence: number | null
  is_correct: boolean | null
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
export const getAccuracy = () =>
  api.get<AccuracyData>('/analytics/accuracy')

export const getRecentPredictions = (limit = 20) =>
  api.get<RecentPrediction[]>('/analytics/recent', { params: { limit } })

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
