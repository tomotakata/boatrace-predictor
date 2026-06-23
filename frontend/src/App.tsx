import { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import RaceList from './pages/RaceList'
import RaceDetail from './pages/RaceDetail'
import Analytics from './pages/Analytics'
import Scraping from './pages/Scraping'
import Import from './pages/Import'
import Venues from './pages/Venues'
import DotSystem from './pages/DotSystem'
import ShishidoPredict from './pages/ShishidoPredict'

const LOCK_KEY = 'bp_unlocked'
const CORRECT_PW = 'boatrace2026'
const DOT_PW = 'Yalove0911'
const DOT_KEY = 'dot_unlocked'

function DotPasswordModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (input === DOT_PW) {
      sessionStorage.setItem(DOT_KEY, '1')
      onSuccess()
    } else {
      setError(true)
      setInput('')
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: '#0d1b2e', border: '1px solid #1e3a5f', borderRadius: 12,
        padding: '32px 28px', maxWidth: 360, width: '90%', textAlign: 'center',
        boxShadow: '0 8px 40px #0008',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 700, color: '#60a5fa', marginBottom: 4 }}>
          DOTシステム
        </div>
        <div style={{ fontSize: 12, color: '#64748b', marginBottom: 20 }}>
          開発パスワードを入力してください
        </div>
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            value={input}
            onChange={e => { setInput(e.target.value); setError(false) }}
            placeholder="パスワード"
            autoFocus
            style={{
              width: '100%', padding: '10px 14px', fontSize: 14,
              background: '#090f1e', border: `1px solid ${error ? '#ef4444' : '#1e3a5f'}`,
              borderRadius: 8, color: '#e2e8f0', outline: 'none', boxSizing: 'border-box',
              marginBottom: error ? 6 : 12,
            }}
          />
          {error && (
            <div style={{ fontSize: 12, color: '#f87171', marginBottom: 10 }}>パスワードが違います</div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onClose} style={{
              flex: 1, padding: '10px 0', background: '#1e293b', color: '#94a3b8',
              border: '1px solid #334155', borderRadius: 8, fontSize: 13, cursor: 'pointer',
            }}>
              キャンセル
            </button>
            <button type="submit" style={{
              flex: 1, padding: '10px 0', background: 'linear-gradient(135deg,#1e40af,#3b82f6)',
              color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}>
              ログイン
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

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

function SystemButtons() {
  const navigate = useNavigate()
  const [showDotModal, setShowDotModal] = useState(false)

  const handleDotClick = () => {
    if (sessionStorage.getItem(DOT_KEY) === '1') {
      navigate('/dot')
    } else {
      setShowDotModal(true)
    }
  }

  const handleDotSuccess = () => {
    setShowDotModal(false)
    navigate('/dot')
  }

  return (
    <>
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={handleDotClick}
          style={{
            padding: '5px 12px', borderRadius: 6, border: '1px solid #334155',
            background: 'rgba(245,158,11,0.1)', color: '#f59e0b',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
          }}
        >
          DOTシステム（開発中）
        </button>
        <button
          onClick={() => navigate('/shishido')}
          style={{
            padding: '5px 12px', borderRadius: 6, border: '1px solid #334155',
            background: 'rgba(167,139,250,0.1)', color: '#a78bfa',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
          }}
        >
          宍戸予想 v58.7
        </button>
      </div>
      {showDotModal && (
        <DotPasswordModal onClose={() => setShowDotModal(false)} onSuccess={handleDotSuccess} />
      )}
    </>
  )
}

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
        <nav className="header-nav" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
          <div style={{ width: 1, height: 24, background: '#334155', margin: '0 4px' }} />
          <SystemButtons />
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
          <Route path="/dot" element={<DotSystem />} />
          <Route path="/shishido" element={<ShishidoPredict />} />
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
