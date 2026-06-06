import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import RaceList from './pages/RaceList'
import RaceDetail from './pages/RaceDetail'
import Analytics from './pages/Analytics'
import Scraping from './pages/Scraping'
import Import from './pages/Import'
import Venues from './pages/Venues'

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
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </BrowserRouter>
  )
}
