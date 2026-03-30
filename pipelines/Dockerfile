FROM python:3.11-slim

WORKDIR /opt/pipelines

# System deps for PostGIS, Playwright, pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pipelines/pyproject.toml pipelines/setup.py* ./
COPY pipelines/countyiq/ ./countyiq/
COPY pipelines/alembic.ini ./
COPY pipelines/alembic/ ./alembic/
COPY pipelines/init-db/ ./init-db/

RUN pip install --no-cache-dir -e "."

# Install Playwright browsers
RUN playwright install --with-deps chromium

EXPOSE 3000

# Run Dagster webserver + daemon together
CMD ["sh", "-c", "dagster-daemon run & dagster-webserver -h 0.0.0.0 -p 3000 -m countyiq.definitions"]
