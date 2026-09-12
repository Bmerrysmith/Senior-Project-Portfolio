"""
Esri Feature Service endpoint for ArcGIS Pro.

ArcGIS Pro recognizes this as a native Feature Service layer.

To add in ArcGIS Pro:
  Map tab → Add Data → Add Data From Path → paste:
  https://your-api.railway.app/arcgis/rest/services/EagleAPI/FeatureServer/0

ArcGIS will connect live — any Supabase change is reflected on refresh.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.db import get_client

router = APIRouter(prefix="/arcgis/rest/services/EagleAPI", tags=["Feature Service"])

_SPATIAL_REF = {"wkid": 4326, "latestWkid": 4326}

_FIELDS = [
    {"name": "OBJECTID",       "type": "esriFieldTypeOID",     "alias": "OBJECTID"},
    {"name": "location_name",  "type": "esriFieldTypeString",  "alias": "Location Name"},
    {"name": "location_type",  "type": "esriFieldTypeString",  "alias": "Type"},
    {"name": "address",        "type": "esriFieldTypeString",  "alias": "Address"},
    {"name": "description",    "type": "esriFieldTypeString",  "alias": "Description"},
    {"name": "project_name",   "type": "esriFieldTypeString",  "alias": "Project"},
    {"name": "project_status", "type": "esriFieldTypeString",  "alias": "Project Status"},
]


@router.get("/FeatureServer")
def feature_server_info():
    return JSONResponse({
        "currentVersion": 10.81,
        "serviceDescription": "Estero Village Project Locations",
        "layers": [{"id": 0, "name": "Locations", "type": "Feature Layer"}],
        "spatialReference": _SPATIAL_REF,
    })


@router.get("/FeatureServer/0")
def layer_info():
    return JSONResponse({
        "currentVersion": 10.81,
        "id": 0,
        "name": "Locations",
        "type": "Feature Layer",
        "geometryType": "esriGeometryPoint",
        "spatialReference": _SPATIAL_REF,
        "fields": _FIELDS,
        "capabilities": "Query",
    })


@router.get("/FeatureServer/0/query")
def query_layer():
    try:
        raw = (
            get_client()
            .table("locations")
            .select("location_id, location_name, location_type, address, description, latitude, longitude, projects(project_name, status)")
            .order("location_id")
            .execute()
            .data
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Supabase error: {exc}") from exc

    features = []
    for row in raw:
        lat = row.get("latitude")
        lon = row.get("longitude")
        if lat is None or lon is None:
            continue
        project = row.get("projects") or {}
        features.append({
            "attributes": {
                "OBJECTID":       row["location_id"],
                "location_name":  row.get("location_name"),
                "location_type":  row.get("location_type"),
                "address":        row.get("address"),
                "description":    row.get("description"),
                "project_name":   project.get("project_name"),
                "project_status": project.get("status"),
            },
            "geometry": {"x": float(lon), "y": float(lat)},
        })

    return JSONResponse({
        "objectIdFieldName": "OBJECTID",
        "geometryType": "esriGeometryPoint",
        "spatialReference": _SPATIAL_REF,
        "fields": _FIELDS,
        "features": features,
    })
