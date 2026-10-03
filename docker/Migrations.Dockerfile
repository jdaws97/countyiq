FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

WORKDIR /opt/pipelines

RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.6@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Migrations use the same lock as development without installing the pipeline,
# Dagster, browsers or model execution tools into the production image.
COPY pipelines/pyproject.toml pipelines/uv.lock ./
RUN uv sync --locked --only-group migrations --no-install-project && uv cache clean
ENV PATH="/opt/pipelines/.venv/bin:$PATH"

RUN groupadd --system --gid 10001 countyiq \
    && useradd --system --uid 10001 --gid countyiq --no-create-home countyiq
COPY --chown=countyiq:countyiq pipelines/alembic.ini ./
COPY --chown=countyiq:countyiq pipelines/alembic/ ./alembic/

RUN rm -f /bin/uv /usr/local/bin/pip* /usr/local/bin/wheel \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/wheel*

USER 10001:10001
CMD ["alembic", "upgrade", "head"]
