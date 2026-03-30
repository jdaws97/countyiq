"""FastAPI application entry point for CountyIQ."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.scout import router as scout_router
from api.routes.stats import router as stats_router
from api.routes.layers import router as layers_router
from api.routes.municipalities import router as municipalities_router
from api.routes.parcels import router as parcels_router
from api.routes.search import router as search_router
from api.routes.delinquent import router as delinquent_router
from api.routes.licenses import router as licenses_router
from api.routes.projects import router as projects_router
from api.routes.ops import router as ops_router

app = FastAPI(
    title="CountyIQ API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Minimal health route for Lambda and smoke tests."""
    return {"status": "ok"}


app.include_router(scout_router, prefix="/api/scout")
app.include_router(stats_router, prefix="/api/stats")
app.include_router(layers_router, prefix="/api/layers")
app.include_router(municipalities_router, prefix="/api/municipalities")
app.include_router(parcels_router, prefix="/api/parcels")
app.include_router(search_router, prefix="/api/search")
app.include_router(delinquent_router, prefix="/api/delinquent")
app.include_router(licenses_router, prefix="/api/licenses")
app.include_router(projects_router, prefix="/api/projects")
app.include_router(ops_router, prefix="/api/ops")
