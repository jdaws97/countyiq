"""FastAPI application entry point for CountyIQ."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg2 import Error as PostgresError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.lib.auth import require_product_access
from api.lib.database import DatabasePoolExhausted, close_pool, get_cursor
from api.lib.response_types import HealthResponse
from api.lib.settings import (
    api_docs_enabled,
    cors_origins,
    county_metadata,
    restricted_distress_enabled,
    trusted_hosts,
)
from api.routes.directory import router as directory_router
from api.routes.session import router as session_router
from api.routes.delinquent import router as delinquent_router
from api.routes.feed import router as feed_router
from api.routes.case_files import router as case_files_router
from api.routes.watchspaces import router as watchspaces_router
from api.routes.layers import router as layers_router
from api.routes.municipalities import router as municipalities_router
from api.routes.ops import router as ops_router
from api.routes.owners import router as owners_router
from api.routes.parcels import router as parcels_router
from api.routes.radar import router as radar_router
from api.routes.scores import router as scores_router
from api.routes.search import router as search_router
from api.routes.stats import router as stats_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="CountyIQ API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(require_product_access)],
    docs_url="/api/docs" if api_docs_enabled() else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if api_docs_enabled() else None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=trusted_hosts(),
    www_redirect=False,
)


@app.exception_handler(DatabasePoolExhausted)
async def database_pool_exhausted(
    _request: Request,
    _exc: DatabasePoolExhausted,
) -> JSONResponse:
    """Return bounded backpressure instead of an internal-server error."""
    return JSONResponse(status_code=503, content={"detail": "database unavailable"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=[
        "Accept",
        "Content-Type",
        "Authorization",
        "X-CountyIQ-Workspace",
        "X-CountyIQ-User",
    ],
)


@app.middleware("http")
async def private_response_cache_control(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/session", "/api/watchspaces")):
        response.headers["Cache-Control"] = "no-store"
    return response


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
    except (PostgresError, DatabasePoolExhausted) as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    if not row or row["ready"] != 1:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}


@app.get("/api/meta")
def metadata() -> dict[str, str]:
    """Public product/county identity used by the county-agnostic frontend."""
    return county_metadata()


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
if restricted_distress_enabled():
    app.include_router(delinquent_router, prefix="/api/delinquent")
    app.include_router(scores_router, prefix="/api/scores")
app.include_router(radar_router, prefix="/api/radar", tags=["radar"])
app.include_router(ops_router, prefix="/api/ops")
app.include_router(feed_router, prefix="/api/feed")

app.include_router(case_files_router, prefix="/api/cases/projects")

app.include_router(watchspaces_router, prefix="/api/watchspaces")

app.include_router(session_router, prefix="/api/session")

app.include_router(directory_router, prefix="/api/directory")
from api.routes.intelligence import router as intelligence_router

app.include_router(intelligence_router, prefix="/api/intelligence")
