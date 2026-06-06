import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getRace, predictRace, predictRaceSystem, type Race, type Boat, type Prediction, type SystemPredictionDetail } from '../lib/api'

const LANE_COLORS = ['#2c2c4e', '#3a3a3a', '#7b241c', '#1a5276', '#7d6608', '#1e8449']

const JUDGEMENT_CONFIG: Record<string, { label: string; cls: string }> = {
  '頭': { label: '頭', cls: 'j-head' },
  '軸': { label: '軸', cls: 'j-pivot' },
  '紐': { label: '紐', cls: 'j-string' },
  '消': { label: '消', cls: 'j-out' },
}

const SOURCE_CONFIG = {
  claude: { label: 'Claude', cls: 'source-claude', color: '#f59e0b' },
  gemini: { label: 'Gemini', cls: 'source-gemini', color: '#34d399' },
  ensemble: { label: 'Ensemble', cls: 'source-ensemble', color: '#a78bfa' },
  system_v56: { label: 'システム v56.3', cls: 'source-ensemble', color: '#60a5fa' },
}

function ScoreCell({ value }: { value?: number }) {
  if (value === undefined || value === null) return <td style={{ color: 'var(--text-muted)' }}>—</td>
  const cls = value >= 7 ? 'score-high' : value >= 4 ? 'score-mid' : 'score-low'
  return <td><span className={`index-score ${cls}`}>{value.toFixed(1)}</span></td>
}

function JudgementCell({ value }: { value?: string }) {
  if (!value) return <td>—</td>
  const cfg = JUDGEMENT_CONFIG[value] || { label: value, cls: 'j-out' }
  return <td><span className={`judgement-badge ${cfg.cls}`}>{cfg.label}</span></td>
}

function formatStat(v?: number | null, decimals = 2) {
  if (v === undefined || v === null) return '—'
  return v.toFixed(decimals)
}

function BoatTable({ boats, prediction }: { boats: Boat[]; prediction?: Prediction }) {
  return (
    <div className="boat-table-wrapper">
      <table className="boat-table">
        <thead>
          <tr>
            <th>艇</th>
            <th className="boat-name-cell">選手</th>
            <th>全勝</th>
            <th>当勝</th>
            <th>全2連</th>
            <th>当2連</th>
            <th>モーター</th>
            <th>出足</th>
            <th>伸足</th>
            <th>M2連</th>
            <th>展示T</th>
            <th>展示ST</th>
            <th>平均ST</th>
            {prediction && <th>EI</th>}
            {prediction && <th>TI</th>}
            {prediction && <th>判定</th>}
          </tr>
        </thead>
        <tbody>
          {boats.map((boat) => {
            const laneColor = LANE_COLORS[(boat.lane - 1) % 6]
            const ei = prediction?.ei?.[boat.lane - 1]
            const ti = prediction?.ti?.[boat.lane - 1]
            const judgement = prediction?.judgement?.[boat.lane - 1]
            return (
              <tr key={boat.lane}>
                <td>
                  <span className="lane-badge" style={{ background: laneColor }}>
                    {boat.lane}
                  </span>
                </td>
                <td className="boat-name-cell" style={{ fontWeight: 600 }}>
                  {boat.name || '—'}
                  {boat.rank && <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>{boat.rank}</span>}
                </td>
                <td>{formatStat(boat.national_win_rate)}</td>
                <td>{formatStat(boat.local_win_rate)}</td>
                <td>{formatStat(boat.national_place2_rate)}</td>
                <td>{formatStat(boat.local_place2_rate)}</td>
                <td style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-secondary)' }}>
                  {boat.motor_no ? `#${boat.motor_no}` : '—'}
                </td>
                <td>{formatStat(boat.motor_dashfoot, 1)}</td>
                <td>{formatStat(boat.motor_extfoot, 1)}</td>
                <td>{formatStat(boat.motor_place2_rate)}</td>
                <td style={{ color: 'var(--accent-blue-light)', fontWeight: 600 }}>
                  {formatStat(boat.exhibition_time, 2)}
                </td>
                <td>{formatStat(boat.exhibition_st, 2)}</td>
                <td>{formatStat(boat.avg_st, 2)}</td>
                {prediction && <ScoreCell value={ei} />}
                {prediction && <ScoreCell value={ti} />}
                {prediction && <JudgementCell value={judgement} />}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function PredictionPanel({ prediction }: { prediction: Prediction }) {
  const src = prediction.source as keyof typeof SOURCE_CONFIG
  const srcCfg = SOURCE_CONFIG[src] || SOURCE_CONFIG.ensemble

  return (
    <div className="prediction-card">
      <div className="prediction-header">
        <span className={`prediction-source-label source-badge ${srcCfg.cls}`}>{srcCfg.label}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {prediction.classification && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{prediction.classification}</span>
          )}
          {prediction.confidence !== undefined && prediction.confidence !== null && (
            <div>
              <div className="confidence-label">信頼度: {Math.round((prediction.confidence || 0) * 100)}%</div>
              <div className="confidence-bar" style={{ width: 100 }}>
                <div className="confidence-fill" style={{ width: `${(prediction.confidence || 0) * 100}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="prediction-body">
        <div className="prediction-section">
          <h4>本命3連単</h4>
          <div className="trifecta-display">{prediction.trifecta || '—'}</div>
          {prediction.exacta && (
            <>
              <h4 style={{ marginTop: 12 }}>本命2連単</h4>
              <div className="exacta-display">{prediction.exacta}</div>
            </>
          )}
          {prediction.honmei_trifecta && prediction.honmei_trifecta.length > 0 && (
            <>
              <h4 style={{ marginTop: 12 }}>本命党 3連単</h4>
              <div className="bet-list">
                {prediction.honmei_trifecta.map((b, i) => (
                  <span key={i} className="bet-item honmei">{b}</span>
                ))}
              </div>
            </>
          )}
          {prediction.ana_trifecta && prediction.ana_trifecta.length > 0 && (
            <>
              <h4 style={{ marginTop: 12 }}>穴党 3連単</h4>
              <div className="bet-list">
                {prediction.ana_trifecta.map((b, i) => (
                  <span key={i} className="bet-item ana">{b}</span>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="prediction-section">
          {prediction.pattern && (
            <>
              <h4>展開パターン</h4>
              <p className="analysis-text" style={{ marginBottom: 12 }}>{prediction.pattern}</p>
            </>
          )}
          {prediction.main_attack && (
            <>
              <h4>主要な攻め手</h4>
              <p className="analysis-text" style={{ marginBottom: 12 }}>{prediction.main_attack}</p>
            </>
          )}
          {prediction.sink_candidate && (
            <>
              <h4>沈み候補</h4>
              <p className="analysis-text" style={{ marginBottom: 12 }}>{prediction.sink_candidate}</p>
            </>
          )}
          {prediction.suji && (
            <>
              <h4>特記</h4>
              <p className="analysis-text">{prediction.suji}</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function SystemPredictionPanel({ detail }: { detail: SystemPredictionDetail }) {
  const regimeColor = detail.regime === '順当' ? '#34d399' : detail.regime === '隠れ混戦' ? '#f59e0b' : '#f87171'
  const sInColor = detail.s_in === 'イン強' ? '#60a5fa' : detail.s_in === 'イン弱' ? '#f87171' : '#a78bfa'

  return (
    <div className="prediction-card" style={{ borderColor: '#60a5fa', borderWidth: 2 }}>
      <div className="prediction-header" style={{ borderBottom: '1px solid #1e3a5f', paddingBottom: 12, marginBottom: 12 }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 15 }}>システム予測 v56.3</span>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ padding: '2px 10px', borderRadius: 12, background: regimeColor + '22', color: regimeColor, fontSize: 12, border: `1px solid ${regimeColor}` }}>
            {detail.regime}
          </span>
          <span style={{ padding: '2px 10px', borderRadius: 12, background: sInColor + '22', color: sInColor, fontSize: 12, border: `1px solid ${sInColor}` }}>
            {detail.s_in}（{detail.surface_type}水面）
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            自信度: {Math.round(detail.confidence)}% / 波乱度: {Math.round(detail.wave_score)}%
          </span>
        </div>
      </div>

      {/* レジーム3軸 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 }}>
        <div style={{ background: '#0f1e35', padding: '8px 12px', borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>分散</div>
          <div style={{ fontWeight: 700, color: '#e2e8f0' }}>{detail.regime_dispersion}pt</div>
        </div>
        <div style={{ background: '#0f1e35', padding: '8px 12px', borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>本命被弾</div>
          <div style={{ fontWeight: 700, color: detail.regime_hit_rate >= 30 ? '#f59e0b' : '#e2e8f0' }}>{detail.regime_hit_rate}%</div>
        </div>
        <div style={{ background: '#0f1e35', padding: '8px 12px', borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>攻め密度</div>
          <div style={{ fontWeight: 700, color: detail.regime_attack_density >= 2 ? '#f59e0b' : '#e2e8f0' }}>{detail.regime_attack_density}枚</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* F1フォーメーション */}
        <div>
          <h4 style={{ margin: '0 0 8px', color: '#60a5fa', fontSize: 13 }}>
            本線F1（頭: {detail.f1_head}号・¥{detail.budget_main.toLocaleString()}）
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {detail.trifecta_f1.length > 0 ? detail.trifecta_f1.map((t, i) => (
              <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 13, border: '1px solid #2d5a8e' }}>{t}</span>
            )) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
          </div>
        </div>

        {/* F2フォーメーション */}
        <div>
          <h4 style={{ margin: '0 0 8px', color: detail.mech1e_active ? '#a78bfa' : 'var(--text-muted)', fontSize: 13 }}>
            本線F2{detail.f2_head ? `（頭: ${detail.f2_head}号）` : ''}
            {detail.mech1e_active && <span style={{ fontSize: 11, marginLeft: 6, color: '#a78bfa' }}>機構1-E発動</span>}
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {detail.trifecta_f2.length > 0 ? detail.trifecta_f2.map((t, i) => (
              <span key={i} style={{ background: '#2d1f5e', color: '#c4b5fd', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 13, border: '1px solid #4c3a9e' }}>{t}</span>
            )) : <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>なし</span>}
          </div>
        </div>
      </div>

      {/* 二連単 */}
      <div style={{ marginBottom: 16 }}>
        <h4 style={{ margin: '0 0 8px', color: '#34d399', fontSize: 13 }}>
          二連単（¥{detail.budget_exacta.toLocaleString()}・上限3点）
        </h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {detail.exacta.length > 0 ? detail.exacta.map((e, i) => (
            <span key={i} style={{ background: '#0f2d23', color: '#6ee7b7', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 13, border: '1px solid #1a5c40' }}>{e}</span>
          )) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
        </div>
      </div>

      {/* 万舟 */}
      <div>
        <h4 style={{ margin: '0 0 8px', color: '#f59e0b', fontSize: 13 }}>
          万舟（全レース必須・¥{detail.budget_manshu.toLocaleString()}・各目100倍以上目標）
        </h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {detail.manshu.map((m, i) => (
            <span key={i} style={{ background: '#2d1a00', color: '#fcd34d', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 12, border: '1px solid #78450a' }}>{m}</span>
          ))}
        </div>
      </div>

      {/* メモ */}
      {detail.notes.length > 0 && (
        <div style={{ marginTop: 12, padding: '8px 12px', background: '#1a0a00', borderRadius: 8, borderLeft: '3px solid #f59e0b' }}>
          {detail.notes.map((n, i) => (
            <div key={i} style={{ fontSize: 12, color: '#fcd34d', marginBottom: 2 }}>⚠ {n}</div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function RaceDetail() {
  const { id } = useParams<{ id: string }>()
  const [race, setRace] = useState<Race | null>(null)
  const [loading, setLoading] = useState(true)
  const [predicting, setPredicting] = useState(false)
  const [systemDetail, setSystemDetail] = useState<SystemPredictionDetail | null>(null)
  const [activePredIdx, setActivePredIdx] = useState(0)

  async function fetchRace() {
    if (!id) return
    setLoading(true)
    try {
      const res = await getRace(parseInt(id))
      setRace(res.data)
    } catch {
      setRace(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchRace() }, [id])

  async function handlePredict(source: 'ensemble' | 'claude' | 'gemini') {
    if (!id) return
    setPredicting(true)
    try {
      const res = await predictRace(parseInt(id), source)
      setRace(res.data)
      setActivePredIdx(0)
    } catch {
      // handle error
    } finally {
      setPredicting(false)
    }
  }

  async function handlePredictSystem() {
    if (!id) return
    setPredicting(true)
    try {
      const res = await predictRaceSystem(parseInt(id))
      setRace(res.data)
      setSystemDetail(res.data.system_prediction_detail || null)
      setActivePredIdx(0)
    } catch {
      // handle error
    } finally {
      setPredicting(false)
    }
  }

  if (loading) {
    return <div className="loading-spinner"><div className="spinner" />読み込み中…</div>
  }

  if (!race) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">⚠️</div>
        <div className="empty-state-text">レースが見つかりません</div>
        <div style={{ marginTop: 12 }}>
          <Link to="/" className="btn btn-secondary">一覧に戻る</Link>
        </div>
      </div>
    )
  }

  const predictions = race.predictions || []
  const activePred = predictions[activePredIdx]
  const status = race.status || 'scheduled'
  const statusConfig = {
    scheduled: { label: '発売中', cls: 'status-scheduled' },
    running: { label: '発走中', cls: 'status-running' },
    finished: { label: '確定', cls: 'status-finished' },
  }
  const sc = statusConfig[status as keyof typeof statusConfig]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/" style={{ color: 'var(--text-muted)', fontSize: 13, textDecoration: 'none' }}>
          ← レース一覧
        </Link>
      </div>

      <div className="race-detail-header">
        <div className="race-info">
          <div className="race-venue-name">
            {race.venue} {race.race_no}R
            {race.race_name && <span style={{ fontSize: 14, color: 'var(--text-secondary)', marginLeft: 8 }}>{race.race_name}</span>}
          </div>
          <div className="race-meta">
            {race.date} &nbsp;|&nbsp;
            <span className={`status-badge ${sc.cls}`}>{sc.label}</span>
          </div>
          {(race.weather || race.wind_speed) && (
            <div className="weather-info">
              {race.weather && <span>天候: {race.weather}</span>}
              {race.wind_speed && <span>風速: {race.wind_speed}m</span>}
              {race.wind_direction && <span>風向: {race.wind_direction}</span>}
              {race.wave_height && <span>波高: {race.wave_height}cm</span>}
            </div>
          )}
        </div>

        <div className="predict-actions">
          <button
            className="btn"
            style={{ background: 'linear-gradient(135deg, #1e40af, #3b82f6)', color: '#fff', fontWeight: 700 }}
            onClick={handlePredictSystem}
            disabled={predicting}
          >
            {predicting ? '予測中…' : 'システム予測 v56.3'}
          </button>
          <button
            className="btn btn-warning"
            onClick={() => handlePredict('ensemble')}
            disabled={predicting}
          >
            AI予測 (Ensemble)
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => handlePredict('claude')}
            disabled={predicting}
            style={{ color: '#f59e0b', borderColor: '#f59e0b' }}
          >
            Claude
          </button>

        </div>
      </div>

      {/* Boats table */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title">出走表・選手データ</div>
        {race.boats && race.boats.length > 0 ? (
          <BoatTable boats={race.boats} prediction={activePred} />
        ) : (
          <div className="empty-state" style={{ padding: '30px 20px' }}>
            <div className="empty-state-text">出走表データなし</div>
          </div>
        )}
      </div>

      {/* System Prediction Detail */}
      {systemDetail && (
        <div className="prediction-panel" style={{ marginBottom: 24 }}>
          <SystemPredictionPanel detail={systemDetail} />
        </div>
      )}

      {/* Predictions */}
      {predictions.length > 0 && (
        <div className="prediction-panel">
          <div className="card-title" style={{ marginBottom: 16 }}>AI予測</div>
          {predictions.length > 1 && (
            <div className="pred-tabs">
              {predictions.map((p, i) => {
                const src = p.source as keyof typeof SOURCE_CONFIG
                const srcCfg = SOURCE_CONFIG[src] || SOURCE_CONFIG.ensemble
                const activeClass = i === activePredIdx ? `active-${p.source}` : ''
                return (
                  <button
                    key={i}
                    className={`pred-tab ${activeClass}`}
                    onClick={() => setActivePredIdx(i)}
                  >
                    {srcCfg.label}
                  </button>
                )
              })}
            </div>
          )}
          {activePred && <PredictionPanel prediction={activePred} />}
        </div>
      )}

      {predicting && (
        <div className="loading-spinner" style={{ marginTop: 16 }}>
          <div className="spinner" />
          AI予測を生成中…
        </div>
      )}
    </div>
  )
}
