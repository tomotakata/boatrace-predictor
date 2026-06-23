import { useState, useEffect, useCallback } from 'react'
import { getShishidoVenues, runShishidoPredict, ShishidoPrediction } from '../lib/api'

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// ダッシュボード1行
function DashboardRow({ boat, data }: { boat: string; data: Record<string, number> }) {
  return (
    <tr>
      <td>
        <span className={`lane-badge lane-${boat}`}>{boat}</span>
      </td>
      <td className="index-score">{data.EI?.toFixed(1) ?? '-'}</td>
      <td className="index-score">{data.TI?.toFixed(1) ?? '-'}</td>
      <td>{data.P1?.toFixed(1) ?? '-'}</td>
      <td>{data.nige ?? '-'}</td>
      <td>{data.place ?? '-'}</td>
      <td>{data.second ?? '-'}</td>
    </tr>
  )
}

// 1レース分の結果カード
function RaceResultCard({ result }: { result: ShishidoPrediction }) {
  if (result.status === 'error') {
    return (
      <div className="card" style={{ marginBottom: 16, borderColor: 'var(--accent-red)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--accent-red)' }}>
            R{result.race_no}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>エラー</span>
        </div>
        <div style={{ fontSize: 13, color: 'var(--accent-red)' }}>
          {result.error || 'データ取得に失敗しました'}
        </div>
      </div>
    )
  }

  const pred = result.prediction
  if (!pred) return null
  const analysis = pred.analysis || {}

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {/* ヘッダー */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            fontSize: 18, fontWeight: 800, color: 'var(--accent-blue-light)',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            R{result.race_no}
          </span>
          {analysis.race_class && (
            <span className={`status-badge ${
              analysis.race_class === '勝負' ? 'status-running' :
              analysis.race_class === '見送り' ? 'status-finished' : 'status-scheduled'
            }`}>
              {analysis.race_class}
            </span>
          )}
        </div>
      </div>

      {/* 攻め主体 */}
      {analysis.attack_subject && (
        <div style={{
          padding: '10px 14px', background: 'var(--bg-secondary)', borderRadius: 8,
          marginBottom: 14, border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase' as const }}>
            攻め主体
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--accent-yellow)' }}>
            {analysis.attack_subject.course}コース {analysis.attack_subject.type} ({analysis.attack_subject.attack_type})
          </div>
        </div>
      )}

      {/* 本線12点 */}
      {analysis.honsen_12 && analysis.honsen_12.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' as const }}>
            本線 {analysis.honsen_12.length}点
          </div>
          <div className="bet-list">
            {analysis.honsen_12.map((bet: string, i: number) => (
              <span key={i} className="bet-item honmei">{bet}</span>
            ))}
          </div>
        </div>
      )}

      {/* 2連単・スイチ */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        {analysis.exacta_top && analysis.exacta_top.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' as const }}>
              2連単
            </div>
            <div className="bet-list">
              {analysis.exacta_top.map((bet: string, i: number) => (
                <span key={i} className="bet-item">{bet}</span>
              ))}
            </div>
          </div>
        )}
        {analysis.suichi && analysis.suichi.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' as const }}>
              スイチ（万舟）
            </div>
            <div className="bet-list">
              {analysis.suichi.map((bet: string, i: number) => (
                <span key={i} className="bet-item ana">{bet}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ダッシュボード */}
      {analysis.dashboard && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' as const }}>
            ダッシュボード
          </div>
          <div className="boat-table-wrapper">
            <table className="boat-table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>艇</th>
                  <th>EI</th>
                  <th>TI</th>
                  <th>P1</th>
                  <th>逃</th>
                  <th>連</th>
                  <th>2着</th>
                </tr>
              </thead>
              <tbody>
                {['1', '2', '3', '4', '5', '6'].map(b => {
                  const d = analysis.dashboard?.[b]
                  if (!d) return null
                  return <DashboardRow key={b} boat={b} data={d} />
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 推論要約 */}
      {pred.reasoning && (
        <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase' as const }}>
            判断要約
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            {pred.reasoning}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ShishidoPredict() {
  const [date, setDate] = useState(formatDate(new Date()))
  const [venues, setVenues] = useState<string[]>([])
  const [selectedVenue, setSelectedVenue] = useState('')
  const [loading, setLoading] = useState(false)
  const [venuesLoading, setVenuesLoading] = useState(false)
  const [results, setResults] = useState<ShishidoPrediction[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)

  // 会場一覧取得
  const fetchVenues = useCallback(async (d: string) => {
    setVenuesLoading(true)
    setSelectedVenue('')
    setResults(null)
    setError(null)
    try {
      const res = await getShishidoVenues(d)
      const v = res.data.venues || []
      setVenues(v)
      if (v.length > 0) setSelectedVenue(v[0])
    } catch (e: any) {
      setVenues([])
      setError('会場一覧の取得に失敗しました: ' + (e.response?.data?.detail || e.message))
    } finally {
      setVenuesLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchVenues(date)
  }, [date, fetchVenues])

  // タイマー
  useEffect(() => {
    if (!loading) return
    const start = Date.now()
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [loading])

  // 予想実行
  const handlePredict = async () => {
    if (!selectedVenue) return
    setLoading(true)
    setResults(null)
    setError(null)
    setElapsed(0)
    try {
      const res = await runShishidoPredict(date, selectedVenue)
      // 全レース結果
      if (res.data.results) {
        setResults(res.data.results)
      } else {
        // 単一レース結果
        setResults([res.data as any])
      }
    } catch (e: any) {
      setError('予想実行に失敗しました: ' + (e.response?.data?.detail || e.message))
    } finally {
      setLoading(false)
    }
  }

  const formatElapsed = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return m > 0 ? `${m}分${sec}秒` : `${sec}秒`
  }

  return (
    <div>
      <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        宍戸予想 v58.7
        <span style={{
          fontSize: 11, padding: '2px 10px', background: 'rgba(167,139,250,0.15)',
          border: '1px solid rgba(167,139,250,0.3)', borderRadius: 20, color: '#a78bfa', fontWeight: 600,
        }}>
          Claude API
        </span>
      </h2>

      {/* コントロール */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="controls-row">
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>日付</label>
            <input
              type="date"
              className="date-input"
              value={date}
              onChange={e => setDate(e.target.value)}
              disabled={loading}
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>会場</label>
            {venuesLoading ? (
              <div className="loading-spinner"><div className="spinner" /> 会場取得中...</div>
            ) : venues.length > 0 ? (
              <select
                className="date-input"
                value={selectedVenue}
                onChange={e => setSelectedVenue(e.target.value)}
                disabled={loading}
                style={{ minWidth: 120 }}
              >
                {venues.map(v => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            ) : (
              <div style={{ fontSize: 13, color: 'var(--text-muted)', padding: '8px 0' }}>
                開催なし
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}>
            <button
              className="btn btn-primary"
              onClick={handlePredict}
              disabled={loading || !selectedVenue}
              style={{ marginTop: 18 }}
            >
              {loading ? (
                <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> 予想実行中...</>
              ) : (
                '全レース予想実行'
              )}
            </button>
            {loading && (
              <div className="elapsed-display" style={{ marginTop: 18 }}>
                {formatElapsed(elapsed)}
              </div>
            )}
          </div>
        </div>
        {loading && (
          <div style={{
            padding: '12px 16px', background: 'rgba(59,130,246,0.08)',
            border: '1px solid rgba(59,130,246,0.2)', borderRadius: 8,
            fontSize: 12, color: 'var(--accent-blue-light)', lineHeight: 1.7,
          }}>
            Claude API で全12レースの予想を実行中です。1レースあたり30秒〜1分程度かかります。<br />
            しばらくお待ちください...
          </div>
        )}
      </div>

      {/* エラー */}
      {error && (
        <div style={{
          padding: '14px 18px', background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8,
          fontSize: 13, color: '#ef4444', marginBottom: 20,
        }}>
          {error}
        </div>
      )}

      {/* 結果 */}
      {results && results.length > 0 && (
        <div>
          <div style={{
            fontSize: 14, fontWeight: 700, color: 'var(--text-secondary)',
            marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8,
          }}>
            予想結果
            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400 }}>
              {results.filter(r => r.status === 'ok').length} / {results.length} レース成功
            </span>
          </div>
          {results.map((r, i) => (
            <RaceResultCard key={i} result={r} />
          ))}
        </div>
      )}
    </div>
  )
}
