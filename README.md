# Boatrace Predictor

AI競艇予測システム - FastAPI + Supabase + React

## 構成

```
boatrace-predictor/
├── api/index.py              # Vercel Serverless Function (FastAPI)
├── backend/app/
│   ├── main.py
│   ├── config.py
│   ├── models/race.py
│   ├── scrapers/
│   │   ├── boaters.py        # boaters-boatrace.com
│   │   ├── boatfrontier.py   # boatfrontier.jp (ログイン必要)
│   │   └── exhibition.py     # boatrace.jp
│   ├── llm/predictor.py      # Claude/Gemini予測エンジン
│   ├── importers/chat_importer.py
│   └── api/
│       ├── races.py
│       ├── analytics.py
│       └── scraping.py
├── frontend/                 # React + Vite + TypeScript
│   ├── src/
│   │   ├── pages/
│   │   │   ├── RaceList.tsx
│   │   │   ├── RaceDetail.tsx
│   │   │   ├── Analytics.tsx
│   │   │   ├── Scraping.tsx
│   │   │   └── Import.tsx
│   │   └── lib/api.ts
├── supabase/migrations/001_init.sql
├── vercel.json
└── requirements.txt
```

## セットアップ

### 1. 環境変数

```bash
cp .env.example .env
# .envを編集して各APIキーを設定
```

### 2. フロントエンド開発

```bash
cd frontend
npm install
npm run dev
```

### 3. バックエンド開発

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

### 4. Supabase マイグレーション

Supabaseダッシュボードで `supabase/migrations/001_init.sql` を実行

## デプロイ

```bash
vercel deploy --prod
```

## 本番URL

https://boatrace-predictor-ten.vercel.app/
