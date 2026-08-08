FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY contexta ./contexta
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && pip install --no-cache-dir -e .

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
