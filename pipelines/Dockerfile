FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

WORKDIR /opt/pipelines

# Refresh the slim base before installing browser dependencies. PostgreSQL is
# accessed through psycopg's binary wheel, and the application has no GDAL
# bindings, so compiler headers do not belong in the runtime image.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.6@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY pipelines/pyproject.toml pipelines/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project && uv cache clean
ENV PATH="/opt/pipelines/.venv/bin:$PATH"

# Install Playwright browsers into a path readable by the runtime user.
RUN mkdir -p /ms-playwright && playwright install --with-deps chromium

RUN groupadd --system --gid 10001 countyiq \
    && useradd --system --uid 10001 --gid countyiq --no-create-home countyiq

# Application code follows the expensive dependency and browser layers so
# ordinary source changes do not trigger a complete browser reinstall.
COPY --chown=countyiq:countyiq pipelines/countyiq/ ./countyiq/
COPY --chown=countyiq:countyiq pipelines/alembic.ini ./
COPY --chown=countyiq:countyiq pipelines/alembic/ ./alembic/
COPY --chown=countyiq:countyiq pipelines/init-db/ ./init-db/
COPY --chown=countyiq:countyiq pipelines/scripts/ ./scripts/
COPY --chown=countyiq:countyiq pipelines/eval/ ./eval/
RUN uv sync --locked --no-dev --no-editable && uv cache clean

# Dagster config
RUN mkdir -p /opt/dagster/home /opt/dagster/storage /opt/countyiq/archives \
    && chown -R countyiq:countyiq /opt/dagster /opt/countyiq /ms-playwright
COPY --chown=countyiq:countyiq pipelines/dagster.yaml /opt/dagster/home/dagster.yaml

# Keep compilers/installers and their vendored archive parsers out of the
# long-running scraper image after the locked environment is assembled.
RUN rm -f /bin/uv /bin/uvx /usr/local/bin/pip* /usr/local/bin/wheel \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/wheel*

USER 10001:10001

EXPOSE 3000

# Compose runs the webserver and daemon as separately supervised containers
# from this same image. The default remains useful for one-off image smoke tests.
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "countyiq.definitions"]
