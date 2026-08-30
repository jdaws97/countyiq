FROM python:3.11-slim

WORKDIR /opt/pipelines

# System deps for PostGIS, Playwright, pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq-dev \
    libgdal-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pipelines/pyproject.toml pipelines/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project && uv cache clean
ENV PATH="/opt/pipelines/.venv/bin:$PATH"

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Application code follows the expensive dependency and browser layers so
# ordinary source changes do not trigger a complete browser reinstall.
COPY pipelines/countyiq/ ./countyiq/
COPY pipelines/alembic.ini ./
COPY pipelines/alembic/ ./alembic/
COPY pipelines/init-db/ ./init-db/
RUN uv sync --locked --no-dev --no-editable && uv cache clean

# Dagster config
RUN mkdir -p /opt/dagster/home
COPY pipelines/dagster.yaml /opt/dagster/home/dagster.yaml

EXPOSE 3000

# Compose runs the webserver and daemon as separately supervised containers
# from this same image. The default remains useful for one-off image smoke tests.
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "countyiq.definitions"]
