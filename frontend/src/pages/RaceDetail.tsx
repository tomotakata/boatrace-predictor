import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getRace, predictRace, getVenueConfig, getRaceResult, savePredictionMemo, scrapeRaceResult, type Race, type Boat, type SystemPredictionDetail, type VenueConfig, type RaceResult } from '../lib/api'

// 進入順ラベルの色
const LANE_BG: Record<number, string> = {
  1: '#1a1a3e',   // 白枠
  2: '#1a1a1a',   // 黒枠
  3: '#7b241c',   // 赤枠
  4: '#1a5276',   // 青枠
  5: '#7d6608',   // 黄枠
  6: '#1e8449',   // 緑枠
}
const LANE_TEXT: Record<number, string> = {
  1: '#e2e8f0', 2: '#e2e8f0', 3: '#fff', 4: '#fff', 5: '#fff', 6: '#fff'
}

function fmt(v?: number | null, d = 2) {
  if (v == null) return '—'
  return v.toFixed(d)
}
function fmtPct(v?: number | null) {
  if (v == null) return '—'
  return v.toFixed(2) + '%'
}

function parsePercentValue(v?: string) {
  if (!v || v === '—' || v === '-') return null
  const n = parseFloat(v.replace('%', ''))
  return Number.isFinite(n) ? n : null
}

function highlightMaxPercent(values: (string | undefined)[]) {
  const nums = values.map(parsePercentValue)
  const max = nums.reduce<number | null>((acc, value) => {
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  return (v: string | undefined) => {
    const n = parsePercentValue(v)
    if (n == null) return '#94a3b8'
    return max != null && n === max ? '#f87171' : '#e2e8f0'
  }
}

// ───── セクションヘッダー ─────
function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div style={{
      background: 'linear-gradient(90deg, #0f2d5e 0%, #0a1f3f 100%)',
      padding: '6px 14px', marginBottom: 2, borderRadius: '6px 6px 0 0',
      display: 'flex', alignItems: 'center', gap: 8
    }}>
      <span style={{ color: '#60a5fa', fontWeight: 700, fontSize: 14 }}>{title}</span>
      {sub && <span style={{ color: '#64748b', fontSize: 11 }}>{sub}</span>}
    </div>
  )
}

// ───── コース列ヘッダー行 ─────
function LaneHeaderRow({ lanes }: { lanes: number[] }) {
  return (
    <tr>
      <td style={{ width: 90, padding: '4px 8px', color: '#64748b', fontSize: 11, background: '#0a1520' }} />
      {lanes.map(l => (
        <td key={l} style={{
          background: LANE_BG[l], color: LANE_TEXT[l],
          textAlign: 'center', fontWeight: 700, fontSize: 13,
          padding: '5px 0', width: 68, border: '1px solid #1e3a5f'
        }}>{l}</td>
      ))}
    </tr>
  )
}

// ───── データ行 ─────
function DataRow({ label, values, colorFn }: {
  label: string
  values: (string | undefined)[]
  colorFn?: (v: string | undefined, idx: number) => string
}) {
  return (
    <tr>
      <td style={{ padding: '4px 8px', color: '#94a3b8', fontSize: 12, background: '#0a1520', borderRight: '1px solid #1e3a5f', whiteSpace: 'nowrap' }}>{label}</td>
      {values.map((v, i) => (
        <td key={i} style={{
          textAlign: 'center', padding: '4px 2px', fontSize: 13, fontWeight: v && v !== '—' ? 600 : 400,
          color: colorFn ? colorFn(v, i) : '#e2e8f0',
          border: '1px solid #0a1520'
        }}>{v ?? '—'}</td>
      ))}
    </tr>
  )
}

function parseNumericRate(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const normalized = value.replace('%', '').trim()
    if (!normalized) return null
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function normalizeBetPattern(value?: string | null) {
  if (!value || typeof value !== 'string') return null
  const normalized = value.replace(/[→ー－]/g, '-').replace(/\s+/g, '')
  return normalized || null
}

function formatPayout(value?: number | null) {
  if (value == null) return null
  return `¥${Math.round(value).toLocaleString()}`
}

function ensureBetList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

// ───── セクションテーブル ─────
function SectionTable({ title, sub, lanes, rows }: {
  title: string; sub?: string; lanes: number[]
  rows: { label: string; values: (string | undefined)[]; colorFn?: (v: string | undefined, idx: number) => string }[]
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <SectionHeader title={title} sub={sub} />
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#0d1b2e', tableLayout: 'fixed' }}>
          <tbody>
            <LaneHeaderRow lanes={lanes} />
            {rows.map((r, i) => <DataRow key={i} label={r.label} values={r.values} colorFn={r.colorFn} />)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ───── ①基本 ─────
function Section1Basic({ boats, venueConfig, venueName }: { boats: Boat[]; venueConfig?: VenueConfig | null; venueName?: string }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const homeBranch = venueConfig?.home_branch?.trim()
  const venueLabel = venueConfig?.venue_name?.trim() || venueName?.trim() || ''
  const isLocalBoat = (boat?: Boat) => {
    if (!boat) return false
    if (boat.is_local) return true
    const branch = boat.branch?.trim()
    return !!(homeBranch && branch && branch === homeBranch)
  }

  const rows = [
    {
      label: '進入',
      values: lanes.map(l => {
        const course = get(l)?.entry_course
        return course != null ? String(course) : '—'
      }),
      colorFn: () => '#e2e8f0'
    },
    {
      label: '枠番',
      values: lanes.map(l => String(l)),
      colorFn: () => '#e2e8f0'
    },
    {
      label: '名前',
      values: lanes.map(l => get(l)?.name || '—'),
      colorFn: () => '#e2e8f0'
    },
    {
      label: '級',
      values: lanes.map(l => get(l)?.rank || '—'),
      colorFn: (v: string | undefined) => v === 'A1' ? '#fcd34d' : v === 'A2' ? '#f59e0b' : '#94a3b8'
    },
    {
      label: '年',
      values: lanes.map(l => get(l)?.age ? String(get(l)!.age) : '—'),
    },
    {
      label: '体重',
      values: lanes.map(l => get(l)?.weight ? `${get(l)!.weight}kg` : '—'),
    },
    {
      label: 'F',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.f_count ? `F${b.f_count}` : '-'
      }),
      colorFn: (v: string | undefined) => (v && v !== '-' && v !== '—') ? '#f87171' : '#94a3b8'
    },
    {
      label: '地元',
      values: lanes.map(l => {
        const boat = get(l)
        return isLocalBoat(boat) && venueLabel ? venueLabel : ''
      }),
      colorFn: (v: string | undefined) => v ? '#fcd34d' : '#94a3b8'
    },
  ]

  return (
    <SectionTable title="①基本" lanes={lanes} rows={rows} />
  )
}

// ───── ②モーター ─────
function Section2Motor({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const rankOrder: Record<string, number> = { A: 4, B: 3, C: 2, D: 1 }
  const dashValues = boats.map(b => b.motor_dashfoot).filter((v): v is number => v != null)
  const extValues = boats.map(b => b.motor_extfoot).filter((v): v is number => v != null)
  const evalValues = boats
    .map(b => b.motor_eval?.trim().toUpperCase())
    .filter((v): v is string => !!v && v in rankOrder)
  const explicitRankValues = boats.map(b => b.motor_rank).filter((v): v is number => v != null)
  const fallbackRankMap = (() => {
    if (explicitRankValues.length > 0) return null
    const sorted = boats
      .filter(b => b.motor_place2_rate != null)
      .sort((a, b) => (b.motor_place2_rate ?? 0) - (a.motor_place2_rate ?? 0))
    if (sorted.length === 0) return null
    const map = new Map<number, number>()
    let currentRank = 1
    let previousRate: number | null = null
    sorted.forEach((boat, index) => {
      const rate = boat.motor_place2_rate ?? null
      if (rate == null) return
      if (previousRate != null && rate !== previousRate) currentRank = index + 1
      map.set(boat.lane, currentRank)
      previousRate = rate
    })
    return map
  })()
  const bestDash = dashValues.length > 0 ? Math.max(...dashValues) : null
  const bestExt = extValues.length > 0 ? Math.max(...extValues) : null
  const bestEval = evalValues.length > 0
    ? Math.max(...evalValues.map(v => rankOrder[v]))
    : null
  const rankCandidates = lanes
    .map(lane => {
      const boat = get(lane)
      return boat?.motor_rank ?? fallbackRankMap?.get(lane) ?? null
    })
    .filter((v): v is number => v != null)
  const bestRank = rankCandidates.length > 0 ? Math.min(...rankCandidates) : null

  const rows = [
    {
      label: '出足',
      values: lanes.map(l => fmt(get(l)?.motor_dashfoot, 1)),
      colorFn: (_v: string | undefined, i: number) => {
        const val = get(lanes[i])?.motor_dashfoot
        if (val == null) return '#94a3b8'
        return bestDash != null && val === bestDash ? '#f87171' : '#e2e8f0'
      }
    },
    {
      label: '伸び足',
      values: lanes.map(l => fmt(get(l)?.motor_extfoot, 1)),
      colorFn: (_v: string | undefined, i: number) => {
        const val = get(lanes[i])?.motor_extfoot
        if (val == null) return '#94a3b8'
        return bestExt != null && val === bestExt ? '#f87171' : '#e2e8f0'
      }
    },
    {
      label: 'ランク',
      values: lanes.map(l => {
        const value = get(l)?.motor_eval?.trim().toUpperCase()
        return value || '—'
      }),
      colorFn: (v: string | undefined) => {
        if (!v || v === '—') return '#94a3b8'
        const score = rankOrder[v]
        return bestEval != null && score === bestEval ? '#22c55e' : '#e2e8f0'
      }
    },
    {
      label: '順位',
      values: lanes.map(l => {
        const boat = get(l)
        const rank = boat?.motor_rank ?? fallbackRankMap?.get(l) ?? null
        return rank != null ? String(rank) : '—'
      }),
      colorFn: (v: string | undefined) => {
        if (!v || v === '—') return '#94a3b8'
        const rank = Number(v)
        return bestRank != null && rank === bestRank ? '#f87171' : '#e2e8f0'
      }
    },
  ]

  return <SectionTable title="②モーター" lanes={lanes} rows={rows} />
}

// ───── ③スタート ─────
function Section3Start({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  // 最も良いSTを黄色、遅いSTを赤
  const stColorFn = (v: string | undefined) => {
    const n = parseFloat(v ?? '99')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n <= 0.15 ? '#fcd34d' : n >= 0.19 ? '#f87171' : '#e2e8f0'
  }

  const rows = [
    {
      label: '平均ST',
      values: lanes.map(l => fmt(get(l)?.avg_st, 2)),
      colorFn: stColorFn
    },
    {
      label: '今節ST',
      values: lanes.map(l => fmt(get(l)?.today_st, 2)),
      colorFn: stColorFn
    },
    {
      label: '今節ST(公式)',
      values: lanes.map(l => fmt(get(l)?.season_st, 2)),
      colorFn: stColorFn
    },
    {
      label: '今節順',
      values: lanes.map(l => get(l)?.today_st_rank ? String(get(l)!.today_st_rank) : '—'),
      colorFn: (v: string | undefined) => v === '1' ? '#fcd34d' : v === '2' ? '#f59e0b' : '#e2e8f0'
    },
    {
      label: 'コースST(1年)',
      values: lanes.map(l => fmt(get(l)?.course1y_st, 2)),
      colorFn: stColorFn
    },
    {
      label: 'ST順(1年)',
      values: lanes.map(l => { const r = get(l)?.course1y_st_rank; return r != null ? String(r) : '—' }),
      colorFn: (v: string | undefined) => v === '1' ? '#fcd34d' : v === '2' ? '#f59e0b' : '#e2e8f0'
    },
    {
      label: '基準ST',
      values: lanes.map(l => fmt(get(l)?.standard_st, 3)),
      colorFn: stColorFn
    },
    {
      label: '優勢順位',
      values: lanes.map(l => get(l)?.st_advantage_rank ? String(get(l)!.st_advantage_rank) : '—'),
      colorFn: (v: string | undefined) => v === '1' ? '#fcd34d' : v === '2' ? '#f59e0b' : '#e2e8f0'
    },
  ]

  return <SectionTable title="③スタート" lanes={lanes} rows={rows} />
}

// ───── ⑤a コース別（直近1年） ─────
function Section5aCourse({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  // 各艇の「自コース」での成績を表示
  const winRates = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    const lane = b.lane
    const r = (b as any)[`c${lane}_win_rate`]
    return fmtPct(r)
  })
  const p2Rates = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    const lane = b.lane
    const r = (b as any)[`c${lane}_place2_rate`]
    return fmtPct(r)
  })
  const p3Rates = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    const lane = b.lane
    const r = (b as any)[`c${lane}_tricast_rate`]
    return fmtPct(r)
  })
  const races = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    const lane = b.lane
    const r = (b as any)[`c${lane}_races`]
    return r ? String(r) : '—'
  })

  const rows = [
    { label: '出走数(自C)', values: races, colorFn: () => '#94a3b8' as string },
    { label: '勝率(自C)', values: winRates, colorFn: highlightMaxPercent(winRates) },
    { label: '2連率(自C)', values: p2Rates, colorFn: highlightMaxPercent(p2Rates) },
    { label: '3連率(自C)', values: p3Rates, colorFn: highlightMaxPercent(p3Rates) },
    {
      label: '全国勝率',
      values: lanes.map(l => fmtPct(get(l)?.national_win_rate)),
      colorFn: highlightMaxPercent(lanes.map(l => fmtPct(get(l)?.national_win_rate)))
    },
    {
      label: '全国2連率',
      values: lanes.map(l => fmtPct(get(l)?.national_place2_rate)),
      colorFn: highlightMaxPercent(lanes.map(l => fmtPct(get(l)?.national_place2_rate)))
    },
    {
      label: '当地勝率',
      values: lanes.map(l => fmtPct(get(l)?.local_win_rate)),
      colorFn: highlightMaxPercent(lanes.map(l => fmtPct(get(l)?.local_win_rate)))
    },
    {
      label: '当地2連率',
      values: lanes.map(l => fmtPct(get(l)?.local_place2_rate)),
      colorFn: highlightMaxPercent(lanes.map(l => fmtPct(get(l)?.local_place2_rate)))
    },
  ]

  return <SectionTable title="⑤a コース別（直近1年）" lanes={lanes} rows={rows} />
}

// ───── ⑤b コース別決まり手 ─────
function Section5bKimete({ boats, venueConfig, venueName }: { boats: Boat[]; venueConfig?: VenueConfig | null; venueName?: string }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const venueLabel = venueConfig?.venue_name?.trim() || venueName?.trim() || ''
  const c2RateLabel = venueConfig?.c2_rate != null ? `${venueConfig.c2_rate.toFixed(1)}%` : '—'

  // 各艇の「自コース」での決まり手データ
  const getKimete = (lane: number, key: string) => {
    const b = get(lane)
    if (!b) return null
    const c = b.lane
    return (b as any)[`c${c}_${key}`] as number | undefined
  }

  // 逃げ/差し/まくり/まくり差し の合計で割合を計算
  const pctOfTotal = (lane: number, key: string): string => {
    const b = get(lane)
    if (!b) return '—'
    const c = b.lane
    const nige = (b as any)[`c${c}_nige`] || 0
    const sashi = (b as any)[`c${c}_sashi`] || 0
    const makuri = (b as any)[`c${c}_makuri`] || 0
    const makurizashi = (b as any)[`c${c}_makurizashi`] || 0
    const total = nige + sashi + makuri + makurizashi
    if (!total) return '—'
    const val = (b as any)[`c${c}_${key}`] || 0
    return Math.round((val / total) * 100) + '%'
  }

  const countColor = (v: string | undefined) => {
    const n = parseInt(v ?? '0')
    return isNaN(n) || v === '—' ? '#94a3b8' : n > 0 ? '#e2e8f0' : '#64748b'
  }
  const pctColor = (v: string | undefined) => {
    const n = parseInt(v ?? '0')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n >= 60 ? '#fcd34d' : n >= 40 ? '#f59e0b' : n > 0 ? '#e2e8f0' : '#64748b'
  }

  const rows = [
    {
      label: '2連対率',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        const r = (b as any)[`c${b.lane}_place2_rate`]
        return r != null ? fmtPct(r) : '—'
      }),
      colorFn: pctColor
    },
    {
      label: '逃げ数',
      values: lanes.map(l => { const v = getKimete(l, 'nige'); return v != null ? String(v) : '—' }),
      colorFn: countColor
    },
    {
      label: '逃げ率',
      values: lanes.map(l => pctOfTotal(l, 'nige')),
      colorFn: pctColor
    },
    {
      label: '差し数',
      values: lanes.map(l => { const v = getKimete(l, 'sashi'); return v != null ? String(v) : '—' }),
      colorFn: countColor
    },
    {
      label: '差★率',
      values: lanes.map(l => pctOfTotal(l, 'sashi')),
      colorFn: pctColor
    },
    {
      label: 'まくり数',
      values: lanes.map(l => { const v = getKimete(l, 'makuri'); return v != null ? String(v) : '—' }),
      colorFn: countColor
    },
    {
      label: 'まくり率',
      values: lanes.map(l => pctOfTotal(l, 'makuri')),
      colorFn: pctColor
    },
    {
      label: 'まくり差し数',
      values: lanes.map(l => { const v = getKimete(l, 'makurizashi'); return v != null ? String(v) : '—' }),
      colorFn: countColor
    },
    {
      label: 'まくり差し率',
      values: lanes.map(l => pctOfTotal(l, 'makurizashi')),
      colorFn: pctColor
    },
  ]

  return <SectionTable title={`⑤b 決まり手(${venueLabel || '場名未設定'}:2C差し率${c2RateLabel}突出)`} lanes={lanes} rows={rows.map((row) => {
    if (row.label === '差し数') return { ...row, label: '差★数' }
    return row
  })} />
}

// ───── ⑤c 握り率 ─────
function Section5cNigiri({ boats, venueConfig, venueName }: { boats: Boat[]; venueConfig?: VenueConfig | null; venueName?: string }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const venueLabel = venueConfig?.venue_name?.trim() || venueName?.trim() || ''
  const c2Correction = venueConfig?.kad_c2 ?? 0.85
  const c3Correction = venueConfig?.kad_c3 ?? 0.85
  const c56Correction = venueConfig?.kad_c5 ?? 0.90
  const nigiriRates = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    if (l === 1) return '-'
    return b.nigiri_rate != null ? fmtPct(b.nigiri_rate) : '—'
  })
  const genRates = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    if (l === 1) return '-'
    return b.gen_rate != null ? fmtPct(b.gen_rate) : '—'
  })

  const rows = [
    {
      label: '握り率',
      values: nigiriRates,
      colorFn: highlightMaxPercent(nigiriRates)
    },
    {
      label: '発生率',
      values: genRates,
      colorFn: highlightMaxPercent(genRates)
    },
  ]

  return (
    <SectionTable
      title={`⑤c 握り率・発生率(${venueLabel || '場名未設定'}差し水面補正:2C×${c2Correction.toFixed(2)}/3C×${c3Correction.toFixed(2)}/5-6C×${c56Correction.toFixed(2)})`}
      lanes={lanes}
      rows={rows}
    />
  )
}

// ───── ⑤e 当地別（直近5年） ─────
function Section5eLocal({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  const pctColor = (v: string | undefined) => {
    const n = parseFloat(v ?? '0')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n >= 30 ? '#fcd34d' : n >= 15 ? '#f59e0b' : '#e2e8f0'
  }

  const rows = [
    {
      label: '出走数',
      values: lanes.map(l => get(l)?.local5y_races ? String(get(l)!.local5y_races) : '—'),
      colorFn: () => '#94a3b8' as string
    },
    {
      label: '勝率',
      values: lanes.map(l => fmtPct(get(l)?.local5y_win_rate)),
      colorFn: pctColor
    },
    {
      label: '2連率',
      values: lanes.map(l => fmtPct(get(l)?.local5y_place2_rate)),
      colorFn: pctColor
    },
    {
      label: '3連率',
      values: lanes.map(l => fmtPct(get(l)?.local5y_tricast_rate)),
      colorFn: pctColor
    },
    {
      label: '差/捲/捲差',
      values: lanes.map(l => {
        const b = get(l)
        if (!b) return '—'
        const s = b.local5y_sashi, mk = b.local5y_makuri, mz = b.local5y_makurizashi
        if (s == null && mk == null && mz == null) return '—'
        return `${s ?? 0}/${mk ?? 0}/${mz ?? 0}`
      }),
      colorFn: () => '#cbd5e1' as string
    },
  ]

  return <SectionTable title="⑤e 当地別" sub="(直近5年)" lanes={lanes} rows={rows} />
}

// ───── ⑤f 一般戦(G2,G3含む) 直近1年 ─────
function Section5fGeneral({ boats }: { boats: Boat[] }) {
  const lanes = [2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const boat1 = boats.find(b => b.lane === 1)
  const hasData = boats.some(b =>
    b.general1y_place2_rate != null ||
    b.general1y_races != null ||
    b.general1y_sashi != null ||
    b.general1y_makuri != null ||
    b.general1y_makurizashi != null
  )
  if (!hasData) return null

  const pickMainAttack = (boat?: Boat) => {
    if (!boat) return '—'
    const candidates = [
      { label: '差', value: boat.general1y_sashi ?? null },
      { label: '捲', value: boat.general1y_makuri ?? null },
      { label: '捲差', value: boat.general1y_makurizashi ?? null },
    ].filter((item) => item.value != null && item.value! > 0)
    if (candidates.length === 0) return '—'
    candidates.sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
    return candidates[0].label
  }

  const hitRates = lanes.map((lane) => {
    const boat = get(lane)
    const value = boat?.escape1y_place2_rate ?? boat?.general1y_place2_rate ?? null
    return value != null ? `${value.toFixed(1)}%` : '—'
  })
  const rideFactors = lanes.map((lane) => {
    const boat = get(lane)
    const place2 = boat?.national_place2_rate ?? boat?.local_place2_rate ?? boat?.general1y_place2_rate ?? null
    if (place2 == null) return '—'
    return (place2 / 50).toFixed(2)
  })
  const adjustedHit = lanes.map((_lane, index) => {
    const hit = parsePercentValue(hitRates[index])
    const factor = rideFactors[index] === '—' ? null : parseFloat(rideFactors[index]!)
    if (hit == null || factor == null || !Number.isFinite(factor)) return '—'
    return `↑${(hit * factor).toFixed(1)}%`
  })
  const adjustedNums = adjustedHit.map((value) => {
    if (!value || value === '—') return null
    const n = parseFloat(value.replace('↑', '').replace('%', ''))
    return Number.isFinite(n) ? n : null
  })
  const adjustedMax = adjustedNums.reduce<number | null>((acc, value) => {
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const confidenceRuns = boat1?.general1y_races ?? null
  const confidenceLabel = confidenceRuns != null
    ? `${confidenceRuns >= 15 ? '完全信頼' : confidenceRuns >= 8 ? '参考信頼' : '低信頼'}（1C走数:${confidenceRuns}/15）`
    : '—'

  const rows = [
    {
      label: '被弾率',
      values: hitRates,
      colorFn: highlightMaxPercent(hitRates)
    },
    {
      label: '主決手',
      values: lanes.map((lane) => pickMainAttack(get(lane))),
      colorFn: () => '#cbd5e1'
    },
    {
      label: '乗艇係数',
      values: rideFactors,
      colorFn: (_v: string | undefined, idx: number) => rideFactors[idx] === '—' ? '#94a3b8' : '#e2e8f0'
    },
    {
      label: '補正被弾',
      values: adjustedHit,
      colorFn: (v: string | undefined) => {
        if (!v || v === '—') return '#94a3b8'
        const n = parseFloat(v.replace('↑', '').replace('%', ''))
        if (!Number.isFinite(n)) return '#94a3b8'
        return adjustedMax != null && n === adjustedMax ? '#f87171' : '#fca5a5'
      }
    },
    {
      label: '危険度',
      values: adjustedNums.map((value) => value != null && value >= 35 ? '高' : value != null ? '低' : '—'),
      colorFn: (v: string | undefined) => v === '高' ? '#f87171' : v === '低' ? '#22c55e' : '#94a3b8'
    },
    {
      label: '他艇2連率',
      values: lanes.map((lane) => {
        const value = get(lane)?.general1y_place2_rate ?? get(lane)?.national_place2_rate ?? null
        return value != null ? `${value.toFixed(1)}%` : '—'
      }),
      colorFn: (_v: string | undefined, idx: number) => {
        const value = get(lanes[idx])?.general1y_place2_rate ?? get(lanes[idx])?.national_place2_rate ?? null
        if (value == null) return '#94a3b8'
        return value >= 40 ? '#fcd34d' : value >= 25 ? '#f59e0b' : '#e2e8f0'
      }
    },
  ]

  return (
    <div style={{ marginBottom: 16, borderRadius: 10, overflow: 'hidden', border: '1px solid #1e3a5f', background: '#0b1730' }}>
      <div style={{ background: 'linear-gradient(90deg, #10264d 0%, #0a1f3f 100%)', padding: '8px 14px', borderBottom: '1px solid #1e3a5f' }}>
        <span style={{ color: '#93c5fd', fontWeight: 700, fontSize: 14 }}>⑤f 1号艇被弾分析(他艇成績実データ統合版)</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#0b1730', tableLayout: 'fixed' }}>
          <tbody>
            <LaneHeaderRow lanes={lanes} />
            {rows.map((r, i) => <DataRow key={i} label={r.label} values={r.values} colorFn={r.colorFn} />)}
          </tbody>
        </table>
      </div>
      <div style={{ padding: '8px 14px 10px', borderTop: '1px solid #1e3a5f', color: '#cbd5e1', fontSize: 12 }}>
        <span style={{ color: '#93c5fd', fontWeight: 700, marginRight: 8 }}>信頼度</span>
        <span>{confidenceLabel}</span>
        {(boat1?.general1y_races == null || boat1?.escape1y_place2_rate == null) && (
          <span style={{ display: 'block', marginTop: 4, color: '#64748b' }}>
            TODO: APIで1号艇被弾専用のコース別実データが未提供のため、一部は既存general1y_/escape1y_から近似計算
          </span>
        )}
      </div>
    </div>
  )
}

// ───── ⑤g P2連動要約 ─────
function Section5gP2LinkSummary({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const summaries = lanes.map((winnerLane) => {
    const candidates = boats
      .filter((boat) => boat.lane !== winnerLane)
      .map((boat) => {
        const rawP2Link = parseNumericRate((boat as any)[`p2_link_${winnerLane}`])
        const fallbackPlace2 = parseNumericRate((boat as any)[`c${winnerLane}_place2_rate`])
        const rate = rawP2Link ?? fallbackPlace2
        const source = rawP2Link != null ? 'p2_link' : fallbackPlace2 != null ? 'fallback' : 'missing'
        return { lane: boat.lane, rate, source }
      })
      .filter((candidate) => candidate.rate != null)
      .sort((a, b) => {
        if ((b.rate ?? -1) !== (a.rate ?? -1)) return (b.rate ?? -1) - (a.rate ?? -1)
        return a.lane - b.lane
      })

    const top = candidates[0] ?? null
    const second = candidates[1] ?? null
    const confidence = top && second
      ? (top.source === 'p2_link' && second.source === 'p2_link'
          ? '完全'
          : top.source !== 'missing'
            ? '中'
            : '低')
      : top
        ? (top.source === 'p2_link' ? '中' : '低')
        : '低'

    return { winnerLane, top, second, confidence }
  })

  const hasAnyData = summaries.some((summary) => summary.top || summary.second)
  if (!hasAnyData) return null

  const topRates = summaries.map((summary) => summary.top?.rate ?? null)
  const maxTopRate = topRates.reduce<number | null>((acc, value) => {
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)

  const formatCandidate = (candidate: { lane: number; rate: number | null } | null) =>
    candidate && candidate.rate != null ? `${candidate.lane}(${candidate.rate.toFixed(0)})` : 'TODO'

  const confidenceColor = (value: string | undefined) => {
    if (value === '完全') return '#4ade80'
    if (value === '中') return '#facc15'
    if (value === '低') return '#f87171'
    return '#94a3b8'
  }

  return (
    <div style={{ marginBottom: 16, borderRadius: 10, overflow: 'hidden', border: '1px solid #1e3a5f', background: '#081427' }}>
      <div style={{ background: 'linear-gradient(90deg, #10264d 0%, #0a1f3f 100%)', padding: '8px 14px', borderBottom: '1px solid #1e3a5f' }}>
        <span style={{ color: '#93c5fd', fontWeight: 700, fontSize: 14 }}>⑤g P2連動要約(他艇成績→2着連動率)</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#081427', tableLayout: 'fixed' }}>
          <tbody>
            <tr>
              <td style={{ width: 90, padding: '6px 8px', color: '#93c5fd', fontSize: 11, fontWeight: 700, background: '#0a1520', borderRight: '1px solid #1e3a5f', whiteSpace: 'nowrap' }}>勝者→</td>
              {lanes.map((lane) => (
                <td key={lane} style={{
                  background: LANE_BG[lane], color: LANE_TEXT[lane],
                  textAlign: 'center', fontWeight: 700, fontSize: 13,
                  padding: '6px 0', width: 68, border: '1px solid #1e3a5f'
                }}>{lane}</td>
              ))}
            </tr>
            <DataRow
              label="2着筆頭"
              values={summaries.map((summary) => formatCandidate(summary.top))}
              colorFn={(_value, index) => {
                const rate = summaries[index].top?.rate ?? null
                if (rate == null) return '#94a3b8'
                return maxTopRate != null && rate === maxTopRate ? '#f87171' : '#e2e8f0'
              }}
            />
            <DataRow
              label="2着次点"
              values={summaries.map((summary) => formatCandidate(summary.second))}
              colorFn={(value) => value === 'TODO' ? '#64748b' : '#cbd5e1'}
            />
            <DataRow
              label="信頼度"
              values={summaries.map((summary) => summary.confidence)}
              colorFn={(value) => confidenceColor(value)}
            />
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Section6EI({ detail, venueName }: { detail: SystemPredictionDetail; venueName?: string }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const evalMap = new Map((detail.boat_evals || []).map((boat) => [boat.lane, boat]))
  const eiValues = lanes.map((lane) => evalMap.get(lane)?.ei)
  const maxEi = eiValues.reduce<number | null>((acc, value) => {
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const venueLabel = venueName?.trim() || '場名未設定'

  return (
    <div style={{ marginBottom: 16, borderRadius: 10, overflow: 'hidden', border: '1px solid #4338ca' }}>
      <div style={{
        background: 'linear-gradient(90deg, #312e81 0%, #581c87 100%)',
        padding: '8px 14px',
        borderBottom: '1px solid #4338ca'
      }}>
        <span style={{ color: '#c4b5fd', fontWeight: 700, fontSize: 14 }}>
          {`⑥期待指数(EI) 最終版-${venueLabel} — 個人実力評価`}
        </span>
      </div>
      <div style={{ overflowX: 'auto', background: '#0f172a' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <tbody>
            <LaneHeaderRow lanes={lanes} />
            <tr>
              <td style={{ padding: '10px 8px', color: '#cbd5e1', fontSize: 13, background: '#111827', borderRight: '1px solid #312e81', whiteSpace: 'nowrap' }}>EI</td>
              {lanes.map((lane, index) => {
                const value = eiValues[index]
                const isMax = value != null && maxEi != null && value === maxEi
                return (
                  <td key={lane} style={{
                    textAlign: 'center',
                    padding: '12px 4px',
                    fontSize: '2.25rem',
                    fontWeight: 700,
                    color: isMax ? '#f87171' : '#e9d5ff',
                    border: '1px solid #1f2937',
                    background: '#111827'
                  }}>
                    {value != null ? Math.round(value).toString() : '—'}
                  </td>
                )
              })}
            </tr>
            <tr>
              <td style={{ padding: '8px', color: '#cbd5e1', fontSize: 13, background: '#111827', borderRight: '1px solid #312e81', whiteSpace: 'nowrap' }}>EI順</td>
              {lanes.map((lane) => {
                const rank = evalMap.get(lane)?.ei_rank
                return (
                  <td key={lane} style={{
                    textAlign: 'center',
                    padding: '8px 4px',
                    fontSize: 16,
                    fontWeight: 700,
                    color: rank === 1 ? '#f87171' : '#e2e8f0',
                    border: '1px solid #1f2937',
                    background: '#111827'
                  }}>
                    {rank != null ? `${rank}` : '—'}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Section7TI({ detail, boats, venueName }: { detail: SystemPredictionDetail; boats: Boat[]; venueName?: string }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const evalMap = new Map((detail.boat_evals || []).map((boat) => [boat.lane, boat]))
  const boatMap = new Map(boats.map((boat) => [boat.lane, boat]))
  const venueLabel = venueName?.trim() || '場名未設定'
  const syntheticOdds = detail.synthetic_odds && detail.synthetic_odds > 0 ? detail.synthetic_odds : null
  const approxFirstRate = syntheticOdds ? Math.min(100, Math.max(0, 100 / syntheticOdds)) : null
  const tiValues = lanes.map((lane) => evalMap.get(lane)?.ti ?? evalMap.get(lane)?.p1 ?? null)
  const maxTi = tiValues.reduce<number | null>((acc, value) => {
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const maxCompletion = lanes.reduce<number | null>((acc, lane) => {
    const value = evalMap.get(lane)?.completion_power ?? null
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const maxResistance = lanes.reduce<number | null>((acc, lane) => {
    const value = boatMap.get(lane)?.general1y_place2_rate ?? boatMap.get(lane)?.national_place2_rate ?? null
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const maxSurvival = lanes.reduce<number | null>((acc, lane) => {
    const value = boatMap.get(lane)?.local5y_tricast_rate ?? boatMap.get(lane)?.general1y_tricast_rate ?? boatMap.get(lane)?.c3_tricast_rate ?? null
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const maxPlace = lanes.reduce<number | null>((acc, lane) => {
    const value = boatMap.get(lane)?.national_place2_rate ?? boatMap.get(lane)?.local_place2_rate ?? null
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const maxSecond = lanes.reduce<number | null>((acc, lane) => {
    const value = boatMap.get(lane)?.local_place2_rate ?? boatMap.get(lane)?.national_place2_rate ?? null
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const tiRanks = [...lanes]
    .map((lane) => ({ lane, value: evalMap.get(lane)?.ti ?? evalMap.get(lane)?.p1 ?? null }))
    .sort((a, b) => {
      if (a.value == null && b.value == null) return a.lane - b.lane
      if (a.value == null) return 1
      if (b.value == null) return -1
      if (b.value !== a.value) return b.value - a.value
      return a.lane - b.lane
    })
  const tiRankMap = new Map<number, number>()
  tiRanks.forEach((item, index) => {
    if (item.value != null) tiRankMap.set(item.lane, index + 1)
  })
  const bestTiRank = tiRankMap.size > 0 ? 1 : null
  const maxFirstRate = lanes.reduce<number | null>((acc, lane) => {
    const value = lane === 1
      ? approxFirstRate
      : ((evalMap.get(lane)?.ti ?? evalMap.get(lane)?.p1 ?? null) != null && approxFirstRate != null
          ? approxFirstRate * ((evalMap.get(lane)?.ti ?? evalMap.get(lane)?.p1 ?? 0) / Math.max(maxTi ?? 1, 1))
          : null)
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const nigeText = [
    detail.main_attack_course ? `${detail.main_attack_course}C${detail.attack_type || '攻め'}` : null,
    detail.surface_type ? `${detail.surface_type}補正` : null,
    detail.regime ? `${detail.regime}連動` : null,
    'TODO: 被弾統合文言'
  ].filter(Boolean).join('・')
  const highlightColor = '#f87171'
  const defaultColor = '#e2e8f0'
  const mutedColor = '#94a3b8'
  const formatRatio = (value?: number | null) => value != null ? value.toFixed(2) : '—'
  const formatPercent = (value?: number | null) => value != null ? `${value.toFixed(2)}%` : '—'
  const formatTi = (value?: number | null) => value != null ? value.toFixed(3) : '—'
  const isMax = (value: number | null | undefined, max: number | null) => value != null && max != null && value === max

  return (
    <div style={{ marginBottom: 16, borderRadius: 10, overflow: 'hidden', border: '1px solid #1d4ed8', background: '#081427' }}>
      <div style={{
        background: 'linear-gradient(90deg, #0f2d5e 0%, #081a38 100%)',
        padding: '8px 14px',
        borderBottom: '1px solid #1d4ed8'
      }}>
        <span style={{ color: '#bfdbfe', fontWeight: 700, fontSize: 14 }}>
          {`⑦展開指数(TI v14.6) — ${venueLabel}差し水面+被弾統合・実P2・逃げ展開度・着内確率`}
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', background: '#081427' }}>
          <tbody>
            <LaneHeaderRow lanes={lanes} />
            <DataRow
              label="旋回型"
              values={lanes.map((lane) => lane === 1 && detail.main_attack_course === 1 ? 'expand' : 'normal')}
              colorFn={(value) => value === 'expand' ? '#fcd34d' : defaultColor}
            />
            <DataRow
              label="万能度"
              values={lanes.map((lane) => formatRatio((evalMap.get(lane)?.completion_power ?? null) != null ? (evalMap.get(lane)!.completion_power! / 5) : null))}
              colorFn={(_value, index) => {
                const raw = evalMap.get(lanes[index])?.completion_power ?? null
                return isMax(raw, maxCompletion) ? highlightColor : raw != null ? defaultColor : mutedColor
              }}
            />
            <DataRow
              label="1着確率"
              values={lanes.map((lane) => {
                const ti = evalMap.get(lane)?.ti ?? evalMap.get(lane)?.p1 ?? null
                if (ti == null || approxFirstRate == null || maxTi == null || maxTi <= 0) return '—'
                return formatPercent(approxFirstRate * (ti / maxTi))
              })}
              colorFn={(value) => {
                const parsed = parsePercentValue(value)
                return parsed != null && maxFirstRate != null && parsed === maxFirstRate ? highlightColor : parsed != null ? defaultColor : mutedColor
              }}
            />
            <tr>
              <td style={{ padding: '4px 8px', color: mutedColor, fontSize: 12, background: '#0a1520', borderRight: '1px solid #1e3a5f', whiteSpace: 'nowrap' }}>逃げ成立</td>
              <td style={{ textAlign: 'center', padding: '4px 2px', fontSize: 13, fontWeight: 600, color: defaultColor, border: '1px solid #0a1520' }}>
                {detail.in_win_rate != null ? detail.in_win_rate.toFixed(2) : 'TODO'}
              </td>
              <td colSpan={5} style={{ padding: '4px 8px', fontSize: 12, color: '#cbd5e1', border: '1px solid #0a1520', background: '#0b1730' }}>
                {nigeText}
              </td>
            </tr>
            <DataRow
              label="抵抗率"
              values={lanes.map((lane) => formatPercent(boatMap.get(lane)?.general1y_place2_rate ?? boatMap.get(lane)?.national_place2_rate ?? null))}
              colorFn={(_value, index) => {
                const raw = boatMap.get(lanes[index])?.general1y_place2_rate ?? boatMap.get(lanes[index])?.national_place2_rate ?? null
                return isMax(raw, maxResistance) ? highlightColor : raw != null ? defaultColor : mutedColor
              }}
            />
            <DataRow
              label="残存確率"
              values={lanes.map((lane) => formatPercent(boatMap.get(lane)?.local5y_tricast_rate ?? boatMap.get(lane)?.general1y_tricast_rate ?? boatMap.get(lane)?.c3_tricast_rate ?? null))}
              colorFn={(_value, index) => {
                const raw = boatMap.get(lanes[index])?.local5y_tricast_rate ?? boatMap.get(lanes[index])?.general1y_tricast_rate ?? boatMap.get(lanes[index])?.c3_tricast_rate ?? null
                return isMax(raw, maxSurvival) ? highlightColor : raw != null ? defaultColor : mutedColor
              }}
            />
            <tr style={{ background: 'linear-gradient(90deg, rgba(180,83,9,0.35) 0%, rgba(251,191,36,0.18) 100%)' }}>
              <td style={{ padding: '6px 8px', color: '#fde68a', fontSize: 12, fontWeight: 700, background: 'rgba(120,53,15,0.45)', borderRight: '1px solid #92400e', whiteSpace: 'nowrap' }}>着内確率</td>
              {lanes.map((lane) => {
                const raw = boatMap.get(lane)?.national_place2_rate ?? boatMap.get(lane)?.local_place2_rate ?? null
                const highlighted = isMax(raw, maxPlace)
                return (
                  <td key={lane} style={{
                    textAlign: 'center',
                    padding: '6px 2px',
                    fontSize: 15,
                    fontWeight: 800,
                    color: highlighted ? highlightColor : '#fef3c7',
                    border: '1px solid rgba(146,64,14,0.45)'
                  }}>
                    {formatPercent(raw)}
                  </td>
                )
              })}
            </tr>
            <DataRow
              label="2着期待"
              values={lanes.map((lane) => formatRatio((boatMap.get(lane)?.local_place2_rate ?? boatMap.get(lane)?.national_place2_rate ?? null) != null ? ((boatMap.get(lane)?.local_place2_rate ?? boatMap.get(lane)?.national_place2_rate ?? 0) / 100) : null))}
              colorFn={(_value, index) => {
                const raw = boatMap.get(lanes[index])?.local_place2_rate ?? boatMap.get(lanes[index])?.national_place2_rate ?? null
                return isMax(raw, maxSecond) ? highlightColor : raw != null ? defaultColor : mutedColor
              }}
            />
            <tr style={{ background: 'linear-gradient(90deg, rgba(30,64,175,0.45) 0%, rgba(37,99,235,0.18) 100%)' }}>
              <td style={{ padding: '8px', color: '#bfdbfe', fontSize: 13, fontWeight: 700, background: 'rgba(15,23,42,0.8)', borderRight: '1px solid #1d4ed8', whiteSpace: 'nowrap' }}>TI</td>
              {lanes.map((lane, index) => {
                const value = tiValues[index]
                const highlighted = isMax(value, maxTi)
                return (
                  <td key={lane} style={{
                    textAlign: 'center',
                    padding: '10px 4px',
                    fontSize: '2.2rem',
                    fontWeight: 800,
                    color: highlighted ? highlightColor : '#dbeafe',
                    border: '1px solid rgba(29,78,216,0.35)'
                  }}>
                    {formatTi(value)}
                  </td>
                )
              })}
            </tr>
            <DataRow
              label="TI順"
              values={lanes.map((lane) => tiRankMap.get(lane) != null ? String(tiRankMap.get(lane)) : '—')}
              colorFn={(value) => {
                const rank = value && value !== '—' ? Number(value) : null
                return rank != null && bestTiRank != null && rank === bestTiRank ? highlightColor : rank != null ? defaultColor : mutedColor
              }}
            />
          </tbody>
        </table>
      </div>
      <div style={{ padding: '8px 14px 10px', borderTop: '1px solid #1e3a5f', color: '#64748b', fontSize: 11 }}>
        TODO: engine側の `output_to_prediction_dict` で TI専用の旋回型・実P2・抵抗率・残存確率・2着期待を明示出力できるようになったら近似値を置換
      </div>
    </div>
  )
}

function Section8OverallJudgement({ detail, boats, venueName }: { detail: SystemPredictionDetail; boats: Boat[]; venueName?: string }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const evalMap = new Map((detail.boat_evals || []).map((boat) => [boat.lane, boat]))
  const boatMap = new Map(boats.map((boat) => [boat.lane, boat]))
  const venueLabel = venueName?.trim() || '場名未設定'
  const fallbackCalFactor = detail.cal_factor != null && Number.isFinite(detail.cal_factor) ? detail.cal_factor : 1
  const placeProbabilities = lanes.map((lane) => {
    const boat = boatMap.get(lane)
    const candidates = [
      boat?.national_place2_rate,
      boat?.local_place2_rate,
      boat?.general1y_place2_rate,
      boat?.c2_rate,
    ]
    const raw = candidates.find((value) => value != null)
    if (raw == null) return null
    const normalized = raw > 1 ? raw / 100 : raw
    return Number.isFinite(normalized) ? Math.max(0, normalized) : null
  })
  const calFactors = lanes.map((lane) => {
    const boat = evalMap.get(lane)
    const raw = lane === 1
      ? fallbackCalFactor
      : ((boat?.gen_rate ?? 0) > 0 ? 1 + (boat?.gen_rate ?? 0) : 1)
    return Number.isFinite(raw) ? raw : 1
  })
  const compositeScores = lanes.map((lane, index) => {
    const boat = evalMap.get(lane)
    const ei = boat?.ei ?? null
    const ti = boat?.ti ?? boat?.p1 ?? null
    const place = placeProbabilities[index]
    const cal = calFactors[index]
    if (ei == null || ti == null || place == null) return null
    const score = ei * ti * place * cal
    return Number.isFinite(score) ? Math.round(score) : null
  })
  const maxCalFactor = calFactors.reduce<number | null>((acc, value) => acc == null ? value : Math.max(acc, value), null)
  const maxComposite = compositeScores.reduce<number | null>((acc, value) => {
    if (value == null) return acc
    return acc == null ? value : Math.max(acc, value)
  }, null)
  const ranked = [...lanes]
    .map((lane, index) => ({ lane, score: compositeScores[index] }))
    .sort((a, b) => {
      if (a.score == null && b.score == null) return a.lane - b.lane
      if (a.score == null) return 1
      if (b.score == null) return -1
      if (b.score !== a.score) return b.score - a.score
      return a.lane - b.lane
    })
  const rankMap = new Map<number, number>()
  ranked.forEach((item, index) => {
    if (item.score != null) rankMap.set(item.lane, index + 1)
  })
  const judgementByRank = (rank?: number) => {
    if (rank === 1) return '軸候補'
    if (rank === 2) return '頭候補'
    if (rank != null && rank <= 4) return '紐候補'
    if (rank != null) return '着外候補'
    return '—'
  }
  const judgementColor = (value: string | undefined) => {
    if (value === '軸候補') return '#f87171'
    if (value === '頭候補') return '#fbbf24'
    if (value === '紐候補') return '#60a5fa'
    if (value === '着外候補') return '#94a3b8'
    return '#64748b'
  }

  return (
    <div style={{ marginBottom: 16, borderRadius: 10, overflow: 'hidden', border: '1px solid #1e3a8a', background: '#081427' }}>
      <div style={{
        background: 'linear-gradient(90deg, #102a56 0%, #081a38 100%)',
        padding: '8px 14px',
        borderBottom: '1px solid #1e3a8a'
      }}>
        <span style={{ color: '#bfdbfe', fontWeight: 700, fontSize: 14 }}>
          {`⑧総合判定 (EI×TI×着内×${venueLabel}乖離補正・被弾統合)`}
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', background: '#081427' }}>
          <tbody>
            <LaneHeaderRow lanes={lanes} />
            <DataRow
              label="乖離補正"
              values={calFactors.map((value) => value.toFixed(2))}
              colorFn={(_value, index) => calFactors[index] === maxCalFactor ? '#f87171' : '#dbeafe'}
            />
            <DataRow
              label="合成"
              values={compositeScores.map((value) => value != null ? String(value) : '—')}
              colorFn={(value) => {
                const numeric = value && value !== '—' ? Number(value) : null
                return numeric != null && maxComposite != null && numeric === maxComposite ? '#f87171' : numeric != null ? '#e2e8f0' : '#64748b'
              }}
            />
            <DataRow
              label="判定"
              values={lanes.map((lane) => judgementByRank(rankMap.get(lane)))}
              colorFn={(value) => judgementColor(value)}
            />
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ───── 展示タイム ─────
function SectionExhibit({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  const times = lanes.map(l => get(l)?.exhibition_time)
  const sorted = [...times].filter(v => v != null).sort((a, b) => (a as number) - (b as number)) as number[]

  const timeColor = (_v: string | undefined, i: number) => {
    const t = times[lanes[i] - 1]
    if (t == null) return '#94a3b8'
    if (sorted.length >= 2 && t <= sorted[1]) return '#fcd34d'
    if (sorted.length >= 5 && t >= sorted[sorted.length - 2]) return '#f87171'
    return '#e2e8f0'
  }

  const rows = [
    {
      label: '展示T',
      values: lanes.map(l => fmt(get(l)?.exhibition_time, 2)),
      colorFn: timeColor
    },
    {
      label: '展示ST',
      values: lanes.map(l => fmt(get(l)?.exhibition_st, 2)),
      colorFn: (v: string | undefined) => {
        const n = parseFloat(v ?? '99')
        return n <= 0.15 ? '#fcd34d' : n >= 0.20 ? '#f87171' : '#e2e8f0'
      }
    },
    {
      label: '1周T',
      values: lanes.map(l => fmt(get(l)?.exhibition_1lap, 2)),
      colorFn: () => '#94a3b8' as string
    },
    {
      label: '回り足',
      values: lanes.map(l => fmt(get(l)?.exhibition_turning, 2)),
      colorFn: () => '#94a3b8' as string
    },
  ]

  return <SectionTable title="展示データ" lanes={lanes} rows={rows} />
}


// ───── 結果確認・改善コメントパネル ─────
function ResultAndMemoPanel({ raceId, raceDate, raceVenue, systemDetail }: { raceId: number; raceDate: string; raceVenue: string; systemDetail: SystemPredictionDetail | null }) {
  const [result, setResult] = useState<RaceResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [memo, setMemo] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const isPast = raceDate < new Date().toISOString().slice(0, 10)
  if (!isPast) return null

  async function fetchResult() {
    setLoading(true)
    setError(null)
    try {
      let res = await getRaceResult(raceId)
      const hasResult = !!(res.data && (res.data.trifecta_result || res.data.winner_lane))

      if (!hasResult) {
        await scrapeRaceResult({ date: raceDate, venue: raceVenue })
        res = await getRaceResult(raceId)
      }

      const refreshed = res.data
      const refreshedHasResult = !!(refreshed && (refreshed.trifecta_result || refreshed.winner_lane))
      setResult(refreshedHasResult ? refreshed : null)
      setFetched(true)
      if (!refreshedHasResult) {
        setError('確定結果を取得しましたが、対象レースの結果はまだ登録されていません。')
      }
    } catch (err: unknown) {
      setResult(null)
      setFetched(false)
      setError(err instanceof Error ? err.message : '確定結果の取得に失敗しました。')
    } finally {
      setLoading(false)
    }
  }

  async function handleSaveMemo() {
    setSaving(true)
    try {
      await savePredictionMemo(raceId, memo)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    setSaving(false)
  }

  const trifecta = normalizeBetPattern(result?.trifecta_result)
  const exacta = normalizeBetPattern(result?.exacta_result)
  const podium = [
    { label: '1着', lane: result?.winner_lane ?? null },
    { label: '2着', lane: result?.place2_lane ?? null },
    { label: '3着', lane: result?.place3_lane ?? null },
  ].filter((item): item is { label: string; lane: number } => item.lane != null)
  const betChecks = [
    {
      label: '本線F1',
      bets: ensureBetList(systemDetail?.trifecta_f1),
      resultValue: trifecta,
      payout: result?.trifecta_payout ?? null,
      accent: '#60a5fa',
      background: '#0f172a',
    },
    {
      label: '本線F2',
      bets: ensureBetList(systemDetail?.trifecta_f2),
      resultValue: trifecta,
      payout: result?.trifecta_payout ?? null,
      accent: '#a78bfa',
      background: '#1f1638',
    },
    {
      label: '二連単',
      bets: ensureBetList(systemDetail?.exacta),
      resultValue: exacta,
      payout: result?.exacta_payout ?? null,
      accent: '#34d399',
      background: '#0b1f1a',
    },
    {
      label: '万舟',
      bets: ensureBetList(systemDetail?.manshu),
      resultValue: trifecta,
      payout: result?.trifecta_payout ?? null,
      accent: '#f59e0b',
      background: '#241507',
    },
  ].map((item) => {
    const safeBets = Array.isArray(item.bets) ? item.bets : []
    const normalizedBets = safeBets
      .map((bet) => normalizeBetPattern(typeof bet === 'string' ? bet : null))
      .filter((value): value is string => !!value)
    const isHit = item.resultValue ? normalizedBets.includes(item.resultValue) : null
    return {
      ...item,
      normalizedBets,
      isHit,
      payoutLabel: isHit ? formatPayout(item.payout) : null,
    }
  })

  return (
    <div style={{ border: '1px solid #1e3a5f', borderRadius: 10, marginTop: 12, overflow: 'hidden' }}>
      <div style={{ background: '#0a1f3f', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid #1e3a5f' }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 13 }}>確定結果・改善コメント</span>
        <span style={{ fontSize: 11, color: '#64748b' }}>（過去レース）</span>
      </div>
      <div style={{ padding: '12px 14px', background: '#090f1e' }}>
        {error && (
          <div style={{ marginBottom: 10, padding: '8px 10px', borderRadius: 8, border: '1px solid #7f1d1d', background: '#2a0f14', color: '#fca5a5', fontSize: 12 }}>
            {error}
          </div>
        )}
        {!fetched ? (
          <button onClick={fetchResult} disabled={loading}
            style={{ padding: '7px 18px', background: '#1e3a5f', color: '#93c5fd', border: '1px solid #3b82f6', borderRadius: 7, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
            {loading ? '取得中…' : '確定結果を取得'}
          </button>
        ) : result && (result.trifecta_result || result.winner_lane) ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
            {/* 結果表示 */}
            <div style={{ minWidth: 280, flex: '1 1 320px' }}>
              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 6, fontWeight: 700 }}>確定結果</div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                {podium.map(({ label, lane }) => (
                  <div key={label} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{label}</div>
                    <div style={{
                      width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: LANE_BG[lane] || '#1e3a5f', color: LANE_TEXT[lane] || '#e2e8f0',
                      fontWeight: 700, fontSize: 16, border: '2px solid #1e3a5f'
                    }}>{lane}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {trifecta && <span style={{ fontSize: 12, color: '#fcd34d', background: '#1a1000', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace' }}>3連単 {trifecta}</span>}
                {typeof result?.trifecta_payout === 'number' && <span style={{ fontSize: 12, color: '#fbbf24', background: '#2a1a00', padding: '2px 8px', borderRadius: 5 }}>払戻 {formatPayout(result?.trifecta_payout)}</span>}
                {exacta && <span style={{ fontSize: 12, color: '#6ee7b7', background: '#001a0f', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace' }}>2連単 {exacta}</span>}
                {typeof result?.exacta_payout === 'number' && <span style={{ fontSize: 12, color: '#86efac', background: '#052e16', padding: '2px 8px', borderRadius: 5 }}>払戻 {formatPayout(result?.exacta_payout)}</span>}
                {typeof result?.trifecta_place_payout === 'number' && <span style={{ fontSize: 12, color: '#c4b5fd', background: '#1e1b4b', padding: '2px 8px', borderRadius: 5 }}>3連複 {formatPayout(result?.trifecta_place_payout)}</span>}
              </div>
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8, fontWeight: 700 }}>買い目別的中判定</div>
                <div style={{ display: 'grid', gap: 8 }}>
                  {betChecks.map((item) => (
                    <div key={item.label} style={{ border: `1px solid ${item.accent}55`, background: item.background, borderRadius: 8, padding: '10px 12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ color: item.accent, fontWeight: 700, fontSize: 13 }}>{item.label}</span>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: 999,
                          fontSize: 11,
                          fontWeight: 700,
                          background: item.isHit ? '#0f2d1a' : '#2d0f0f',
                          color: item.isHit ? '#22c55e' : '#f87171',
                          border: `1px solid ${item.isHit ? '#166534' : '#7f1d1d'}`
                        }}>
                          {item.isHit ? '的中' : '不的中'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {item.normalizedBets.length > 0 ? item.normalizedBets.map((bet) => (
                          <span key={`${item.label}-${bet}`} style={{
                            fontSize: 12,
                            fontFamily: 'monospace',
                            color: item.resultValue && bet === item.resultValue ? '#f8fafc' : '#cbd5e1',
                            background: item.resultValue && bet === item.resultValue ? `${item.accent}cc` : '#0b1220',
                            border: `1px solid ${item.resultValue && bet === item.resultValue ? item.accent : '#1e3a5f'}`,
                            borderRadius: 5,
                            padding: '2px 6px'
                          }}>
                            {bet}
                          </span>
                        )) : (
                          <span style={{ fontSize: 12, color: '#64748b' }}>買い目なし</span>
                        )}
                      </div>
                      {item.payoutLabel && (
                        <div style={{ marginTop: 6, fontSize: 11, color: '#f8fafc' }}>払戻 {item.payoutLabel}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 6, fontWeight: 700 }}>改善コメント</div>
              <textarea
                value={memo}
                onChange={e => setMemo(e.target.value)}
                placeholder="予想との乖離や改善点を記入…"
                rows={3}
                style={{ width: '100%', background: '#0d1b2e', border: '1px solid #1e3a5f', borderRadius: 6, color: '#e2e8f0', fontSize: 12, padding: '6px 8px', resize: 'vertical', boxSizing: 'border-box' }}
              />
              <button onClick={handleSaveMemo} disabled={saving}
                style={{ marginTop: 6, padding: '5px 16px', background: saved ? '#0f2d1a' : '#1e3a5f', color: saved ? '#22c55e' : '#93c5fd', border: '1px solid #3b82f6', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
                {saving ? '保存中…' : saved ? '保存済' : '保存'}
              </button>
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: '#64748b' }}>結果データがありません（未スクレイピング）</div>
        )}
      </div>
    </div>
  )
}

function SystemPredictionPanel({ detail }: { detail: SystemPredictionDetail }) {
  const escapeVerdict = (detail as any).escape_verdict || (detail as any).nige_verdict || (
    detail.fire_boat_lane
      ? `逃堅め候補（${detail.fire_boat_lane}号発動警戒）`
      : '逃堅め候補'
  )
  const sujiAndNotes = [
    (detail as any).suji,
    ...(Array.isArray(detail.notes) ? detail.notes : []),
  ].filter((value): value is string => !!value && value.trim().length > 0)

  return (
    <div style={{ border: '2px solid #3b82f644', borderRadius: 10, marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ background: '#1e3a5f44', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid #1e3a5f', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 14 }}>システム予測 {detail.version || 'v60.0'}</span>
        <span style={{ padding: '2px 10px', borderRadius: 10, background: '#1e3a5f', color: '#94a3b8', fontSize: 12 }}>{detail.regime}</span>
        <span style={{ padding: '2px 10px', borderRadius: 10, background: '#1e3a5f', color: '#94a3b8', fontSize: 12 }}>{detail.s_in}（{detail.surface_type}）</span>
        <span style={{ fontSize: 12, color: '#64748b' }}>自信度: {Math.round(detail.confidence)}% / 波乱度: {Math.round(detail.wave_score)}%</span>
      </div>
      {/* v58.7 改正60：戻り額ゲート＋発動艇 */}
      {(() => {
        const v = detail.race_verdict || detail.payout_grade || '—'
        const vColor = v === '勝負' ? '#22c55e' : v === '通常' ? '#3b82f6' : '#ef4444'
        const vBg = v === '勝負' ? '#0f2d1a' : v === '通常' ? '#0d1b3e' : '#2d0f0f'
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', padding: '10px 14px', background: vBg, borderBottom: '1px solid #1e3a5f' }}>
            <span style={{ fontSize: 13, fontWeight: 800, color: vColor, padding: '2px 12px', border: `1px solid ${vColor}`, borderRadius: 8 }}>判定: {v}</span>
            {detail.odds_available ? (
              <>
                <span style={{ fontSize: 12, color: '#cbd5e1' }}>合成オッズ <b style={{ color: '#fcd34d' }}>{(detail.synthetic_odds ?? 0).toFixed(1)}倍</b></span>
                <span style={{ fontSize: 12, color: '#cbd5e1' }}>戻り額 <b style={{ color: '#6ee7b7' }}>¥{Math.round(detail.payout ?? 0).toLocaleString()}</b></span>
                <span style={{ fontSize: 10, color: '#64748b' }}>（≤3万=見送り / 3万〜5万=通常 / ≥5万=勝負）</span>
              </>
            ) : (
              <span style={{ fontSize: 12, color: '#f87171' }}>オッズ未取得のため戻り額判定不能（全枝見送り）</span>
            )}
            {detail.fire_boat_lane ? (
              <span style={{ fontSize: 12, color: '#fb923c', fontWeight: 700, padding: '2px 10px', background: '#2d1500', borderRadius: 8 }}>
                発動艇 {detail.fire_boat_lane}号（発生率{Math.round((detail.fire_boat_gen ?? 0) * 100)}%）
              </span>
            ) : (
              <span style={{ fontSize: 12, color: '#64748b' }}>発動艇なし（1逃げ主体）</span>
            )}
            {detail.main_attack_course && (
              <span style={{ fontSize: 12, color: '#94a3b8' }}>攻め主体 {detail.main_attack_course}号（{detail.attack_type}）</span>
            )}
          </div>
        )
      })()}
      <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
        <div>
          <div style={{ fontSize: 11, color: '#60a5fa', marginBottom: 6, fontWeight: 600 }}>本線F1（頭:{detail.f1_head}号・¥{detail.budget_main.toLocaleString()}）</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {detail.trifecta_f1.map((t, i) => <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace', fontSize: 12 }}>{t}</span>)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#a78bfa', marginBottom: 6, fontWeight: 600 }}>本線F2{detail.f2_head ? `（頭:${detail.f2_head}号）` : ''}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {detail.trifecta_f2.length > 0 ? detail.trifecta_f2.map((t, i) => <span key={i} style={{ background: '#2d1f5e', color: '#c4b5fd', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace', fontSize: 12 }}>{t}</span>) : <span style={{ color: '#64748b', fontSize: 12 }}>なし</span>}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#34d399', marginBottom: 6, fontWeight: 600 }}>二連単（¥{detail.budget_exacta.toLocaleString()}）</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {detail.exacta.map((e, i) => <span key={i} style={{ background: '#0f2d23', color: '#6ee7b7', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace', fontSize: 12 }}>{e}</span>)}
          </div>
        </div>
      </div>
      <div style={{ padding: '0 14px 14px' }}>
        <div style={{ fontSize: 11, color: '#f59e0b', marginBottom: 6, fontWeight: 600 }}>万舟（全レース必須・¥{detail.budget_manshu.toLocaleString()}）</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {detail.manshu.map((m, i) => <span key={i} style={{ background: '#2d1a00', color: '#fcd34d', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace', fontSize: 12 }}>{m}</span>)}
        </div>
        {detail.notes.length > 0 && (
          <div style={{ marginTop: 10, padding: '6px 10px', background: '#1a0a00', borderRadius: 6, borderLeft: '3px solid #f59e0b' }}>
            {detail.notes.map((n, i) => <div key={i} style={{ fontSize: 12, color: '#fcd34d' }}>⚠ {n}</div>)}
          </div>
        )}
      </div>
      <div style={{ padding: '0 14px 14px' }}>
        <div style={{ background: '#2d1f5e', border: '1px solid #4c1d95', borderRadius: 8, overflow: 'hidden' }}>
          {[
            ['パターン', detail.regime || '—'],
            ['逃げ判定', escapeVerdict],
            ['主攻め候補', detail.main_attack_course ? `${detail.main_attack_course}号${detail.attack_type ? `（${detail.attack_type}）` : ''}` : '—'],
            ['沈み候補', detail.sink_boat_lane ? `${detail.sink_boat_lane}号` : '—'],
            ['スジ・特記', sujiAndNotes.length > 0 ? sujiAndNotes.join(' / ') : '—'],
          ].map(([label, value], index) => (
            <div key={label} style={{
              display: 'grid',
              gridTemplateColumns: '120px 1fr',
              gap: 12,
              padding: '10px 12px',
              borderTop: index === 0 ? 'none' : '1px solid #5b21b6',
              background: index % 2 === 0 ? '#2d1f5e' : '#312e81'
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#c4b5fd' }}>{label}</div>
              <div style={{ fontSize: 12, color: '#ede9fe' }}>{value}</div>
            </div>
          ))}
        </div>
      </div>
      {detail.boat_evals && detail.boat_evals.length > 0 && (
        <div style={{ padding: '0 14px 14px' }}>
          <div style={{ fontSize: 11, color: '#60a5fa', marginBottom: 6, fontWeight: 600 }}>各艇評価（全6艇）</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {detail.boat_evals.map((b) => {
              const roleColor = b.role === '頭' ? '#fcd34d' : b.role === '2着候補' ? '#60a5fa' : '#64748b'
              return (
                <div key={b.lane} style={{ flex: 1, textAlign: 'center', background: LANE_BG[b.lane] || '#0a1520', borderRadius: 6, padding: 6, border: b.is_fire ? '1px solid #fb923c' : '1px solid #1e3a5f' }}>
                  <div style={{ fontSize: 11, color: '#cbd5e1', fontWeight: 700 }}>{b.lane}号{b.is_fire ? ' 🔥' : ''}</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: roleColor }}>{b.role}</div>
                  <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>EI:{b.ei ?? '—'}</div>
                  <div style={{ fontSize: 10, color: '#94a3b8' }}>優勢:{b.ei_rank ?? '—'}位</div>
                  <div style={{ fontSize: 10, color: '#94a3b8' }}>基準ST:{b.st_rank ?? '—'}位</div>
                  <div style={{ fontSize: 10, color: '#a5b4fc' }}>D-KAN:{(b.dkan ?? b.completion_power) ?? '—'}/5</div>
                  {b.gen_rate != null && b.gen_rate > 0 && (
                    <div style={{ fontSize: 10, color: '#fb923c' }}>発生率:{Math.round(b.gen_rate * 100)}%</div>
                  )}
                  {b.lane === 1 && b.hit_rate != null && b.hit_rate > 0 && (
                    <div style={{ fontSize: 10, color: '#f87171' }}>被弾:{Math.round(b.hit_rate * 100)}%</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ───── オッズセクション ─────
function OddsSection({ race }: { race: Race }) {
  const odds3t = race.odds_3t || {}
  const odds2t = race.odds_2t || {}
  const oddsWin = race.odds_win || {}
  const has = Object.keys(odds3t).length > 0 || Object.keys(oddsWin).length > 0
  if (!has) return null

  const top3t = Object.entries(odds3t)
    .filter(([, v]) => v && v > 0)
    .sort((a, b) => a[1] - b[1])
    .slice(0, 12)
  const top2t = Object.entries(odds2t)
    .filter(([, v]) => v && v > 0)
    .sort((a, b) => a[1] - b[1])
    .slice(0, 8)
  const winRows = [1, 2, 3, 4, 5, 6]

  const updated = race.odds_updated_at
    ? new Date(race.odds_updated_at).toLocaleString('ja-JP', { hour: '2-digit', minute: '2-digit', month: 'numeric', day: 'numeric' })
    : null

  const cell: React.CSSProperties = { padding: '4px 8px', fontSize: 13, border: '1px solid #1e3a5f', textAlign: 'center' }

  return (
    <div style={{ marginBottom: 16 }}>
      <SectionHeader title="オッズ" sub={updated ? `更新 ${updated}` : 'boaters.com'} />
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', background: '#0d1b2e', padding: 12, borderRadius: '0 0 6px 6px' }}>
        {top3t.length > 0 && (
          <div style={{ flex: '1 1 200px', minWidth: 180 }}>
            <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 6, fontWeight: 700 }}>3連単 人気順</div>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                {top3t.map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ ...cell, color: '#e2e8f0', fontWeight: 600, width: '55%' }}>{k}</td>
                    <td style={{ ...cell, color: v < 10 ? '#fcd34d' : v < 50 ? '#e2e8f0' : '#94a3b8', fontWeight: 700 }}>{v.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {top2t.length > 0 && (
          <div style={{ flex: '1 1 160px', minWidth: 140 }}>
            <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 6, fontWeight: 700 }}>2連単 人気順</div>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                {top2t.map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ ...cell, color: '#e2e8f0', fontWeight: 600, width: '55%' }}>{k}</td>
                    <td style={{ ...cell, color: v < 10 ? '#fcd34d' : '#e2e8f0', fontWeight: 700 }}>{v.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {Object.keys(oddsWin).length > 0 && (
          <div style={{ flex: '1 1 140px', minWidth: 120 }}>
            <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 6, fontWeight: 700 }}>単勝</div>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                {winRows.map(l => {
                  const v = oddsWin[String(l)]
                  return (
                    <tr key={l}>
                      <td style={{ ...cell, background: LANE_BG[l], color: LANE_TEXT[l], fontWeight: 700, width: 40 }}>{l}</td>
                      <td style={{ ...cell, color: v && v < 3 ? '#fcd34d' : '#e2e8f0', fontWeight: 700 }}>{v != null ? v.toFixed(1) : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ───── DOTパスワードモーダル（RaceDetail用） ─────
const DOT_PW = 'Yalove0911'
const DOT_KEY = 'dot_unlocked'

function DotPasswordModalInline({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
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

// ───── メインページ ─────
export default function RaceDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [race, setRace] = useState<Race | null>(null)
  const [loading, setLoading] = useState(true)
  const [predicting, setPredicting] = useState(false)
  const [systemDetail, _setSystemDetail] = useState<SystemPredictionDetail | null>(null)
  const [venueConfig, setVenueConfig] = useState<VenueConfig | null>(null)
  const [showDotModal, setShowDotModal] = useState(false)

  async function fetchRace() {
    if (!id) return
    setLoading(true)
    try {
      const res = await getRace(parseInt(id))
      setRace(res.data)
      // 会場設定を取得
      if (res.data?.venue) {
        try {
          const vc = await getVenueConfig(res.data.venue)
          setVenueConfig(vc.data)
        } catch { /* ignore */ }
      }
    } catch {
      setRace(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchRace() }, [id])

  async function handlePredict(source: 'ensemble' | 'claude' | 'gemini') {
    if (!id) return
    setPredicting(true)
    try {
      const res = await predictRace(parseInt(id), source)
      setRace(res.data)
    } catch { /* ignore */ } finally { setPredicting(false) }
  }

  if (loading) return <div className="loading-spinner"><div className="spinner" />読み込み中…</div>
  if (!race) return (
    <div className="empty-state">
      <div className="empty-state-icon">⚠️</div>
      <div className="empty-state-text">レースが見つかりません</div>
      <div style={{ marginTop: 12 }}><Link to="/" className="btn btn-secondary">一覧に戻る</Link></div>
    </div>
  )

  const boats = race.boats || []
  const predictions = race.predictions || []
  const sc = { scheduled: '発売中', running: '発走中', finished: '確定' }[race.status || 'scheduled'] || '発売中'
  const scCls = { scheduled: '#3b82f6', running: '#f59e0b', finished: '#34d399' }[race.status || 'scheduled'] || '#3b82f6'

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* 戻るリンク */}
      <div style={{ marginBottom: 12 }}>
        <Link to="/" style={{ color: '#64748b', fontSize: 13, textDecoration: 'none' }}>← レース一覧</Link>
      </div>

      {/* ヘッダー */}
      <div style={{ background: 'linear-gradient(90deg, #0a1f3f, #0d1b2e)', borderRadius: 10, padding: '14px 18px', marginBottom: 18, border: '1px solid #1e3a5f' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>
              {race.venue} {race.race_no}R
              {race.race_name && <span style={{ fontSize: 13, color: '#64748b', marginLeft: 8 }}>{race.race_name}</span>}
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, color: '#94a3b8' }}>{race.date}</span>
              <span style={{ padding: '2px 10px', borderRadius: 8, border: `1px solid ${scCls}`, color: scCls, fontSize: 12 }}>{sc}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button onClick={() => {
              if (sessionStorage.getItem('dot_unlocked') === '1') {
                navigate('/dot')
              } else {
                setShowDotModal(true)
              }
            }}
              style={{ padding: '8px 16px', background: 'rgba(245,158,11,0.15)', color: '#f59e0b', border: '1px solid #78450a', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
              DOTシステム（開発中）
            </button>
            <button onClick={() => navigate('/shishido')}
              style={{ padding: '8px 16px', background: 'rgba(167,139,250,0.15)', color: '#a78bfa', border: '1px solid #4c3a9e', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
              宍戸予想 v58.7
            </button>
            <button onClick={() => handlePredict('ensemble')} disabled={predicting}
              style={{ padding: '8px 14px', background: '#1e2a40', color: '#a78bfa', border: '1px solid #4c3a9e', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}>
              Ensemble
            </button>
            <button onClick={() => handlePredict('claude')} disabled={predicting}
              style={{ padding: '8px 14px', background: '#1e2a40', color: '#f59e0b', border: '1px solid #78450a', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}>
              Claude
            </button>
          </div>
        </div>

        {/* 会場特性バナー */}
        {venueConfig && (
          <div style={{ marginTop: 10, background: 'linear-gradient(90deg, #064e3b, #065f46)', borderRadius: 6, padding: '8px 12px', border: '1px solid #10b981' }}>
            <div style={{ fontSize: 12, color: '#6ee7b7', lineHeight: 1.7, display: 'flex', flexWrap: 'wrap', gap: '0 8px' }}>
              {[
                `ボートレース${venueConfig.venue_name}専用`,
                venueConfig.water_type && `${venueConfig.water_type}`,
                venueConfig.back_width_m && `バック${venueConfig.back_width_m}m幅`,
                venueConfig.surface_type && `${venueConfig.surface_type}水面`,
                venueConfig.c2_rate != null && `2C差し率${venueConfig.c2_rate}%`,
                venueConfig.has_tide_correction != null && (venueConfig.has_tide_correction ? '潮汐補正あり' : '潮汐適用なし'),
                venueConfig.prompt_version && `${venueConfig.prompt_version}`,
              ].filter(Boolean).map((item, i, arr) => (
                <span key={i}>{item}{i < arr.length - 1 ? ' /' : ''}</span>
              ))}
            </div>
            {venueConfig.notes && (
              <div style={{ fontSize: 11, color: '#a7f3d0', marginTop: 4, borderTop: '1px solid #065f46', paddingTop: 4 }}>
                {venueConfig.notes}
              </div>
            )}
          </div>
        )}

        {/* 天候情報 */}
        {(race.weather || race.wind_speed || race.temperature || race.wave_height) && (
          <div style={{ marginTop: 8, display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, color: '#94a3b8' }}>
            {race.weather && <span>天候: <span style={{ color: '#e2e8f0' }}>{race.weather}</span></span>}
            {race.wind_speed != null && <span>風速: <span style={{ color: '#e2e8f0' }}>{race.wind_speed}m/s</span></span>}
            {race.wind_direction && <span>風向: <span style={{ color: '#e2e8f0' }}>{race.wind_direction}</span></span>}
            {race.temperature != null && <span>気温: <span style={{ color: '#e2e8f0' }}>{race.temperature}℃</span></span>}
            {race.wave_height != null && <span>波高: <span style={{ color: '#e2e8f0' }}>{race.wave_height}cm</span></span>}
          </div>
        )}
      </div>

      {/* データセクション */}
      {boats.length > 0 ? (
        <div>
          <Section1Basic boats={boats} venueConfig={venueConfig} venueName={race.venue} />
          <Section2Motor boats={boats} />
          <Section3Start boats={boats} />
          <SectionExhibit boats={boats} />
          <Section5aCourse boats={boats} />
          <Section5bKimete boats={boats} venueConfig={venueConfig} venueName={race.venue} />
          <Section5cNigiri boats={boats} venueConfig={venueConfig} venueName={race.venue} />
          <Section5eLocal boats={boats} />
          <Section5fGeneral boats={boats} />
          <Section5gP2LinkSummary boats={boats} />
          {systemDetail && <Section6EI detail={systemDetail} venueName={race.venue} />}
          {systemDetail && <Section7TI detail={systemDetail} boats={boats} venueName={race.venue} />}
          {systemDetail && <Section8OverallJudgement detail={systemDetail} boats={boats} venueName={race.venue} />}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b', background: '#0d1b2e', borderRadius: 10, marginBottom: 18 }}>
          出走表データがありません。スクレイピングを実行してください。
        </div>
      )}

      {/* オッズ */}
      <OddsSection race={race} />

      {/* 予測結果 */}
      {(systemDetail || predictions.length > 0) && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#94a3b8', marginBottom: 12 }}>予測結果</div>
          {systemDetail && <SystemPredictionPanel detail={systemDetail} />}
          {/* 過去レース：確定結果取得 & 改善コメント */}
          <ResultAndMemoPanel raceId={race.id!} raceDate={race.date} raceVenue={race.venue} systemDetail={systemDetail} />
        </div>
      )}

      {/* 予測なし・過去レースの場合も結果パネルを表示 */}
      {!(systemDetail || predictions.length > 0) && race.id && (
        <div style={{ marginTop: 20 }}>
          <ResultAndMemoPanel raceId={race.id} raceDate={race.date} raceVenue={race.venue} systemDetail={null} />
        </div>
      )}

      {predicting && (
        <div className="loading-spinner" style={{ marginTop: 16 }}>
          <div className="spinner" />AI予測を生成中…
        </div>
      )}

      {/* DOTシステム パスワードモーダル */}
      {showDotModal && (
        <DotPasswordModalInline onClose={() => setShowDotModal(false)} onSuccess={() => { setShowDotModal(false); navigate('/dot') }} />
      )}
    </div>
  )
}
