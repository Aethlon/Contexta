FROM ghcr.io/astral-sh/uv:latest AS uv_bin
FROM python:3.12-slim

WORKDIR /app

COPY --from=uv_bin /uv /uvx /bin/

# Copy dependency specifications and lockfile for cached layer installation
COPY pyproject.toml uv.lock* alembic.ini ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and entrypoint
COPY contexta ./contexta
COPY scripts ./scripts
COPY entrypoint.sh /entrypoint.sh

RUN uv sync --frozen --no-dev && chmod +x /entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000 8001

ENTRYPOINT ["/entrypoint.sh"]

# The model-server stage layers the CPU Torch + sentence-transformers stack on top
# of the shared runtime image. Keeping it as a separate target means the API, worker
# and dashboard images never pay for it, while the model server still gets real
# Qwen3 embeddings instead of a degraded fallback.
FROM python:3.12-slim AS model-server

WORKDIR /app

COPY --from=uv_bin /uv /uvx /bin/

COPY pyproject.toml uv.lock* alembic.ini ./
RUN uv sync --frozen --no-dev --extra model-server --no-install-project

COPY contexta ./contexta
COPY scripts ./scripts
COPY entrypoint.sh /entrypoint.sh

RUN uv sync --frozen --no-dev --extra model-server && chmod +x /entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8001

ENTRYPOINT ["/entrypoint.sh"]
