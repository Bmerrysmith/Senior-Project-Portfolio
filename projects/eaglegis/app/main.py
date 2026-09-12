from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from app.config import settings
from app.routers import (
    documents,
    export,
    feature_service,
    layers,
    locations,
    meeting_types,
    meetings,
    projects,
)

app = FastAPI(
    title=settings.app_name,
    description=(
        "Serves live CSV exports from Supabase for ArcGIS geocoding plus a "
        "CSV/silver-backed read-API (meetings, projects, documents, locations, "
        "meeting types) and GeoJSON GIS layers. An elderly-accessible interactive "
        "map dashboard is served at /dashboard."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Live Supabase-backed routers (unchanged behaviour)
app.include_router(export.router, prefix=settings.api_v1_prefix)
app.include_router(feature_service.router)

# CSV/silver-backed read-API + GeoJSON GIS layers
app.include_router(meetings.router, prefix=settings.api_v1_prefix)
app.include_router(projects.router, prefix=settings.api_v1_prefix)
app.include_router(documents.router, prefix=settings.api_v1_prefix)
app.include_router(meeting_types.router, prefix=settings.api_v1_prefix)
app.include_router(locations.router, prefix=settings.api_v1_prefix)
app.include_router(layers.router, prefix=settings.api_v1_prefix)

_DASHBOARD_FILE = Path(__file__).parent / "static" / "dashboard.html"


@app.get("/", tags=["System"], include_in_schema=False)
def root():
    p = settings.api_v1_prefix
    return {
        "api": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "dashboard": "/dashboard",
        "export": {
            "projects_csv":      f"{p}/export/projects.csv",
            "meeting_types_csv": f"{p}/export/meeting_types.csv",
            "meetings_csv":      f"{p}/export/meetings.csv",
            "locations_csv":     f"{p}/export/locations.csv",
            "documents_csv":     f"{p}/export/documents.csv",
        },
        "read_api": {
            "meetings":      f"{p}/meetings",
            "projects":      f"{p}/projects",
            "documents":     f"{p}/documents",
            "meeting_types": f"{p}/meeting-types",
            "locations":     f"{p}/locations",
        },
        "gis_layers": {
            "points":      f"{p}/layers/points",
            "roads":       f"{p}/layers/roads",
            "areas":       f"{p}/layers/areas",
            "points_csv":  f"{p}/layers/points.csv",
        },
    }


@app.get("/dashboard", tags=["System"], include_in_schema=False, response_class=HTMLResponse)
def dashboard():
    """Elderly-accessible interactive map dashboard (single self-contained page)."""
    if not _DASHBOARD_FILE.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return HTMLResponse(_DASHBOARD_FILE.read_text(encoding="utf-8"))


@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok"}
