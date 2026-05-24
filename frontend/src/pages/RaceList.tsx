import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import { ja } from 'date-fns/locale'
import { getRaces, scrapeRaces, type Race } from '../lib/api'

const STATUS_CONFIG = {
  scheduled: { label: '発売中', cls: 'status-scheduled' },
  running: { label: '発走中', cls: 'status-running' },
  finished: { label: '確定', cls: 'status-finished' },
}

function groupByVenue(races: Race[]): Record<string, Race[]> {
  return races.reduce((acc, race) => {
    if (!acc[race.venue]) acc[race.venue] = []
    acc[race.venue].push(race)
    return acc
  }, {} as Record<string, Race[]>)
}

function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return format(d, 'M月d日(E)', { locale: ja })
  } catch {
    return dateStr
  }
}

export default function RaceList() {
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [races, setRaces] = useState<Race[]>([])
  const [loading, setLoading] = useState(true)
  const [scraping, setScraping] = useState(false)

  async function fetchRaces(d: string) {
    setLoading(true)
    try {
      const res = await getRaces(d)
      setRaces(res.data)
    } catch {
      setRaces([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchRaces(date) }, [date])

  async function handleScrape() {
    setScraping(true)
    try {
      await scrapeRaces(date)
      await fetchRaces(date)
    } finally {
      setScraping(false)
    }
  }

  const grouped = groupByVenue(races)

  return (
    <div>
      <h2 className="page-title">レース一覧</h2>

      <div className="controls-row">
        <input
          type="date"
          className="date-input"
          value={date}
          onChange={e => setDate(e.target.value)}
        />
        <span className="text-secondary" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
          {formatDate(date)}
        </span>
        <button className="btn btn-secondary" onClick={() => fetchRaces(date)} disabled={loading}>
          {loading ? '読み込み中…' : '更新'}
        </button>
        <button className="btn btn-primary" onClick={handleScrape} disabled={scraping || loading}>
          {scraping ? '取得中…' : 'スクレイピング実行'}
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
          読み込み中…
        </div>
      ) : races.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🚤</div>
          <div className="empty-state-text">
            {formatDate(date)} のレースデータがありません
          </div>
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-primary" onClick={handleScrape} disabled={scraping}>
              {scraping ? '取得中…' : 'データを取得する'}
            </button>
          </div>
        </div>
      ) : (
        Object.entries(grouped).map(([venue, venueRaces]) => (
          <div key={venue} className="venue-group">
            <div className="venue-header">{venue}</div>
            <div className="card" style={{ padding: 0 }}>
              <table className="race-table">
                <thead>
                  <tr>
                    <th>R</th>
                    <th>レース名</th>
                    <th>ステータス</th>
                    <th>予測数</th>
                    <th>3連単</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {venueRaces.map(race => {
                    const status = race.status || 'scheduled'
                    const sc = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.scheduled
                    return (
                      <tr key={race.id}>
                        <td style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: 'var(--accent-blue-light)' }}>
                          {race.race_no}R
                        </td>
                        <td>
                          <Link to={`/race/${race.id}`} className="race-link">
                            {race.race_name || `${race.race_no}R`}
                          </Link>
                        </td>
                        <td>
                          <span className={`status-badge ${sc.cls}`}>{sc.label}</span>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono, monospace' }}>
                          {race.predictions_count ?? 0}
                        </td>
                        <td style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent-yellow)' }}>
                          {race.predictions && race.predictions[0]?.trifecta || '—'}
                        </td>
                        <td>
                          <Link to={`/race/${race.id}`} className="btn btn-sm btn-secondary">
                            詳細
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
