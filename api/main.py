"""FastAPI application entry point for CountyIQ."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import Error as PostgresError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.lib.database import close_pool, get_cursor
from api.lib.response_types import HealthResponse
from api.lib.settings import (
    api_docs_enabled,
    county_metadata,
    cors_origins,
    restricted_distress_enabled,
    trusted_hosts,
)
from api.routes.delinquent import router as delinquent_router
from api.routes.feed import router as feed_router
from api.routes.layers import router as layers_router
from api.routes.licenses import router as licenses_router
from api.routes.municipalities import router as municipalities_router
from api.routes.ops import router as ops_router
from api.routes.owners import router as owners_router
from api.routes.parcels import router as parcels_router
from api.routes.projects import router as projects_router
from api.routes.radar import router as radar_router
from api.routes.scores import router as scores_router
from api.routes.scout import router as scout_router
from api.routes.search import router as search_router
from api.routes.stats import router as stats_router

load_dotenv()  # Local development only; production Compose passes an allowlist.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="CountyIQ API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if api_docs_enabled() else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if api_docs_enabled() else None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=trusted_hosts(),
    www_redirect=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


@app.get("/api/health")
def health() -> HealthResponse:
    """Process liveness check that does not depend on downstream services."""
    return {"status": "ok"}


@app.get("/api/ready")
def readiness() -> HealthResponse:
    """Return success only when the API can query its production dependency."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1 AS ready")
            row = cur.fetchone()
    except PostgresError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    if not row or row["ready"] != 1:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}


@app.get("/api/meta")
def metadata() -> dict[str, str]:
    """Public product/county identity used by the county-agnostic frontend."""
    return county_metadata()


app.include_router(scout_router, prefix="/api/scout")
app.include_router(stats_router, prefix="/api/stats")
app.include_router(layers_router, prefix="/api/layers")
app.include_router(municipalities_router, prefix="/api/municipalities")
app.include_router(parcels_router, prefix="/api/parcels")
app.include_router(search_router, prefix="/api/search")
app.include_router(owners_router, prefix="/api/owners")
# Entity case files deliberately reuse the stable public.owners identity
# space.  The alias keeps old owner URLs working without creating a second
# entity ID system.
app.include_router(owners_router, prefix="/api/entities")
app.include_router(licenses_router, prefix="/api/licenses")
app.include_router(projects_router, prefix="/api/projects")
if restricted_distress_enabled():
    app.include_router(delinquent_router, prefix="/api/delinquent")
    app.include_router(scores_router, prefix="/api/scores")
app.include_router(radar_router, prefix="/api/radar", tags=["radar"])
app.include_router(ops_router, prefix="/api/ops")
app.include_router(feed_router, prefix="/api/feed")
