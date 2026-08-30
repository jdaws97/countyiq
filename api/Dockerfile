FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project && uv cache clean

COPY api/main.py ./api/main.py
COPY api/lib/ ./api/lib/
COPY api/routes/ ./api/routes/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8000/api/health || exit 1

CMD ["/app/.venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
