import { useState, useEffect, useRef } from 'react'
import { getVenues, runScraping, setTeleboadCookies, checkTeleboadCookies } from '../lib/api'

const SCRAPE_ITEMS = [
  { key: 'entry',         label: '出走表・選手データ',             note: 'boaters.com | 前日〜当日朝' },
  { key: 'motor',         label: '出足・伸び足・ランク',           note: 'boatfrontier.jp | 前日〜当日朝' },
  { key: 'exhibition',    label: '展示タイム・ST・天候',           note: 'boatrace.jp | レース15分前以降' },
  { key: 'profile',       label: 'コース別決まり手・2連対率',      note: 'boatrace.jp | 前日〜当日朝' },
  { key: 'raceinfo_time', label: '今節ST(公式)', note: 'boatrace.jp（テレボート認証必須）' },
]

interface ScrapeResult {
  venue: string
  item: string
  status: 'ok' | 'error'
  message?: string
}

export default function Scraping() {
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [allVenues, setAllVenues] = useState<string[]>([])
  const [selectedVenues, setSelectedVenues] = useState<string[]>([])
  const [selectedItems, setSelectedItems] = useState<string[]>(['entry'])
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [results, setResults] = useState<ScrapeResult[]>([])
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<number | null>(null)

  // テレボートCookie設定
  const [cookieInput, setCookieInput] = useState('')
  const [cookieStatus, setCookieStatus] = useState<string | null>(null)
  const [cookieInfo, setCookieInfo] = useState<{ status: string; cookie_count?: number } | null>(null)

  useEffect(() => {
    getVenues().then(res => setAllVenues(res.data.venues || [])).catch(() => {})
    checkTeleboadCookies().then(res => setCookieInfo(res.data)).catch(() => {})
  }, [])

  function toggleVenue(v: string) {
    setSelectedVenues(prev =>
      prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v]
    )
  }

  function toggleItem(key: string) {
    setSelectedItems(prev =>
      prev.includes(key) ? prev.filter(x => x !== key) : [...prev, key]
    )
  }

  async function handleSetCookies() {
    if (!cookieInput.trim()) return
    setCookieStatus('保存中…')
    try {
      const res = await setTeleboadCookies(cookieInput.trim())
      if (res.data.status === 'ok') {
        setCookieStatus(`保存完了 (${res.data.cookie_count}件)`)
        checkTeleboadCookies().then(r => setCookieInfo(r.data)).catch(() => {})
        setCookieInput('')
      } else {
        setCookieStatus(`エラー: ${res.data.message}`)
      }
    } catch (e) {
      setCookieStatus('保存失敗')
    }
  }

  function toggleAllVenues() {
    if (selectedVenues.length === allVenues.length) {
      setSelectedVenues([])
    } else {
      setSelectedVenues([...allVenues])
    }
  }

  async function handleRun() {
    if (selectedVenues.length === 0 || selectedItems.length === 0) return

    setStatus('running')
    setResults([])
    setElapsed(0)

    const start = Date.now()
    timerRef.current = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000))
    }, 1000)

    try {
      const allResults: ScrapeResult[] = []
      // 会場×項目ごとに1つずつ実行（Vercel 60秒タイムアウト対策）
      for (const venue of selectedVenues) {
        for (const item of selectedItems) {
          try {
            const res = await runScraping({ date, venues: [venue], items: [item] })
            allResults.push(...(res.data.results as ScrapeResult[]))
            setResults([...allResults])
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err)
            allResults.push({ venue, item, status: 'error', message: msg })
            setResults([...allResults])
          }
        }
      }
      setStatus('done')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setResults([{ venue: '全体', item: 'all', status: 'error', message: msg }])
      setStatus('error')
    } finally {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }

  const okCount = results.filter(r => r.status === 'ok').length
  const errCount = results.filter(r => r.status === 'error').length

  return (
    <div>
      <h2 className="page-title">データ取得</h2>

      <div className="scrape-controls">
        {/* Left: items + date */}
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">実行日時</div>
            <input
              type="date"
              className="date-input"
              value={date}
              onChange={e => setDate(e.target.value)}
              style={{ width: '100%' }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              レース数: {selectedVenues.length} 場所選択中
            </div>
          </div>

          <div className="card">
            <div className="card-title">取得項目</div>
            <div className="checkbox-group">
              {SCRAPE_ITEMS.map(item => (
                <label key={item.key} className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={selectedItems.includes(item.key)}
                    onChange={() => toggleItem(item.key)}
                  />
                  <div>
                    <div className="checkbox-label">{item.label}</div>
                    <div className="checkbox-note">{item.note}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Right: venues */}
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>開催場所</span>
            <button className="btn btn-sm btn-secondary" onClick={toggleAllVenues}>
              {selectedVenues.length === allVenues.length ? '全解除' : '全選択'}
            </button>
          </div>
          <div className="venue-grid">
            {allVenues.map(v => (
              <div
                key={v}
                className={`venue-checkbox ${selectedVenues.includes(v) ? 'selected' : ''}`}
                onClick={() => toggleVenue(v)}
              >
                {v}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Run button */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20 }}>
        <button
          className="btn btn-primary"
          onClick={handleRun}
          disabled={status === 'running' || selectedVenues.length === 0 || selectedItems.length === 0}
          style={{ minWidth: 140 }}
        >
          {status === 'running' ? '実行中…' : 'スクレイピング実行'}
        </button>
        {status === 'running' && (
          <div className="elapsed-display">{String(Math.floor(elapsed / 60)).padStart(2, '0')}:{String(elapsed % 60).padStart(2, '0')}</div>
        )}
        {status === 'done' && (
          <span style={{ fontSize: 13, color: 'var(--accent-green)' }}>
            完了: 成功 {okCount} / エラー {errCount}
          </span>
        )}
        {status === 'error' && (
          <span style={{ fontSize: 13, color: '#ef4444' }}>エラーが発生しました</span>
        )}
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="card">
          <div className="card-title">実行結果</div>
          <div className="scrape-results">
            {results.map((r, i) => (
              <div key={i} className={`scrape-result-item ${r.status}`}>
                <span className="scrape-status-icon">{r.status === 'ok' ? '✓' : '✗'}</span>
                <span className="scrape-venue">{r.venue}</span>
                <span className="scrape-item">
                  {SCRAPE_ITEMS.find(x => x.key === r.item)?.label || r.item}
                </span>
                {r.message && <span className="scrape-message">{r.message}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* テレボートCookie設定パネル */}
      <div className="card" style={{ marginTop: 24, borderColor: '#ca8a04' }}>
        <div className="card-title" style={{ color: '#92400e' }}>
          🔑 テレボートCookie設定（今節ST(公式) 取得に必要）
        </div>
        <div style={{ marginBottom: 8, fontSize: 12, color: '#78350f' }}>
          <strong>設定方法:</strong><br />
          1. PCブラウザで <a href="https://www.boatrace.jp" target="_blank" rel="noreferrer" style={{ color: '#b45309', textDecoration: 'underline' }}>boatrace.jp</a> にテレボートログイン<br />
          2. DevTools (F12) → Network タブ → 任意のリクエストを選択<br />
          3. Request Headers の <code>Cookie:</code> 行の値をすべてコピーして貼り付け
        </div>
        {cookieInfo && (
          <div style={{ marginBottom: 8, fontSize: 12, padding: '4px 8px', borderRadius: 4,
            background: cookieInfo.status === 'ok' ? '#d1fae5' : '#fef3c7',
            color: cookieInfo.status === 'ok' ? '#065f46' : '#92400e' }}>
            {cookieInfo.status === 'ok'
              ? `✅ Cookie保存済み (${cookieInfo.cookie_count}件)`
              : '⚠ Cookieが未設定です'}
          </div>
        )}
        <textarea
          value={cookieInput}
          onChange={e => setCookieInput(e.target.value)}
          style={{ width: '100%', height: 80, fontSize: 11, fontFamily: 'monospace',
            border: '1px solid #d97706', borderRadius: 4, padding: 8, boxSizing: 'border-box' }}
          placeholder="JSESSIONID=xxx; BRS_BRS=yyy; _abck=zzz; ..."
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
          <button
            onClick={handleSetCookies}
            disabled={!cookieInput.trim()}
            style={{ background: '#b45309', color: 'white', border: 'none', borderRadius: 4,
              padding: '6px 16px', fontSize: 13, cursor: cookieInput.trim() ? 'pointer' : 'not-allowed',
              opacity: cookieInput.trim() ? 1 : 0.5 }}
          >
            Cookieを保存
          </button>
          {cookieStatus && (
            <span style={{ fontSize: 12, color: cookieStatus.includes('完了') ? '#065f46' : '#b91c1c' }}>
              {cookieStatus}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
