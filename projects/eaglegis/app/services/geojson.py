"""
GeoJSON feature-building service.

Each builder function assembles a FeatureCollection from the store,
enriching feature properties with cross-table context (project name,
meeting summary) so ArcGIS popups get everything they need from one request.
"""
from app.data.csv_store import CSVStore as MockStore
from app.models.geojson import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    LineStringGeometry,
    PointGeometry,
    PolygonGeometry,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _meeting_summary(meetings: list[dict]) -> dict:
    """Summarize a list of meeting dicts into popup-friendly properties."""
    if not meetings:
        return {
            "meeting_count": 0,
            "latest_meeting_date": None,
            "latest_meeting_status": None,
            "latest_action_taken": None,
        }
    latest = max(meetings, key=lambda m: m["meeting_date"])
    return {
        "meeting_count": len(meetings),
        "latest_meeting_date": str(latest["meeting_date"]),
        "latest_meeting_status": latest["status"],
        "latest_action_taken": latest.get("action_taken"),
    }


def _location_properties(loc: dict, project: dict, meetings: list[dict]) -> dict:
    """Shared property block used by all three layer builders."""
    return {
        "location_id": loc["location_id"],
        "location_name": loc["location_name"],
        "location_type": loc["location_type"],
        "address": loc["address"],
        "description": loc["description"],
        "project_id": loc["project_id"],
        "project_name": project.get("project_name"),
        "project_status": project.get("status"),
        **_meeting_summary(meetings),
    }


def _location_meetings(store: MockStore, loc: dict) -> list[dict]:
    """Return only the meetings that reference this specific location."""
    return store.get_meetings(
        project_id=loc["project_id"],
        location_id=loc["location_id"],
    )


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------

def build_point_layer(
    store: MockStore,
    project_id: int | None = None,
) -> GeoJSONFeatureCollection:
    """All locations with coordinates → Point features."""
    projects = {p["project_id"]: p for p in store.get_projects()}
    features: list[GeoJSONFeature] = []

    for loc in store.get_locations(project_id=project_id):
        if loc["latitude"] is None or loc["longitude"] is None:
            continue
        meetings = _location_meetings(store, loc)
        props = _location_properties(loc, projects.get(loc["project_id"], {}), meetings)
        features.append(
            GeoJSONFeature(
                id=loc["location_id"],
                geometry=PointGeometry(
                    coordinates=[float(loc["longitude"]), float(loc["latitude"])]
                ),
                properties=props,
            )
        )

    return GeoJSONFeatureCollection(
        name="Estero Project Locations",
        features=features,
    )


def build_road_layer(
    store: MockStore,
    project_id: int | None = None,
) -> GeoJSONFeatureCollection:
    """Road and Trail locations → LineString features."""
    road_types = {"Road", "Trail"}
    projects = {p["project_id"]: p for p in store.get_projects()}
    features: list[GeoJSONFeature] = []

    for loc in store.get_locations(project_id=project_id):
        if loc["location_type"] not in road_types:
            continue

        coords = store.get_road_geometry(loc["location_id"])
        if coords is None:
            # Fall back: degenerate two-point line if no geometry is registered
            if loc["latitude"] is not None and loc["longitude"] is not None:
                lon, lat = float(loc["longitude"]), float(loc["latitude"])
                coords = [[lon, lat], [lon + 0.001, lat]]
            else:
                continue

        meetings = _location_meetings(store, loc)
        props = _location_properties(loc, projects.get(loc["project_id"], {}), meetings)
        features.append(
            GeoJSONFeature(
                id=loc["location_id"],
                geometry=LineStringGeometry(coordinates=coords),
                properties=props,
            )
        )

    return GeoJSONFeatureCollection(
        name="Estero Road & Trail Corridors",
        features=features,
    )


def build_area_layer(
    store: MockStore,
    project_id: int | None = None,
) -> GeoJSONFeatureCollection:
    """Park and Development locations → Polygon features."""
    area_types = {"Park", "Development", "Infrastructure"}
    projects = {p["project_id"]: p for p in store.get_projects()}
    features: list[GeoJSONFeature] = []

    for loc in store.get_locations(project_id=project_id):
        if loc["location_type"] not in area_types:
            continue

        coords = store.get_area_geometry(loc["location_id"])
        if coords is None:
            # Fall back: small bounding box (~200 m) around the centroid point
            if loc["latitude"] is not None and loc["longitude"] is not None:
                lat, lon = float(loc["latitude"]), float(loc["longitude"])
                d = 0.002
                coords = [[[lon - d, lat - d], [lon + d, lat - d],
                            [lon + d, lat + d], [lon - d, lat + d],
                            [lon - d, lat - d]]]
            else:
                continue

        meetings = _location_meetings(store, loc)
        props = _location_properties(loc, projects.get(loc["project_id"], {}), meetings)
        features.append(
            GeoJSONFeature(
                id=loc["location_id"],
                geometry=PolygonGeometry(coordinates=coords),
                properties=props,
            )
        )

    return GeoJSONFeatureCollection(
        name="Estero Project Areas",
        features=features,
    )
