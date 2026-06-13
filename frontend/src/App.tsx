import { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import RaceList from './pages/RaceList'
import RaceDetail from './pages/RaceDetail'
import Analytics from './pages/Analytics'
import Scraping from './pages/Scraping'
import Import from './pages/Import'
import Venues from './pages/Venues'

const LOCK_KEY = 'bp_unlocked'
const CORRECT_PW = 'boatrace2026'

function PasswordGate({ onUnlock }: { onUnlock: () => void }) {
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (input === CORRECT_PW) {
      sessionStorage.setItem(LOCK_KEY, '1')
      onUnlock()
    } else {
      setError(true)
      setInput('')
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #040d1f 0%, #0a1f3f 100%)', fontFamily: 'sans-serif'
    }}>
      <div style={{
        background: '#0d1b2e', border: '1px solid #1e3a5f', borderRadius: 14,
        padding: '40px 36px', maxWidth: 420, width: '90%', textAlign: 'center', boxShadow: '0 8px 40px #0005'
      }}>
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#60a5fa', letterSpacing: 2 }}>BOATRACE PREDICTOR</div>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>AI競艇予測システム</div>
        </div>
        <div style={{
          margin: '20px 0', padding: '14px 16px',
          background: 'linear-gradient(90deg, #1e2d1a, #0f2d1a)', border: '1px solid #22c55e44',
          borderRadius: 9
        }}>
          <div style={{ fontSize: 14, color: '#4ade80', fontWeight: 700, marginBottom: 6 }}>修正更新中</div>
          <div style={{ fontSize: 13, color: '#86efac', lineHeight: 1.7 }}>
            現在、システムの修正・更新作業を行っております。<br />
            完了しましたら、ロックを解除させていただきます。<br />
            しばらくお待ちください。
          </div>
        </div>
        <form onSubmit={handleSubmit} style={{ marginTop: 24 }}>
          <input
            type="password"
            value={input}
            onChange={e => { setInput(e.target.value); setError(false) }}
            placeholder="パスワードを入力"
            autoFocus
            style={{
              width: '100%', padding: '10px 14px', fontSize: 15,
              background: '#090f1e', border: `1px solid ${error ? '#ef4444' : '#1e3a5f'}`,
              borderRadius: 8, color: '#e2e8f0', outline: 'none', boxSizing: 'border-box',
              marginBottom: error ? 6 : 12
            }}
          />
          {error && (
            <div style={{ fontSize: 12, color: '#f87171', marginBottom: 10 }}>パスワードが違います</div>
          )}
          <button type="submit" style={{
            width: '100%', padding: '10px 0', background: 'linear-gradient(135deg,#1e40af,#3b82f6)',
            color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer'
          }}>
            ロック解除
          </button>
        </form>
      </div>
    </div>
  )
}

const NAV_LINKS = [
  { to: '/', label: 'レース一覧' },
  { to: '/analytics', label: '的中分析' },
  { to: '/scraping', label: 'データ取得' },
  { to: '/import', label: 'データ取込' },
  { to: '/venues', label: '会場設定' },
]

function AppLayout() {
  return (
    <div className="app-layout">
      <header className="header">
        <div className="header-brand">
          <div>
            <h1>BOATRACE PREDICTOR</h1>
            <div className="subtitle">AI競艇予測システム</div>
          </div>
        </div>
        <nav className="header-nav">
          {NAV_LINKS.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<RaceList />} />
          <Route path="/race/:id" element={<RaceDetail />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/scraping" element={<Scraping />} />
          <Route path="/import" element={<Import />} />
          <Route path="/venues" element={<Venues />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  const [unlocked, setUnlocked] = useState(() => sessionStorage.getItem(LOCK_KEY) === '1')

  if (!unlocked) {
    return <PasswordGate onUnlock={() => setUnlocked(true)} />
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </BrowserRouter>
  )
}
