FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.6@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project && uv cache clean

RUN groupadd --system --gid 10001 countyiq \
    && useradd --system --uid 10001 --gid countyiq --no-create-home countyiq

COPY --chown=countyiq:countyiq api/main.py ./api/main.py
COPY --chown=countyiq:countyiq api/lib/ ./api/lib/
COPY --chown=countyiq:countyiq api/routes/ ./api/routes/

# Build tooling is not part of the runtime contract. Removing it also removes
# vendored archive/wheel parsers that would otherwise expand the attack surface.
RUN rm -f /bin/uv /bin/uvx /usr/local/bin/pip* /usr/local/bin/wheel \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/wheel*

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8000/api/ready || exit 1

CMD ["/app/.venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--no-server-header"]
