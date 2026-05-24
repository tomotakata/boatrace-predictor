import { useState, useRef } from 'react'
import { importClaudeChat, importGeminiChat } from '../lib/api'

type UploadStatus = 'idle' | 'loading' | 'done' | 'error'

interface UploadCardProps {
  title: string
  description: string
  onUpload: (file: File) => Promise<{ imported: number; skipped: number }>
}

function UploadCard({ title, description, onUpload }: UploadCardProps) {
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setStatus('loading')
    setResult(null)
    setErrorMsg('')
    try {
      const res = await onUpload(file)
      setResult(res)
      setStatus('done')
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'アップロードエラー')
      setStatus('error')
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  return (
    <div className="card">
      <div className="card-title">{title}</div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>{description}</p>

      <div
        className={`upload-zone ${dragging ? 'dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <div className="upload-icon">
          {status === 'loading' ? '⏳' : status === 'done' ? '✅' : '📁'}
        </div>
        <div className="upload-title">
          {status === 'loading' ? 'アップロード中…' :
           status === 'done' ? 'アップロード完了' :
           'ファイルをドラッグ&ドロップ'}
        </div>
        <div className="upload-desc">
          {status === 'idle' && 'またはクリックしてファイルを選択 (.json)'}
          {status === 'loading' && '処理中...'}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".json"
          style={{ display: 'none' }}
          onChange={handleChange}
        />
      </div>

      {status === 'done' && result && (
        <div className="upload-result success">
          取込完了: {result.imported} 件インポート / {result.skipped} 件スキップ
        </div>
      )}

      {status === 'error' && (
        <div className="upload-result error">
          エラー: {errorMsg || 'アップロードに失敗しました'}
        </div>
      )}
    </div>
  )
}

export default function Import() {
  return (
    <div>
      <h2 className="page-title">データ取込</h2>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 24 }}>
        Claude.aiまたはGeminiのチャット履歴をエクスポートしてアップロードすることで、
        過去の予測データを取り込めます。
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 20 }}>
        <UploadCard
          title="Claude.ai チャット履歴"
          description="Claude.aiからエクスポートしたJSONファイルをアップロードしてください。会話内の競艇予測を自動抽出します。"
          onUpload={async (file) => {
            const res = await importClaudeChat(file)
            return res.data
          }}
        />
        <UploadCard
          title="Gemini チャット履歴"
          description="Geminiからエクスポートしたテキスト/JSONファイルをアップロードしてください。会話内の競艇予測を自動抽出します。"
          onUpload={async (file) => {
            const res = await importGeminiChat(file)
            return res.data
          }}
        />
      </div>
    </div>
  )
}
