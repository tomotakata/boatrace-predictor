import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getRace, predictRace, predictRaceSystem, type Race, type Boat, type Prediction, type SystemPredictionDetail } from '../lib/api'

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
      label: '出足',
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
      label: '伸び足',
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
      label: '今節順',
      values: lanes.map(l => get(l)?.today_st_rank ? String(get(l)!.today_st_rank) : '—'),
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
      label: '3連率',
      values: lanes.map(l => fmtPct(get(l)?.local5y_tricast_rate)),
      colorFn: pctColor
    },
  ]

  return <SectionTable title="⑤e 当地別" sub="(直近5年)" lanes={lanes} rows={rows} />
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

function SystemPredictionPanel({ detail }: { detail: SystemPredictionDetail }) {
  return (
    <div style={{ border: '2px solid #3b82f644', borderRadius: 10, marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ background: '#1e3a5f44', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid #1e3a5f', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, color: '#60a5fa', fontSize: 14 }}>システム予測 v56.3</span>
        <span style={{ padding: '2px 10px', borderRadius: 10, background: '#1e3a5f', color: '#94a3b8', fontSize: 12 }}>{detail.regime}</span>
        <span style={{ padding: '2px 10px', borderRadius: 10, background: '#1e3a5f', color: '#94a3b8', fontSize: 12 }}>{detail.s_in}（{detail.surface_type}）</span>
        <span style={{ fontSize: 12, color: '#64748b' }}>自信度: {Math.round(detail.confidence)}% / 波乱度: {Math.round(detail.wave_score)}%</span>
      </div>
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

  async function fetchRace() {
    if (!id) return
    setLoading(true)
    try {
      const res = await getRace(parseInt(id))
      setRace(res.data)
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
              {race.weather && <span style={{ fontSize: 12, color: '#64748b' }}>天候: {race.weather}</span>}
              {race.wind_speed && <span style={{ fontSize: 12, color: '#64748b' }}>風速: {race.wind_speed}m</span>}
              {race.wind_direction && <span style={{ fontSize: 12, color: '#64748b' }}>風向: {race.wind_direction}</span>}
              {race.wave_height && <span style={{ fontSize: 12, color: '#64748b' }}>波高: {race.wave_height}cm</span>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button onClick={handlePredictSystem} disabled={predicting}
              style={{ padding: '8px 16px', background: 'linear-gradient(135deg,#1e40af,#3b82f6)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
              {predicting ? '予測中…' : 'システム予測 v56.3'}
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
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b', background: '#0d1b2e', borderRadius: 10, marginBottom: 18 }}>
          出走表データがありません。スクレイピングを実行してください。
        </div>
      )}

      {/* 予測結果 */}
      {(systemDetail || predictions.length > 0) && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#94a3b8', marginBottom: 12 }}>予測結果</div>
          {systemDetail && <SystemPredictionPanel detail={systemDetail} />}
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

      {predicting && (
        <div className="loading-spinner" style={{ marginTop: 16 }}>
          <div className="spinner" />AI予測を生成中…
        </div>
      )}
    </div>
  )
}
