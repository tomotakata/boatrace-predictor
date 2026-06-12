import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getRace, predictRace, predictRaceSystem, getVenueConfig, getRaceResult, savePredictionMemo, type Race, type Boat, type Prediction, type SystemPredictionDetail, type VenueConfig, type RaceResult } from '../lib/api'

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
function Section1Basic({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  const rows = [
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
      label: '年齢',
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
  ]

  return (
    <SectionTable title="①基本" lanes={lanes} rows={rows} />
  )
}

// ───── ②モーター ─────
function Section2Motor({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  const rows = [
    {
      label: 'M出足',
      values: lanes.map(l => fmt(get(l)?.motor_dashfoot, 1)),
      colorFn: (_v: string | undefined, i: number) => {
        const b = get(lanes[i]); const val = b?.motor_dashfoot
        if (val == null) return '#94a3b8'
        // 上位2位を黄色
        const sorted = boats.map(b2 => b2.motor_dashfoot ?? 0).sort((a, b2) => b2 - a)
        return val >= sorted[1] ? '#fcd34d' : val <= sorted[3] ? '#f87171' : '#e2e8f0'
      }
    },
    {
      label: 'M伸び足',
      values: lanes.map(l => fmt(get(l)?.motor_extfoot, 1)),
      colorFn: (_v: string | undefined, i: number) => {
        const b = get(lanes[i]); const val = b?.motor_extfoot
        if (val == null) return '#94a3b8'
        const sorted = boats.map(b2 => b2.motor_extfoot ?? 0).sort((a, b2) => b2 - a)
        return val >= sorted[1] ? '#fcd34d' : val <= sorted[3] ? '#f87171' : '#e2e8f0'
      }
    },
    {
      label: 'M2連率',
      values: lanes.map(l => get(l)?.motor_place2_rate ? `${fmt(get(l)!.motor_place2_rate)}%` : '—'),
      colorFn: (v: string | undefined) => {
        const n = parseFloat(v ?? '0'); return n >= 40 ? '#fcd34d' : n <= 20 ? '#f87171' : '#e2e8f0'
      }
    },
    {
      label: 'モーターNo',
      values: lanes.map(l => get(l)?.motor_no ? `#${get(l)!.motor_no}` : '—'),
      colorFn: () => '#94a3b8'
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
    // c1_tricast is actually 2-place rate based on context
    const r = (b as any)[`c${lane}_tricast_rate`]  // using tricast as 3-place
    return fmtPct(r)
  })
  const races = lanes.map(l => {
    const b = get(l); if (!b) return '—'
    const lane = b.lane
    const r = (b as any)[`c${lane}_races`]
    return r ? String(r) : '—'
  })

  const pctColor = (v: string | undefined) => {
    const n = parseFloat(v ?? '0')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n >= 50 ? '#fcd34d' : n >= 30 ? '#f59e0b' : n < 5 ? '#f87171' : '#e2e8f0'
  }

  const rows = [
    { label: '出走数(自C)', values: races, colorFn: () => '#94a3b8' as string },
    { label: '勝率(自C)', values: winRates, colorFn: pctColor },
    { label: '3連率(自C)', values: p2Rates, colorFn: pctColor },
    {
      label: '全国勝率',
      values: lanes.map(l => fmtPct(get(l)?.national_win_rate)),
      colorFn: pctColor
    },
    {
      label: '全国2連率',
      values: lanes.map(l => fmtPct(get(l)?.national_place2_rate)),
      colorFn: pctColor
    },
    {
      label: '当地勝率',
      values: lanes.map(l => fmtPct(get(l)?.local_win_rate)),
      colorFn: pctColor
    },
    {
      label: '当地2連率',
      values: lanes.map(l => fmtPct(get(l)?.local_place2_rate)),
      colorFn: pctColor
    },
  ]

  return <SectionTable title="⑤a コース別・勝率" sub="(自コース直近)" lanes={lanes} rows={rows} />
}

// ───── ⑤b コース別決まり手 ─────
function Section5bKimete({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

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
      label: '差し率',
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

  return <SectionTable title="⑤b コース別決まり手" sub="(自コース)" lanes={lanes} rows={rows} />
}

// ───── ⑤c 握り率 ─────
function Section5cNigiri({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)

  const pctColor = (v: string | undefined) => {
    const n = parseFloat(v ?? '0')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n >= 70 ? '#fcd34d' : n >= 50 ? '#f59e0b' : n > 0 ? '#e2e8f0' : '#64748b'
  }

  const rows = [
    {
      label: '握り率',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.nigiri_rate != null ? fmtPct(b.nigiri_rate) : '—'
      }),
      colorFn: pctColor
    },
    {
      label: '握り発生数',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.nigiri_occurrence != null ? String(b.nigiri_occurrence) : '—'
      }),
      colorFn: () => '#94a3b8' as string
    },
    {
      label: '全国逃げ数',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.nige_count != null ? String(b.nige_count) : '—'
      }),
      colorFn: () => '#94a3b8' as string
    },
    {
      label: '全国差し数',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.sashi_count != null ? String(b.sashi_count) : '—'
      }),
      colorFn: () => '#94a3b8' as string
    },
    {
      label: '全国まくり数',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.makuri_count != null ? String(b.makuri_count) : '—'
      }),
      colorFn: () => '#94a3b8' as string
    },
    {
      label: '全国まくり差し数',
      values: lanes.map(l => {
        const b = get(l); if (!b) return '—'
        return b.makurisashi_count != null ? String(b.makurisashi_count) : '—'
      }),
      colorFn: () => '#94a3b8' as string
    },
  ]

  return <SectionTable title="⑤c 握り率・決まり手" sub="(全国)" lanes={lanes} rows={rows} />
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
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const hasData = boats.some(b => b.general1y_win_rate != null || b.general1y_place2_rate != null || b.general1y_races != null)
  if (!hasData) return null

  const pctColor = (v: string | undefined) => {
    const n = parseFloat(v ?? '0')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n >= 30 ? '#fcd34d' : n >= 15 ? '#f59e0b' : '#e2e8f0'
  }

  const rows = [
    { label: '出走数', values: lanes.map(l => get(l)?.general1y_races != null ? String(get(l)!.general1y_races) : '—'), colorFn: () => '#94a3b8' as string },
    { label: '勝率', values: lanes.map(l => fmtPct(get(l)?.general1y_win_rate)), colorFn: pctColor },
    { label: '2連率', values: lanes.map(l => fmtPct(get(l)?.general1y_place2_rate)), colorFn: pctColor },
    { label: '3連率', values: lanes.map(l => fmtPct(get(l)?.general1y_tricast_rate)), colorFn: pctColor },
    {
      label: '差/捲/捲差',
      values: lanes.map(l => {
        const b = get(l)
        if (!b) return '—'
        const s = b.general1y_sashi, mk = b.general1y_makuri, mz = b.general1y_makurizashi
        if (s == null && mk == null && mz == null) return '—'
        return `${s ?? 0}/${mk ?? 0}/${mz ?? 0}`
      }),
      colorFn: () => '#cbd5e1' as string
    },
  ]
  return <SectionTable title="⑤f 一般戦(G2,G3含む)" sub="(直近1年)" lanes={lanes} rows={rows} />
}

// ───── ⑤g イン逃げ時 直近1年 ─────
function Section5gEscape({ boats }: { boats: Boat[] }) {
  const lanes = [1, 2, 3, 4, 5, 6]
  const get = (lane: number) => boats.find(b => b.lane === lane)
  const hasData = boats.some(b => b.escape1y_place2_rate != null || b.escape1y_tricast_rate != null)
  if (!hasData) return null

  const pctColor = (v: string | undefined) => {
    const n = parseFloat(v ?? '0')
    if (isNaN(n) || v === '—') return '#94a3b8'
    return n >= 30 ? '#fcd34d' : n >= 15 ? '#f59e0b' : '#e2e8f0'
  }

  const rows = [
    { label: '2連率', values: lanes.map(l => fmtPct(get(l)?.escape1y_place2_rate)), colorFn: pctColor },
    { label: '3連率', values: lanes.map(l => fmtPct(get(l)?.escape1y_tricast_rate)), colorFn: pctColor },
  ]
  return <SectionTable title="⑤g イン逃げ時" sub="(直近1年)" lanes={lanes} rows={rows} />
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

// ───── 予測パネル ─────
const SOURCE_CONFIG = {
  claude: { label: 'Claude', color: '#f59e0b' },
  gemini: { label: 'Gemini', color: '#34d399' },
  ensemble: { label: 'Ensemble', color: '#a78bfa' },
  system_v56: { label: 'システム v56.3', color: '#60a5fa' },
  system_v58: { label: 'システム v58.7', color: '#60a5fa' },
}

function PredictionPanel({ prediction }: { prediction: Prediction }) {
  const src = prediction.source as keyof typeof SOURCE_CONFIG
  const srcCfg = SOURCE_CONFIG[src] || SOURCE_CONFIG.ensemble

  return (
    <div style={{ border: `1px solid ${srcCfg.color}44`, borderRadius: 10, marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ background: `${srcCfg.color}18`, padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: `1px solid ${srcCfg.color}33` }}>
        <span style={{ fontWeight: 700, color: srcCfg.color, fontSize: 14 }}>{srcCfg.label}</span>
        {prediction.confidence != null && (
          <span style={{ fontSize: 12, color: '#94a3b8' }}>信頼度: {Math.round(prediction.confidence * 100)}%</span>
        )}
      </div>
      <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          {prediction.trifecta && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>本命3連単</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#fcd34d', fontFamily: 'monospace' }}>{prediction.trifecta}</div>
            </div>
          )}
          {prediction.exacta && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>本命2連単</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#34d399', fontFamily: 'monospace' }}>{prediction.exacta}</div>
            </div>
          )}
          {prediction.honmei_trifecta && prediction.honmei_trifecta.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>本命党 3連単</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {prediction.honmei_trifecta.map((b, i) => (
                  <span key={i} style={{ background: '#1e3a5f', color: '#93c5fd', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace', fontSize: 12 }}>{b}</span>
                ))}
              </div>
            </div>
          )}
          {prediction.ana_trifecta && prediction.ana_trifecta.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>穴党 3連単</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {prediction.ana_trifecta.map((b, i) => (
                  <span key={i} style={{ background: '#2d1a1a', color: '#fca5a5', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace', fontSize: 12 }}>{b}</span>
                ))}
              </div>
            </div>
          )}
        </div>
        <div>
          {prediction.pattern && <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8 }}><strong style={{ color: '#60a5fa' }}>展開:</strong> {prediction.pattern}</p>}
          {prediction.main_attack && <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8 }}><strong style={{ color: '#60a5fa' }}>主攻め:</strong> {prediction.main_attack}</p>}
          {prediction.sink_candidate && <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8 }}><strong style={{ color: '#f87171' }}>沈み:</strong> {prediction.sink_candidate}</p>}
          {prediction.suji && <p style={{ fontSize: 12, color: '#64748b' }}>{prediction.suji}</p>}
        </div>
      </div>
      {prediction.ei && (
        <div style={{ padding: '8px 14px', borderTop: '1px solid #1e3a5f', display: 'flex', gap: 4 }}>
          {[1,2,3,4,5,6].map((l, i) => (
            <div key={l} style={{ flex: 1, textAlign: 'center', background: '#0a1520', borderRadius: 6, padding: 6 }}>
              <div style={{ fontSize: 10, color: '#64748b' }}>{l}号</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: prediction.judgement?.[i] === '頭' ? '#fcd34d' : prediction.judgement?.[i] === '軸' ? '#60a5fa' : '#94a3b8' }}>
                {prediction.judgement?.[i] || '—'}
              </div>
              <div style={{ fontSize: 11, color: '#94a3b8' }}>EI:{prediction.ei?.[i]?.toFixed(0) ?? '—'}</div>
              <div style={{ fontSize: 11, color: '#94a3b8' }}>TI:{prediction.ti?.[i]?.toFixed(0) ?? '—'}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ───── 結果確認・改善コメントパネル ─────
function ResultAndMemoPanel({ raceId, raceDate, systemDetail }: { raceId: number; raceDate: string; systemDetail: SystemPredictionDetail | null }) {
  const [result, setResult] = useState<RaceResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)
  const [memo, setMemo] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const isPast = raceDate < new Date().toISOString().slice(0, 10)
  if (!isPast) return null

  async function fetchResult() {
    setLoading(true)
    try {
      const res = await getRaceResult(raceId)
      setResult(res.data)
    } catch { setResult(null) }
    setFetched(true)
    setLoading(false)
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

  // 的中判定（3連単・2連単）
  const trifecta = result?.trifecta_result
  const exacta = result?.exacta_result
  const predTrifecta = systemDetail?.trifecta_f1?.concat(systemDetail?.trifecta_f2 || []) || []
  const predExacta = systemDetail?.exacta || []
  const hitTrifecta = trifecta ? predTrifecta.some(t => t.replace(/-/g, '') === trifecta.replace(/-/g, '').replace(/→/g, '')) : null
  const hitExacta = exacta ? predExacta.some(e => e.replace(/-/g, '') === exacta.replace(/-/g, '').replace(/→/g, '')) : null

  return (
    <div style={{ border: '1px solid #1e3a5f', borderRadius: 10, marginTop: 12, overflow: 'hidden' }}>
      <div style={{ background: '#0a1f3f', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid #1e3a5f' }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 13 }}>確定結果・改善コメント</span>
        <span style={{ fontSize: 11, color: '#64748b' }}>（過去レース）</span>
      </div>
      <div style={{ padding: '12px 14px', background: '#090f1e' }}>
        {!fetched ? (
          <button onClick={fetchResult} disabled={loading}
            style={{ padding: '7px 18px', background: '#1e3a5f', color: '#93c5fd', border: '1px solid #3b82f6', borderRadius: 7, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
            {loading ? '取得中…' : '確定結果を取得'}
          </button>
        ) : result && (result.trifecta_result || result.winner_lane) ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
            {/* 結果表示 */}
            <div style={{ minWidth: 200 }}>
              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 6, fontWeight: 700 }}>確定結果</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {[result.winner_lane, result.place2_lane, result.place3_lane].filter(Boolean).map((lane, i) => (
                  <div key={i} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{i + 1}着</div>
                    <div style={{
                      width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: LANE_BG[lane as number] || '#1e3a5f', color: LANE_TEXT[lane as number] || '#e2e8f0',
                      fontWeight: 700, fontSize: 16, border: '2px solid #1e3a5f'
                    }}>{lane}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {trifecta && <span style={{ fontSize: 12, color: '#fcd34d', background: '#1a1000', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace' }}>3連単 {trifecta}</span>}
                {exacta && <span style={{ fontSize: 12, color: '#6ee7b7', background: '#001a0f', padding: '2px 8px', borderRadius: 5, fontFamily: 'monospace' }}>2連単 {exacta}</span>}
              </div>
              {/* 的中バッジ */}
              <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {hitTrifecta != null && (
                  <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 700, background: hitTrifecta ? '#0f2d1a' : '#2d0f0f', color: hitTrifecta ? '#22c55e' : '#ef4444', border: `1px solid ${hitTrifecta ? '#22c55e' : '#ef4444'}` }}>
                    3連単 {hitTrifecta ? '的中' : '外れ'}
                  </span>
                )}
                {hitExacta != null && (
                  <span style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 700, background: hitExacta ? '#0f2d1a' : '#2d0f0f', color: hitExacta ? '#22c55e' : '#ef4444', border: `1px solid ${hitExacta ? '#22c55e' : '#ef4444'}` }}>
                    2連単 {hitExacta ? '的中' : '外れ'}
                  </span>
                )}
              </div>
            </div>
            {/* 改善コメント */}
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
  return (
    <div style={{ border: '2px solid #3b82f644', borderRadius: 10, marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ background: '#1e3a5f44', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid #1e3a5f', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 14 }}>システム予測 {detail.version || 'v58.7'}</span>
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

// ───── メインページ ─────
export default function RaceDetail() {
  const { id } = useParams<{ id: string }>()
  const [race, setRace] = useState<Race | null>(null)
  const [loading, setLoading] = useState(true)
  const [predicting, setPredicting] = useState(false)
  const [systemDetail, setSystemDetail] = useState<SystemPredictionDetail | null>(null)
  const [activePredIdx, setActivePredIdx] = useState(0)
  const [venueConfig, setVenueConfig] = useState<VenueConfig | null>(null)

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
      setActivePredIdx(0)
    } catch { /* ignore */ } finally { setPredicting(false) }
  }

  async function handlePredictSystem() {
    if (!id) return
    setPredicting(true)
    try {
      const res = await predictRaceSystem(parseInt(id))
      setRace(res.data)
      setSystemDetail(res.data.system_prediction_detail || null)
      setActivePredIdx(0)
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
  const activePred = predictions[activePredIdx]
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
            <button onClick={handlePredictSystem} disabled={predicting}
              style={{ padding: '8px 16px', background: 'linear-gradient(135deg,#1e40af,#3b82f6)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
              {predicting ? '予測中…' : 'システム予測 v58.7'}
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
          <Section1Basic boats={boats} />
          <Section2Motor boats={boats} />
          <Section3Start boats={boats} />
          <SectionExhibit boats={boats} />
          <Section5aCourse boats={boats} />
          <Section5bKimete boats={boats} />
          <Section5cNigiri boats={boats} />
          <Section5eLocal boats={boats} />
          <Section5fGeneral boats={boats} />
          <Section5gEscape boats={boats} />
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
          <ResultAndMemoPanel raceId={race.id!} raceDate={race.date} systemDetail={systemDetail} />
          {predictions.length > 1 && (
            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
              {predictions.map((p, i) => {
                const src = p.source as keyof typeof SOURCE_CONFIG
                const cfg = SOURCE_CONFIG[src] || SOURCE_CONFIG.ensemble
                return (
                  <button key={i} onClick={() => setActivePredIdx(i)}
                    style={{ padding: '5px 14px', borderRadius: 7, border: `1px solid ${i === activePredIdx ? cfg.color : '#1e3a5f'}`, background: i === activePredIdx ? cfg.color + '22' : 'transparent', color: i === activePredIdx ? cfg.color : '#64748b', cursor: 'pointer', fontSize: 12 }}>
                    {cfg.label}
                  </button>
                )
              })}
            </div>
          )}
          {activePred && <PredictionPanel prediction={activePred} />}
        </div>
      )}

      {/* 予測なし・過去レースの場合も結果パネルを表示 */}
      {!(systemDetail || predictions.length > 0) && race.id && (
        <div style={{ marginTop: 20 }}>
          <ResultAndMemoPanel raceId={race.id} raceDate={race.date} systemDetail={null} />
        </div>
      )}

      {predicting && (
        <div className="loading-spinner" style={{ marginTop: 16 }}>
          <div className="spinner" />AI予測を生成中…
        </div>
      )}
    </div>
  )
}
