import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getRace, predictRace, predictRaceSystem, type Race, type Boat, type Prediction, type SystemPredictionDetail } from '../lib/api'

// ── 艇番カラー（1=黒, 2=白, 3=赤, 4=青, 5=黄, 6=緑）────────────────────
const LANE_BG   = ['#1a1a1a', '#e8e8e8', '#9b1a1a', '#1a3a9b', '#9b8a00', '#1a6b1a']
const LANE_TEXT = ['#ffffff', '#000000', '#ffffff', '#ffffff', '#ffffff', '#ffffff']

// セクションヘッダー背景
const SEC_COLORS: Record<string, string> = {
  '①基本':                '#1a2d1a',
  '②モーター':            '#1a1a2d',
  '③スタート・展示':      '#2d1a1a',
  '⑤a コース別(直近1年)': '#1a2d2d',
}

function fmt(v?: number | null, d = 2): string {
  if (v === undefined || v === null) return '—'
  return v.toFixed(d)
}

// ── 6艇ヘッダー行 ────────────────────────────────────────────────────────
function LaneHeader({ boats }: { boats: Boat[] }) {
  return (
    <tr>
      <td style={{ width: 80, background: '#0a1520', color: '#64748b', fontSize: 11, padding: '4px 8px' }} />
      {[1,2,3,4,5,6].map(lane => {
        const boat = boats.find(b => b.lane === lane)
        return (
          <td key={lane} style={{
            background: LANE_BG[lane-1], color: LANE_TEXT[lane-1],
            textAlign: 'center', fontWeight: 700, fontSize: 13, padding: '6px 4px', width: 80,
          }}>
            {lane}
            {boat?.name && (
              <div style={{ fontSize: 10, fontWeight: 400, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 76 }}>
                {boat.name}
              </div>
            )}
          </td>
        )
      })}
    </tr>
  )
}

// ── 1行コンポーネント ─────────────────────────────────────────────────────
type CellVal = string | number | null | undefined
type HighlightFn = (v: CellVal, boats: Boat[]) => boolean

function DataRow({
  label, boats, getValue, decimals = 2, highlight, labelColor,
}: {
  label: string
  boats: Boat[]
  getValue: (b: Boat) => CellVal
  decimals?: number
  highlight?: HighlightFn
  labelColor?: string
}) {
  const vals = [1,2,3,4,5,6].map(lane => boats.find(b => b.lane === lane))
  return (
    <tr style={{ borderBottom: '1px solid #0d1f30' }}>
      <td style={{ padding: '5px 8px', fontSize: 12, color: labelColor || '#94a3b8', background: '#0a1520', whiteSpace: 'nowrap' }}>
        {label}
      </td>
      {vals.map((boat, i) => {
        const raw = boat ? getValue(boat) : undefined
        const display = typeof raw === 'number' ? fmt(raw, decimals)
                      : raw === undefined || raw === null ? '—'
                      : String(raw)
        const isHL = highlight ? highlight(raw, boats.filter(Boolean) as Boat[]) : false
        return (
          <td key={i} style={{
            textAlign: 'center', fontSize: 13, padding: '5px 4px',
            color: isHL ? '#f59e0b' : '#e2e8f0',
            fontWeight: isHL ? 700 : 400,
          }}>
            {display}
          </td>
        )
      })}
    </tr>
  )
}

// ── セクションラッパー ────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const bg = SEC_COLORS[title] || '#1a1a2d'
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ background: bg, borderLeft: '3px solid #3b82f6', padding: '6px 12px', fontSize: 13, fontWeight: 700, color: '#93c5fd' }}>
        {title}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: 80 }} />
            {[1,2,3,4,5,6].map(i => <col key={i} style={{ width: 80 }} />)}
          </colgroup>
          <tbody>
            {children}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── ハイライトヘルパー（最大値強調）─────────────────────────────────────
function maxHL(getValue: (b: Boat) => CellVal): HighlightFn {
  return (v, boats) => {
    if (v === null || v === undefined) return false
    const nums = boats.map(b => getValue(b)).filter(x => x !== null && x !== undefined) as number[]
    if (nums.length === 0) return false
    return v === Math.max(...nums)
  }
}
function minHL(getValue: (b: Boat) => CellVal): HighlightFn {
  return (v, boats) => {
    if (v === null || v === undefined) return false
    const nums = boats.map(b => getValue(b)).filter(x => x !== null && x !== undefined) as number[]
    if (nums.length === 0) return false
    return v === Math.min(...nums)
  }
}

// ── メインデータセクション群 ─────────────────────────────────────────────
function RaceDataSections({ boats }: { boats: Boat[] }) {
  return (
    <div>
      {/* ① 基本 */}
      <Section title="①基本">
        <LaneHeader boats={boats} />
        <DataRow label="ランク"    boats={boats} getValue={b => b.rank} decimals={0} />
        <DataRow label="年齢"      boats={boats} getValue={b => b.age}  decimals={0} />
        <DataRow label="F回数"     boats={boats} getValue={b => b.f_count} decimals={0} />
        <DataRow label="全国勝率"  boats={boats} getValue={b => b.national_win_rate} highlight={maxHL(b => b.national_win_rate)} />
        <DataRow label="当地勝率"  boats={boats} getValue={b => b.local_win_rate}    highlight={maxHL(b => b.local_win_rate)} />
        <DataRow label="全国2連率" boats={boats} getValue={b => b.national_place2_rate} highlight={maxHL(b => b.national_place2_rate)} />
        <DataRow label="当地2連率" boats={boats} getValue={b => b.local_place2_rate}    highlight={maxHL(b => b.local_place2_rate)} />
      </Section>

      {/* ② モーター */}
      <Section title="②モーター">
        <LaneHeader boats={boats} />
        <DataRow label="モーターNo" boats={boats} getValue={b => b.motor_no}           decimals={0} />
        <DataRow label="出足"        boats={boats} getValue={b => b.motor_dashfoot}     decimals={1} highlight={maxHL(b => b.motor_dashfoot)} />
        <DataRow label="伸び足"      boats={boats} getValue={b => b.motor_stretch ?? (b as any).motor_extfoot} decimals={1} highlight={maxHL(b => b.motor_stretch ?? (b as any).motor_extfoot)} />
        <DataRow label="モーター2連" boats={boats} getValue={b => b.motor_place2_rate} highlight={maxHL(b => b.motor_place2_rate)} />
        <DataRow label="ボートNo"    boats={boats} getValue={b => b.boat_no}            decimals={0} />
        <DataRow label="ボート2連"   boats={boats} getValue={b => b.boat_place2_rate}   highlight={maxHL(b => b.boat_place2_rate)} />
      </Section>

      {/* ③ スタート・展示 */}
      <Section title="③スタート・展示">
        <LaneHeader boats={boats} />
        <DataRow label="展示T"  boats={boats} getValue={b => b.exhibition_time} decimals={2}
          highlight={minHL(b => b.exhibition_time)} />
        <DataRow label="展示ST" boats={boats} getValue={b => b.exhibition_st}   decimals={2}
          highlight={minHL(b => b.exhibition_st)} />
        <DataRow label="平均ST" boats={boats} getValue={b => b.avg_st}          decimals={2}
          highlight={minHL(b => b.avg_st)} />
      </Section>

      {/* ⑤a コース別（直近1年） */}
      {boats.some(b => b.national_win_rate != null) && (
        <Section title="⑤a コース別(直近1年)">
          <LaneHeader boats={boats} />
          <DataRow label="全国勝率%"  boats={boats} getValue={b => b.national_win_rate}    highlight={maxHL(b => b.national_win_rate)} />
          <DataRow label="全国2連%"   boats={boats} getValue={b => b.national_place2_rate} highlight={maxHL(b => b.national_place2_rate)} />
          <DataRow label="当地勝率%"  boats={boats} getValue={b => b.local_win_rate}       highlight={maxHL(b => b.local_win_rate)} />
          <DataRow label="当地2連%"   boats={boats} getValue={b => b.local_place2_rate}    highlight={maxHL(b => b.local_place2_rate)} />
        </Section>
      )}
    </div>
  )
}

// ── 予測・判定パネル（既存） ──────────────────────────────────────────────
const SOURCE_CONFIG = {
  claude:     { label: 'Claude',          color: '#f59e0b' },
  gemini:     { label: 'Gemini',          color: '#34d399' },
  ensemble:   { label: 'Ensemble',        color: '#a78bfa' },
  system_v56: { label: 'システム v56.3', color: '#60a5fa' },
}

const JUDGEMENT_CONFIG: Record<string, { cls: string }> = {
  '頭': { cls: 'j-head' }, '軸': { cls: 'j-pivot' }, '紐': { cls: 'j-string' }, '消': { cls: 'j-out' },
}

function ScoreCell({ value }: { value?: number }) {
  if (value === undefined || value === null) return <td style={{ color: '#64748b' }}>—</td>
  const color = value >= 70 ? '#34d399' : value >= 50 ? '#f59e0b' : '#94a3b8'
  return <td style={{ textAlign: 'center', color, fontWeight: 700, fontSize: 15 }}>{value}</td>
}

function JudgementCell({ value }: { value?: string }) {
  if (!value) return <td>—</td>
  const cfg = JUDGEMENT_CONFIG[value] || { cls: 'j-out' }
  return <td><span className={`judgement-badge ${cfg.cls}`}>{value}</span></td>
}

function PredictionPanel({ prediction }: { prediction: Prediction }) {
  const src = prediction.source as keyof typeof SOURCE_CONFIG
  const srcCfg = SOURCE_CONFIG[src] || SOURCE_CONFIG.ensemble

  return (
    <div className="prediction-card">
      <div className="prediction-header">
        <span style={{ fontWeight: 700, color: srcCfg.color }}>{srcCfg.label}</span>
        {prediction.confidence !== undefined && prediction.confidence !== null && (
          <div>
            <div style={{ fontSize: 12, color: '#64748b' }}>信頼度: {Math.round((prediction.confidence || 0) * 100)}%</div>
            <div className="confidence-bar" style={{ width: 100 }}>
              <div className="confidence-fill" style={{ width: `${(prediction.confidence || 0) * 100}%` }} />
            </div>
          </div>
        )}
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
              <div className="bet-list">{prediction.honmei_trifecta.map((b, i) => <span key={i} className="bet-item honmei">{b}</span>)}</div>
            </>
          )}
          {prediction.ana_trifecta && prediction.ana_trifecta.length > 0 && (
            <>
              <h4 style={{ marginTop: 12 }}>穴党 3連単</h4>
              <div className="bet-list">{prediction.ana_trifecta.map((b, i) => <span key={i} className="bet-item ana">{b}</span>)}</div>
            </>
          )}
        </div>
        <div className="prediction-section">
          {prediction.pattern      && <><h4>展開パターン</h4><p className="analysis-text">{prediction.pattern}</p></>}
          {prediction.main_attack  && <><h4>主要な攻め手</h4><p className="analysis-text">{prediction.main_attack}</p></>}
          {prediction.sink_candidate && <><h4>沈み候補</h4><p className="analysis-text">{prediction.sink_candidate}</p></>}
          {prediction.suji         && <><h4>特記</h4><p className="analysis-text">{prediction.suji}</p></>}
        </div>
      </div>

      {/* EI / TI 行 */}
      {(prediction.ei || prediction.ti) && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
            <colgroup><col style={{ width: 80 }} />{[1,2,3,4,5,6].map(i => <col key={i} style={{ width: 80 }} />)}</colgroup>
            <tbody>
              <tr style={{ borderBottom: '1px solid #0d1f30' }}>
                <td style={{ padding: '4px 8px', fontSize: 11, color: '#64748b', background: '#0a1520' }}>艇番</td>
                {[1,2,3,4,5,6].map(lane => (
                  <td key={lane} style={{ textAlign: 'center', background: LANE_BG[lane-1], color: LANE_TEXT[lane-1], fontWeight: 700, fontSize: 13, padding: '5px 4px' }}>{lane}</td>
                ))}
              </tr>
              {prediction.ei && (
                <tr>
                  <td style={{ padding: '4px 8px', fontSize: 12, color: '#94a3b8', background: '#0a1520' }}>EI</td>
                  {[0,1,2,3,4,5].map(i => <ScoreCell key={i} value={prediction.ei![i]} />)}
                </tr>
              )}
              {prediction.ti && (
                <tr>
                  <td style={{ padding: '4px 8px', fontSize: 12, color: '#94a3b8', background: '#0a1520' }}>TI</td>
                  {[0,1,2,3,4,5].map(i => <ScoreCell key={i} value={prediction.ti![i]} />)}
                </tr>
              )}
              {prediction.judgement && (
                <tr>
                  <td style={{ padding: '4px 8px', fontSize: 12, color: '#94a3b8', background: '#0a1520' }}>判定</td>
                  {[0,1,2,3,4,5].map(i => <JudgementCell key={i} value={prediction.judgement![i]} />)}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SystemPredictionPanel({ detail }: { detail: SystemPredictionDetail }) {
  const regimeColor = detail.regime === '順当' ? '#34d399' : detail.regime === '隠れ混戦' ? '#f59e0b' : '#f87171'
  const sInColor    = detail.s_in === 'イン強' ? '#60a5fa' : detail.s_in === 'イン弱' ? '#f87171' : '#a78bfa'

  return (
    <div className="prediction-card" style={{ borderColor: '#60a5fa', borderWidth: 2 }}>
      <div className="prediction-header" style={{ borderBottom: '1px solid #1e3a5f', paddingBottom: 12, marginBottom: 12 }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 15 }}>システム予測 v56.3</span>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ padding: '2px 10px', borderRadius: 12, background: regimeColor + '22', color: regimeColor, fontSize: 12, border: `1px solid ${regimeColor}` }}>{detail.regime}</span>
          <span style={{ padding: '2px 10px', borderRadius: 12, background: sInColor + '22', color: sInColor, fontSize: 12, border: `1px solid ${sInColor}` }}>{detail.s_in}（{detail.surface_type}水面）</span>
          <span style={{ fontSize: 12, color: '#64748b' }}>自信度: {Math.round(detail.confidence)}% / 波乱度: {Math.round(detail.wave_score)}%</span>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 16 }}>
        <div style={{ background: '#0f1e35', padding: '8px 12px', borderRadius: 8 }}><div style={{ fontSize: 11, color: '#64748b' }}>分散</div><div style={{ fontWeight: 700, color: '#e2e8f0' }}>{detail.regime_dispersion}pt</div></div>
        <div style={{ background: '#0f1e35', padding: '8px 12px', borderRadius: 8 }}><div style={{ fontSize: 11, color: '#64748b' }}>本命被弾</div><div style={{ fontWeight: 700, color: detail.regime_hit_rate >= 30 ? '#f59e0b' : '#e2e8f0' }}>{detail.regime_hit_rate}%</div></div>
        <div style={{ background: '#0f1e35', padding: '8px 12px', borderRadius: 8 }}><div style={{ fontSize: 11, color: '#64748b' }}>攻め密度</div><div style={{ fontWeight: 700, color: detail.regime_attack_density >= 2 ? '#f59e0b' : '#e2e8f0' }}>{detail.regime_attack_density}枚</div></div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div>
          <h4 style={{ margin: '0 0 8px', color: '#60a5fa', fontSize: 13 }}>本線F1（頭: {detail.f1_head}号・¥{detail.budget_main.toLocaleString()}）</h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {detail.trifecta_f1.length > 0 ? detail.trifecta_f1.map((t, i) => (
              <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 13, border: '1px solid #2d5a8e' }}>{t}</span>
            )) : <span style={{ color: '#64748b' }}>—</span>}
          </div>
        </div>
        <div>
          <h4 style={{ margin: '0 0 8px', color: detail.mech1e_active ? '#a78bfa' : '#64748b', fontSize: 13 }}>
            本線F2{detail.f2_head ? `（頭: ${detail.f2_head}号）` : ''}{detail.mech1e_active && <span style={{ fontSize: 11, marginLeft: 6, color: '#a78bfa' }}>機構1-E発動</span>}
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {detail.trifecta_f2.length > 0 ? detail.trifecta_f2.map((t, i) => (
              <span key={i} style={{ background: '#2d1f5e', color: '#c4b5fd', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 13, border: '1px solid #4c3a9e' }}>{t}</span>
            )) : <span style={{ color: '#64748b', fontSize: 13 }}>なし</span>}
          </div>
        </div>
      </div>
      <div style={{ marginBottom: 16 }}>
        <h4 style={{ margin: '0 0 8px', color: '#34d399', fontSize: 13 }}>二連単（¥{detail.budget_exacta.toLocaleString()}・上限3点）</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {detail.exacta.length > 0 ? detail.exacta.map((e, i) => (
            <span key={i} style={{ background: '#0f2d23', color: '#6ee7b7', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 13, border: '1px solid #1a5c40' }}>{e}</span>
          )) : <span style={{ color: '#64748b' }}>—</span>}
        </div>
      </div>
      <div>
        <h4 style={{ margin: '0 0 8px', color: '#f59e0b', fontSize: 13 }}>万舟（全レース必須・¥{detail.budget_manshu.toLocaleString()}・各目100倍以上目標）</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {detail.manshu.map((m, i) => (
            <span key={i} style={{ background: '#2d1a00', color: '#fcd34d', padding: '3px 10px', borderRadius: 6, fontFamily: 'monospace', fontSize: 12, border: '1px solid #78450a' }}>{m}</span>
          ))}
        </div>
      </div>
      {detail.notes.length > 0 && (
        <div style={{ marginTop: 12, padding: '8px 12px', background: '#1a0a00', borderRadius: 8, borderLeft: '3px solid #f59e0b' }}>
          {detail.notes.map((n, i) => <div key={i} style={{ fontSize: 12, color: '#fcd34d', marginBottom: 2 }}>⚠ {n}</div>)}
        </div>
      )}
    </div>
  )
}

// ── メインページ ──────────────────────────────────────────────────────────
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
    try { setRace((await getRace(parseInt(id))).data) }
    catch { setRace(null) }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchRace() }, [id])

  async function handlePredict(source: 'ensemble' | 'claude' | 'gemini') {
    if (!id) return
    setPredicting(true)
    try { const r = await predictRace(parseInt(id), source); setRace(r.data); setActivePredIdx(0) }
    catch {}
    finally { setPredicting(false) }
  }

  async function handlePredictSystem() {
    if (!id) return
    setPredicting(true)
    try {
      const r = await predictRaceSystem(parseInt(id))
      setRace(r.data)
      setSystemDetail(r.data.system_prediction_detail || null)
      setActivePredIdx(0)
    } catch {}
    finally { setPredicting(false) }
  }

  if (loading) return <div className="loading-spinner"><div className="spinner" />読み込み中…</div>

  if (!race) return (
    <div className="empty-state">
      <div className="empty-state-icon">⚠️</div>
      <div className="empty-state-text">レースが見つかりません</div>
      <Link to="/" className="btn btn-secondary" style={{ marginTop: 12 }}>一覧に戻る</Link>
    </div>
  )

  const predictions = race.predictions || []
  const activePred  = predictions[activePredIdx]
  const sc = ({ scheduled: { label: '発売中', cls: 'status-scheduled' }, running: { label: '発走中', cls: 'status-running' }, finished: { label: '確定', cls: 'status-finished' } })[race.status as 'scheduled' | 'running' | 'finished'] || { label: race.status, cls: 'status-scheduled' }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/" style={{ color: '#64748b', fontSize: 13, textDecoration: 'none' }}>← レース一覧</Link>
      </div>

      {/* ── ヘッダー ── */}
      <div className="race-detail-header">
        <div className="race-info">
          <div className="race-venue-name">
            {race.venue} {race.race_no}R
            {race.race_name && <span style={{ fontSize: 14, color: '#94a3b8', marginLeft: 8 }}>{race.race_name}</span>}
          </div>
          <div className="race-meta">
            {race.date} &nbsp;|&nbsp;
            <span className={`status-badge ${sc.cls}`}>{sc.label}</span>
          </div>
          {(race.weather || race.wind_speed) && (
            <div className="weather-info">
              {race.weather       && <span>天候: {race.weather}</span>}
              {race.wind_speed    && <span>風速: {race.wind_speed}m</span>}
              {race.wind_direction && <span>風向: {race.wind_direction}</span>}
              {race.wave_height   && <span>波高: {race.wave_height}cm</span>}
            </div>
          )}
        </div>
        <div className="predict-actions">
          <button className="btn" style={{ background: 'linear-gradient(135deg,#1e40af,#3b82f6)', color: '#fff', fontWeight: 700 }}
            onClick={handlePredictSystem} disabled={predicting}>
            {predicting ? '予測中…' : 'システム予測 v56.3'}
          </button>
          <button className="btn btn-warning" onClick={() => handlePredict('ensemble')} disabled={predicting}>AI予測 (Ensemble)</button>
          <button className="btn btn-secondary btn-sm" onClick={() => handlePredict('claude')} disabled={predicting} style={{ color: '#f59e0b', borderColor: '#f59e0b' }}>Claude</button>
        </div>
      </div>

      {/* ── セクション別データ表示 ── */}
      <div className="card" style={{ marginBottom: 24, padding: 16 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>出走表・選手データ</div>
        {race.boats && race.boats.length > 0 ? (
          <RaceDataSections boats={race.boats} />
        ) : (
          <div className="empty-state" style={{ padding: '30px 20px' }}>
            <div className="empty-state-text">出走表データなし（スクレイピングを実行してください）</div>
          </div>
        )}
      </div>

      {/* ── システム予測詳細 ── */}
      {systemDetail && (
        <div className="prediction-panel" style={{ marginBottom: 24 }}>
          <SystemPredictionPanel detail={systemDetail} />
        </div>
      )}

      {/* ── AI予測 ── */}
      {predictions.length > 0 && (
        <div className="prediction-panel">
          <div className="card-title" style={{ marginBottom: 16 }}>AI予測</div>
          {predictions.length > 1 && (
            <div className="pred-tabs">
              {predictions.map((p, i) => {
                const srcCfg = SOURCE_CONFIG[p.source as keyof typeof SOURCE_CONFIG] || SOURCE_CONFIG.ensemble
                return (
                  <button key={i} className={`pred-tab ${i === activePredIdx ? `active-${p.source}` : ''}`} onClick={() => setActivePredIdx(i)}>
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
          <div className="spinner" />AI予測を生成中…
        </div>
      )}
    </div>
  )
}
