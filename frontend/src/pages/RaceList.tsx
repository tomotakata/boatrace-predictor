import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { format, addDays, subDays } from 'date-fns'
import { ja } from 'date-fns/locale'
import { getRaces, getLatestDate, scrapeRaces, type Race } from '../lib/api'

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
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const dateInputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  // 起動時: データがある最新日付を自動取得
  useEffect(() => {
    getLatestDate()
      .then(res => {
        const latest = res.data.date
        setDate(latest)
        return fetchRaces(latest)
      })
      .catch(() => fetchRaces(today))
  }, [])

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

  async function handleScrape() {
    setScraping(true)
    try {
      await scrapeRaces(date)
      await fetchRaces(date)
    } finally {
      setScraping(false)
    }
  }

  function changeDate(newDate: string) {
    setDate(newDate)
    fetchRaces(newDate)
  }

  function goPrev() {
    const prev = format(subDays(new Date(date + 'T00:00:00'), 1), 'yyyy-MM-dd')
    changeDate(prev)
  }

  function goNext() {
    const next = format(addDays(new Date(date + 'T00:00:00'), 1), 'yyyy-MM-dd')
    changeDate(next)
  }

  function goToday() {
    const t = new Date().toISOString().slice(0, 10)
    changeDate(t)
  }

  function toggleVenue(venue: string) {
    setCollapsed(prev => ({ ...prev, [venue]: !prev[venue] }))
  }

  const isToday = date === new Date().toISOString().slice(0, 10)

  const grouped = groupByVenue(races)

  return (
    <div>
      <h2 className="page-title">レース一覧</h2>

      <div className="controls-row">
        <div className="date-nav">
          <button className="date-nav-arrow" onClick={goPrev} title="前日">◀</button>
          <button
            className="date-nav-display"
            onClick={() => dateInputRef.current?.showPicker()}
            title="カレンダーを開く"
          >
            <span className="date-nav-main">{formatDate(date)}</span>
            <span className="date-nav-sub">{date.replace(/-/g, '/')}</span>
          </button>
          <button className="date-nav-arrow" onClick={goNext} title="翌日">▶</button>
          <input
            ref={dateInputRef}
            type="date"
            className="date-input-hidden"
            value={date}
            onChange={e => {
              if (e.target.value) changeDate(e.target.value)
            }}
            tabIndex={-1}
          />
        </div>
        {!isToday && (
          <button className="btn btn-today" onClick={goToday}>今日</button>
        )}
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
        Object.entries(grouped).map(([venue, venueRaces]) => {
          const isCollapsed = collapsed[venue] ?? false
          return (
            <div key={venue} className="venue-group">
              <button
                className={`venue-header-toggle ${isCollapsed ? 'collapsed' : ''}`}
                onClick={() => toggleVenue(venue)}
              >
                <span className="venue-header-name">{venue}</span>
                <span className="venue-header-count">{venueRaces.length}R</span>
                <span className="venue-header-chevron">{isCollapsed ? '▶' : '▼'}</span>
              </button>
              {!isCollapsed && (
                <div className="race-grid">
                  {venueRaces.map(race => {
                    const status = race.status || 'scheduled'
                    const sc = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.scheduled
                    const trifecta = race.result?.trifecta
                    return (
                      <div
                        key={race.id}
                        className="race-card"
                        onClick={() => navigate(`/race/${race.id}`)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={e => { if (e.key === 'Enter') navigate(`/race/${race.id}`) }}
                      >
                        <div className="race-card-no">{race.race_no}R</div>
                        <span className={`status-badge ${sc.cls}`}>{sc.label}</span>
                        <div className="race-card-result">
                          {trifecta || '—'}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })
      )}
    </div>
  )
}
