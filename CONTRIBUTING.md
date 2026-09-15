# Contributing to Contexta

Thanks for your interest in Contexta! Contexta is a memory layer for AI agents — it gives agents long-term memory through a simple API: call `observe()` to store what happened, and `context()` to retrieve what is relevant. This repo contains the engine, services, SDKs, and dashboards that make up the platform.

## Repository layout

| Directory | What lives here |
| --- | --- |
| `contexta/` | The Python engine and FastAPI backend |
| `services/` | Go services: gateway, data-plane, aggregator |
| `clients/` | Official SDKs (e.g. TypeScript) |
| `dashboard/` | The Next.js dashboard |
| `landingpage/` | The public landing site |
| `docs/` | Documentation site |
| `tests/` | Backend tests |

## What to contribute

We highly encourage contributions! Right now, our main focus areas are:
1. **Enhancing the Dashboard UI**: If you are a frontend developer, we'd love your help making the Next.js dashboard more beautiful and intuitive.
2. **Codebase Cleanup & Refactoring**: Help us keep the code clean, remove unused dependencies, and simplify complex architecture.

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

Contexta is fully open-source and licensed under the Apache 2.0 License. You are free to use it for personal and commercial purposes.
