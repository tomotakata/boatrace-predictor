import { useState, useEffect } from 'react'
import {
  getAccuracy,
  getAccuracyByVenue,
  getRecentPredictions,
  triggerEvaluate,
  triggerScrapeHistory,
  type AccuracyData,
  type VenueStats,
  type RecentPrediction,
} from '../lib/api'

// ── helpers ──────────────────────────────────────────────────────────────────
const today = () => new Date().toISOString().slice(0, 10)
const daysAgo = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const gradeColor: Record<string, string> = {
  '勝負':  'text-red-400',
  '通常':  'text-yellow-300',
  '見送り':'text-slate-400',
  '未評価':'text-slate-500',
}
const gradeTag: Record<string, string> = {
  '勝負':  'bg-red-900/60 text-red-300 border border-red-700',
  '通常':  'bg-yellow-900/60 text-yellow-200 border border-yellow-700',
  '見送り':'bg-slate-700/60 text-slate-300 border border-slate-600',
  '未評価':'bg-slate-800/40 text-slate-500 border border-slate-700',
}

// ── component ────────────────────────────────────────────────────────────────
export default function Analytics() {
  const [tab, setTab] = useState<'overview' | 'venue' | 'grade' | 'history'>('overview')
  const [accuracy, setAccuracy] = useState<AccuracyData | null>(null)
  const [venues, setVenues] = useState<VenueStats[]>([])
  const [recent, setRecent] = useState<RecentPrediction[]>([])
  const [loading, setLoading] = useState(true)

  // date range state
  const [fromDate, setFromDate] = useState(daysAgo(30))
  const [toDate, setToDate]   = useState(today())

  // actions
  const [histFrom, setHistFrom] = useState(daysAgo(7))
  const [histTo, setHistTo]     = useState(daysAgo(1))
  const [histLoading, setHistLoading]   = useState(false)
  const [evalLoading, setEvalLoading]   = useState(false)
  const [actionMsg, setActionMsg]       = useState('')

  // ── fetch ─────────────────────────────────────────────────────────────────
  const fetchAll = async () => {
    setLoading(true)
    try {
      const [accRes, venueRes, recentRes] = await Promise.all([
        getAccuracy({ from_date: fromDate, to_date: toDate }),
        getAccuracyByVenue({ from_date: fromDate, to_date: toDate }),
        getRecentPredictions(50),
      ])
      setAccuracy(accRes.data)
      setVenues(venueRes.data)
      setRecent(recentRes.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [fromDate, toDate])

  // ── handlers ──────────────────────────────────────────────────────────────
  const handleScrapeHistory = async () => {
    setHistLoading(true)
    setActionMsg('')
    try {
      const res = await triggerScrapeHistory(histFrom, histTo)
      setActionMsg(`着順取得: ${res.data.summary || 'OK'}`)
    } catch (e: any) {
      setActionMsg(`エラー: ${e.message}`)
    } finally {
      setHistLoading(false)
    }
  }

  const handleEvaluate = async () => {
    setEvalLoading(true)
    setActionMsg('')
    try {
      const res = await triggerEvaluate(histFrom, histTo)
      const d = res.data as any
      setActionMsg(`突合完了: 更新${d.updated}件 / スキップ${d.skipped}件`)
      await fetchAll()
    } catch (e: any) {
      setActionMsg(`エラー: ${e.message}`)
    } finally {
      setEvalLoading(false)
    }
  }

  // ── render ────────────────────────────────────────────────────────────────
  const tabCls = (t: string) =>
    `px-4 py-2 text-sm font-medium rounded-t transition-colors ${
      tab === t
        ? 'bg-slate-800 text-white border-b-2 border-blue-500'
        : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
    }`

  return (
    <div className="min-h-screen bg-slate-900 text-white p-4 md:p-6">
      <h1 className="text-2xl font-bold mb-1">正答率研究ダッシュボード</h1>
      <p className="text-slate-400 text-sm mb-5">過去レース結果と予想を突合し、精度を分析します。</p>

      {/* date range filter */}
      <div className="flex flex-wrap items-center gap-3 mb-5 bg-slate-800/50 rounded-lg p-3">
        <span className="text-slate-400 text-sm">集計期間</span>
        <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
          className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm" />
        <span className="text-slate-500">〜</span>
        <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
          className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm" />
        <button onClick={fetchAll}
          className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium transition-colors">
          更新
        </button>
      </div>

      {/* stats cards */}
      {loading ? (
        <div className="flex items-center justify-center h-32 text-slate-400">読み込み中...</div>
      ) : accuracy ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard label="予想総数" value={String(accuracy.total_predictions)} sub="件" />
          <StatCard label="突合済み" value={String(accuracy.evaluated ?? 0)} sub="件" />
          <StatCard label="3連単的中率" value={`${accuracy.trifecta_rate}%`}
            sub={`${accuracy.evaluated || 0}件中`} highlight />
          <StatCard label="2連単的中率" value={`${accuracy.exacta_rate}%`}
            sub={`${accuracy.evaluated || 0}件中`} highlight={accuracy.exacta_rate > 0} />
        </div>
      ) : null}

      {/* tabs */}
      <div className="flex gap-1 border-b border-slate-700 mb-5">
        <button className={tabCls('overview')} onClick={() => setTab('overview')}>概要</button>
        <button className={tabCls('venue')}    onClick={() => setTab('venue')}>会場別</button>
        <button className={tabCls('grade')}    onClick={() => setTab('grade')}>判定別</button>
        <button className={tabCls('history')}  onClick={() => setTab('history')}>履歴取得</button>
      </div>

      {/* tab contents */}
      {tab === 'overview' && (
        <div className="space-y-6">
          {/* recent predictions */}
          <div>
            <h2 className="text-lg font-semibold mb-3">直近の予想履歴</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 border-b border-slate-700">
                    <th className="text-left py-2 px-3">日付</th>
                    <th className="text-left py-2 px-3">レース</th>
                    <th className="text-left py-2 px-3">判定</th>
                    <th className="text-left py-2 px-3">予想3連単</th>
                    <th className="text-left py-2 px-3">実結果</th>
                    <th className="text-center py-2 px-3">3連</th>
                    <th className="text-center py-2 px-3">2連</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.length === 0 ? (
                    <tr><td colSpan={7} className="py-8 text-center text-slate-500">
                      予想データなし（システム予想を実行するとここに表示されます）
                    </td></tr>
                  ) : (
                    recent.map(p => (
                      <tr key={p.id} className="border-b border-slate-800 hover:bg-slate-800/30">
                        <td className="py-2 px-3 text-slate-300">{p.date}</td>
                        <td className="py-2 px-3">
                          <a href={`/race/${p.race_no}`} className="text-blue-400 hover:underline">
                            {p.venue} {p.race_no}R
                          </a>
                        </td>
                        <td className="py-2 px-3">
                          {p.payout_grade ? (
                            <span className={`px-2 py-0.5 rounded text-xs ${gradeTag[p.payout_grade] || gradeTag['未評価']}`}>
                              {p.payout_grade}
                            </span>
                          ) : <span className="text-slate-600">—</span>}
                        </td>
                        <td className="py-2 px-3 text-slate-300 font-mono text-xs">{p.trifecta || '—'}</td>
                        <td className="py-2 px-3 font-mono text-xs">
                          {p.actual_trifecta
                            ? <span className="text-green-400">{p.actual_trifecta}</span>
                            : <span className="text-slate-600">未取得</span>}
                        </td>
                        <td className="py-2 px-3 text-center">
                          <ResultBadge v={p.is_correct} />
                        </td>
                        <td className="py-2 px-3 text-center">
                          <ResultBadge v={p.is_correct_exacta} />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {tab === 'venue' && (
        <div>
          <h2 className="text-lg font-semibold mb-3">会場別 3連単的中率</h2>
          {venues.length === 0 ? (
            <p className="text-slate-500">データなし</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 border-b border-slate-700">
                    <th className="text-left py-2 px-3">会場</th>
                    <th className="text-right py-2 px-3">予想数</th>
                    <th className="text-right py-2 px-3">突合数</th>
                    <th className="text-right py-2 px-3">3連単</th>
                    <th className="text-right py-2 px-3">2連単</th>
                    <th className="py-2 px-3">バー</th>
                  </tr>
                </thead>
                <tbody>
                  {venues.map(v => (
                    <tr key={v.venue} className="border-b border-slate-800 hover:bg-slate-800/30">
                      <td className="py-2 px-3 font-medium">{v.venue}</td>
                      <td className="py-2 px-3 text-right text-slate-400">{v.total}</td>
                      <td className="py-2 px-3 text-right text-slate-400">{v.evaluated}</td>
                      <td className="py-2 px-3 text-right font-mono">
                        <RateText rate={v.trifecta_rate} />
                      </td>
                      <td className="py-2 px-3 text-right font-mono">
                        <RateText rate={v.exacta_rate} />
                      </td>
                      <td className="py-2 px-3 min-w-[120px]">
                        <div className="w-full bg-slate-700 rounded-full h-2">
                          <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${Math.min(v.trifecta_rate, 100)}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'grade' && (
        <div>
          <h2 className="text-lg font-semibold mb-3">判定グレード別 的中率</h2>
          <p className="text-slate-400 text-sm mb-4">
            「勝負」「通常」「見送り」ごとに的中率を比較し、戻り額ゲートの有効性を検証します。
          </p>
          {!accuracy || accuracy.by_grade.length === 0 ? (
            <p className="text-slate-500">データなし（まず予想を突合してください）</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-3">
              {accuracy.by_grade.map(g => (
                <div key={g.grade} className={`rounded-lg p-4 border ${gradeTag[g.grade] || gradeTag['未評価']}`}>
                  <div className={`text-xl font-bold mb-1 ${gradeColor[g.grade] || 'text-slate-400'}`}>
                    {g.grade}
                  </div>
                  <div className="text-3xl font-bold">{g.trifecta_rate}%</div>
                  <div className="text-sm opacity-70 mt-1">3連単的中率</div>
                  <div className="text-sm mt-2">2連単: {g.exacta_rate}%</div>
                  <div className="text-xs opacity-60 mt-1">対象 {g.total}件</div>
                </div>
              ))}
            </div>
          )}

          {/* breakdown by source */}
          {accuracy && accuracy.by_source.length > 0 && (
            <div className="mt-6">
              <h3 className="text-base font-semibold mb-3 text-slate-300">ソース別</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-700">
                      <th className="text-left py-2 px-3">ソース</th>
                      <th className="text-right py-2 px-3">件数</th>
                      <th className="text-right py-2 px-3">3連単</th>
                      <th className="text-right py-2 px-3">2連単</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accuracy.by_source.map(s => (
                      <tr key={s.source} className="border-b border-slate-800">
                        <td className="py-2 px-3">{s.source}</td>
                        <td className="py-2 px-3 text-right text-slate-400">{s.total}</td>
                        <td className="py-2 px-3 text-right"><RateText rate={s.trifecta_rate} /></td>
                        <td className="py-2 px-3 text-right"><RateText rate={s.exacta_rate} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-6">
          <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
            <h2 className="text-lg font-semibold mb-1">過去着順の一括取得</h2>
            <p className="text-slate-400 text-sm mb-4">
              指定期間の確定着順(1〜3着)を boaters-boatrace.com からスクレイプして保存します。
            </p>
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <input type="date" value={histFrom} onChange={e => setHistFrom(e.target.value)}
                className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm" />
              <span className="text-slate-500">〜</span>
              <input type="date" value={histTo} onChange={e => setHistTo(e.target.value)}
                className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm" />
            </div>
            <div className="flex flex-wrap gap-3">
              <button onClick={handleScrapeHistory} disabled={histLoading}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-5 py-2 rounded-lg text-sm font-medium transition-colors">
                {histLoading ? '取得中...' : '着順データ取得'}
              </button>
              <button onClick={handleEvaluate} disabled={evalLoading}
                className="bg-green-700 hover:bg-green-600 disabled:opacity-50 px-5 py-2 rounded-lg text-sm font-medium transition-colors">
                {evalLoading ? '突合中...' : '予想を突合して的中判定'}
              </button>
            </div>
            {actionMsg && (
              <div className="mt-3 text-sm text-green-400 bg-green-900/30 border border-green-800 rounded p-3">
                {actionMsg}
              </div>
            )}
          </div>

          <div className="bg-slate-800/30 rounded-lg p-4 border border-slate-700 text-sm text-slate-300">
            <h3 className="font-semibold mb-2">手順ガイド</h3>
            <ol className="list-decimal list-inside space-y-1 text-slate-400">
              <li>期間を指定して「着順データ取得」を実行（最大30日）</li>
              <li>「予想を突合して的中判定」をクリックすると予想と実結果を照合</li>
              <li>「概要」タブで3連単/2連単的中率を確認</li>
              <li>「判定別」タブで勝負/通常/見送りごとの効果を検証</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  )
}

// ── sub components ────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, highlight }: {
  label: string; value: string; sub?: string; highlight?: boolean
}) {
  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
      <div className="text-slate-400 text-xs mb-1">{label}</div>
      <div className={`text-3xl font-bold ${highlight ? 'text-blue-400' : 'text-white'}`}>{value}</div>
      {sub && <div className="text-slate-500 text-xs mt-0.5">{sub}</div>}
    </div>
  )
}

function ResultBadge({ v }: { v: boolean | null | undefined }) {
  if (v === true)  return <span className="inline-block w-6 h-6 rounded-full bg-green-600/80 text-white text-xs flex items-center justify-center">✓</span>
  if (v === false) return <span className="inline-block w-6 h-6 rounded-full bg-red-800/60 text-slate-300 text-xs flex items-center justify-center">✗</span>
  return <span className="text-slate-600 text-xs">—</span>
}

function RateText({ rate }: { rate: number }) {
  const color = rate >= 20 ? 'text-green-400' : rate >= 10 ? 'text-yellow-300' : 'text-slate-300'
  return <span className={`${color} font-mono`}>{rate}%</span>
}
