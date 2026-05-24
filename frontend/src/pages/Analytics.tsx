import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { getAccuracy, getRecentPredictions, type AccuracyData, type RecentPrediction } from '../lib/api'

const SOURCE_COLORS: Record<string, string> = {
  claude: '#f59e0b',
  gemini: '#34d399',
  ensemble: '#a78bfa',
}

export default function Analytics() {
  const [accuracy, setAccuracy] = useState<AccuracyData | null>(null)
  const [recent, setRecent] = useState<RecentPrediction[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      setLoading(true)
      try {
        const [accRes, recRes] = await Promise.all([
          getAccuracy(),
          getRecentPredictions(20),
        ])
        setAccuracy(accRes.data)
        setRecent(recRes.data)
      } catch {
        // ignore
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return <div className="loading-spinner"><div className="spinner" />読み込み中…</div>
  }

  const acc = accuracy || { total_predictions: 0, trifecta_rate: 0, exacta_rate: 0, by_source: [] }

  return (
    <div>
      <h2 className="page-title">的中分析</h2>

      {/* Stats cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{acc.total_predictions}</div>
          <div className="stat-label">総予測数</div>
        </div>
        <div className="stat-card">
          <div className="stat-value highlight">{acc.trifecta_rate.toFixed(1)}%</div>
          <div className="stat-label">3連単的中率</div>
        </div>
        <div className="stat-card">
          <div className="stat-value highlight">{acc.exacta_rate.toFixed(1)}%</div>
          <div className="stat-label">2連単的中率</div>
        </div>
      </div>

      {/* Chart */}
      {acc.by_source.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">ソース別的中率</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={acc.by_source} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis dataKey="source" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} unit="%" />
              <Tooltip
                contentStyle={{ background: '#1a1a2e', border: '1px solid #2d3748', borderRadius: 6 }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Bar dataKey="rate" name="的中率" radius={[4, 4, 0, 0]}>
                {acc.by_source.map((entry, idx) => (
                  <Cell key={idx} fill={SOURCE_COLORS[entry.source] || '#60a5fa'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent predictions */}
      <div className="card">
        <div className="card-title">最近の予測</div>
        {recent.length === 0 ? (
          <div className="empty-state" style={{ padding: '30px 20px' }}>
            <div className="empty-state-text">予測データなし</div>
          </div>
        ) : (
          <table className="race-table">
            <thead>
              <tr>
                <th>日付</th>
                <th>レース</th>
                <th>ソース</th>
                <th>3連単</th>
                <th>信頼度</th>
                <th>結果</th>
              </tr>
            </thead>
            <tbody>
              {recent.map(p => (
                <tr key={p.id}>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{p.date}</td>
                  <td style={{ fontWeight: 600 }}>{p.race}</td>
                  <td>
                    <span className={`source-badge source-${p.source}`}>{p.source}</span>
                  </td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent-yellow)' }}>
                    {p.trifecta || '—'}
                  </td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                    {p.confidence !== null ? `${Math.round((p.confidence || 0) * 100)}%` : '—'}
                  </td>
                  <td>
                    {p.is_correct === true && <span className="correct-badge correct-yes">的中</span>}
                    {p.is_correct === false && <span className="correct-badge correct-no">外れ</span>}
                    {p.is_correct === null && <span className="correct-badge correct-null">未確定</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
