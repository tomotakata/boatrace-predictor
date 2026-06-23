export default function DotSystem() {
  return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '60px 40px',
        maxWidth: 600,
        margin: '0 auto',
      }}>
        <div style={{
          fontSize: 28,
          fontWeight: 800,
          color: 'var(--accent-blue-light)',
          letterSpacing: 2,
          marginBottom: 12,
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          DOT SYSTEM
        </div>
        <div style={{
          display: 'inline-block',
          padding: '4px 14px',
          background: 'rgba(245,158,11,0.15)',
          border: '1px solid rgba(245,158,11,0.3)',
          borderRadius: 20,
          fontSize: 12,
          fontWeight: 600,
          color: '#f59e0b',
          marginBottom: 24,
        }}>
          開発中
        </div>
        <div style={{
          fontSize: 14,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
        }}>
          DOTシステムは現在開発中です。<br />
          機械学習ベースの予測エンジンを構築しています。
        </div>
      </div>
    </div>
  )
}
