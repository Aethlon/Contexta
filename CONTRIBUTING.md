# Contributing to Contexta

Thanks for your interest in Contexta! Contexta is a memory layer for AI agents — it gives agents long-term memory through a simple API: call `observe()` to store what happened, and `context()` to retrieve what is relevant. This repo contains the engine, services, SDKs, and dashboards that make up the platform.

## Repository layout

| Directory | What lives here |
| --- | --- |
| `contexta/` | The Python engine and FastAPI backend |
| `services/` | Go services: gateway, data-plane, aggregator |
| `clients/` | Official SDKs (e.g. TypeScript) |
| `web/` | The Next.js dashboard |
| `web-public/` | The public landing site |
| `docs/` | Documentation site |
| `tests/` | Backend tests |

## Local development

### Option A: Docker

```bash
cp .env.example .env
docker compose up
```

### Option B: Python directly

```bash
pip install -e ".[dev]"
uvicorn contexta.api.app:app
```

You will also need Postgres and Redis running (see `docker-compose.yml`).

## Tests

```bash
pytest
```

## Linting

```bash
ruff check contexta tests
```

For the dashboard(s), run `npm run lint` inside `web/` or `web-public/`.

## Making a pull request

1. Fork the repository and create a feature branch.
2. Make your change, keeping it focused and well described.
3. Run the tests and linter before opening the PR.
4. Open a pull request describing what you changed and why.

## License

Contexta is dual-licensed: Apache 2.0 for personal and self-use. Commercial use requires a paid license — contact licensing@contexta.dev for details.
