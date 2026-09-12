"""
GIS layer endpoints.

GeoJSON endpoints for programmatic use.
CSV endpoint for ArcGIS Online live layer consumption:
  Map Viewer → Add → Add layer from URL → paste /layers/points.csv
  ArcGIS auto-detects latitude/longitude columns and renders live points.
"""
import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.geojson import GeoJSONFeatureCollection
from app.services.geojson import build_area_layer, build_point_layer, build_road_layer

router = APIRouter(prefix="/layers", tags=["GIS Layers"])

_GEO_MEDIA = "application/json"


@router.get(
    "/points",
    response_model=GeoJSONFeatureCollection,
    summary="Point layer — all project locations",
    description=(
        "Returns every project location as a GeoJSON **Point** feature. "
        "Properties include project name/status and a meeting summary suitable "
        "for ArcGIS pop-up configuration."
    ),
)
def get_point_layer(
    project_id: Optional[int] = Query(None, description="Restrict to a single project"),
    store: CSVStore = Depends(get_store),
):
    fc = build_point_layer(store, project_id=project_id)
    return Response(content=fc.model_dump_json(), media_type=_GEO_MEDIA)


@router.get(
    "/roads",
    response_model=GeoJSONFeatureCollection,
    summary="Road & trail layer — LineString features",
    description=(
        "Returns Road and Trail locations as GeoJSON **LineString** features. "
        "Geometry represents the project corridor centerline."
    ),
)
def get_road_layer(
    project_id: Optional[int] = Query(None),
    store: CSVStore = Depends(get_store),
):
    fc = build_road_layer(store, project_id=project_id)
    return Response(content=fc.model_dump_json(), media_type=_GEO_MEDIA)


@router.get(
    "/areas",
    response_model=GeoJSONFeatureCollection,
    summary="Area layer — Polygon features",
    description=(
        "Returns Park and Development locations as GeoJSON **Polygon** features. "
        "Geometry represents the approximate project boundary."
    ),
)
def get_area_layer(
    project_id: Optional[int] = Query(None),
    store: CSVStore = Depends(get_store),
):
    fc = build_area_layer(store, project_id=project_id)
    return Response(content=fc.model_dump_json(), media_type=_GEO_MEDIA)


@router.get(
    "/points.csv",
    summary="Point layer as CSV — for ArcGIS Online live layer",
    description=(
        "Returns all project locations as CSV with latitude/longitude columns. "
        "Add to ArcGIS Online via Map Viewer → Add → Add layer from URL. "
        "ArcGIS auto-detects the coordinate columns and renders live points."
    ),
)
def get_point_layer_csv(
    project_id: Optional[int] = Query(None),
    store: CSVStore = Depends(get_store),
):
    locations = store.get_locations(project_id=project_id)
    projects = {p["project_id"]: p for p in store.get_projects()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "location_id", "location_name", "location_type", "address",
        "project_name", "project_status", "meeting_count", "latitude", "longitude",
    ])
    for loc in locations:
        if loc["latitude"] is None or loc["longitude"] is None:
            continue
        proj = projects.get(loc["project_id"], {})
        meetings = store.get_meetings(project_id=loc["project_id"])
        writer.writerow([
            loc["location_id"],
            loc["location_name"],
            loc["location_type"],
            loc["address"],
            proj.get("project_name", ""),
            proj.get("status", ""),
            len(meetings),
            loc["latitude"],
            loc["longitude"],
        ])

    return Response(content=buf.getvalue(), media_type="text/csv")
