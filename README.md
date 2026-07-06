# Contexta

Contexta is a memory intelligence layer for AI agents. The backend is a Python
FastAPI engine that ingests observations, extracts memories, scores them,
stores them with tenant isolation, and retrieves context. The `web/` app is a
Next.js dashboard for account access, API keys, usage, memories, and setup docs.

## What Runs Where

- Backend API: Python package `contexta`, served with FastAPI/Uvicorn.
- Workers: Celery workers using Redis for extraction, embeddings, decay,
  reflection, and dream-cycle jobs.
- Storage: PostgreSQL with pgvector for memories and embeddings.
- Cache/queue: Redis.
- Dashboard: Next.js app in `web/`.

## Local Backend

```bash
pip install -e ".[dev]"
uvicorn contexta.api.app:app --reload
```

For full services:

```bash
docker compose up --build
```

## Local Dashboard

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`.

Demo auth accepts any email and password with 8 or more characters. API keys
generated in the dashboard are shown once and should be copied into agent
`.env` files:

```env
CONTEXTA_API_URL=http://localhost:8000
CONTEXTA_API_KEY=mk_live_your_key_here
```

## Python Package

The backend is a pip package from `pyproject.toml`. Use `pip install -e .` for
local development or build a wheel with:

```bash
python -m build
```

## NPM Package

The dashboard is a separate npm app under `web/`. It is not published as an npm
SDK yet; it is the hosted management UI.
