"""
CSV export endpoints for ArcGIS — one per Supabase table.

All endpoints query Supabase live on every request.
No caching — changes in Supabase are reflected immediately.

Endpoints:
  GET /export/projects.csv
  GET /export/meeting_types.csv
  GET /export/meetings.csv
  GET /export/locations.csv
  GET /export/documents.csv
"""
import csv
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.db import get_client

router = APIRouter(prefix="/export", tags=["Export"])


def _csv_response(rows: list[dict], filename: str) -> Response:
    """Generic helper — writes any list of flat dicts to CSV."""
    if not rows:
        return Response(content="", media_type="text/csv")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


def _query(table: str, select: str = "*", order: str | None = None):
    """Run a Supabase select and raise a clean 502 on failure."""
    try:
        q = get_client().table(table).select(select)
        if order:
            q = q.order(order)
        return q.execute().data
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Supabase error: {exc}") from exc


@router.get("/projects.csv", summary="Export projects table")
def export_projects():
    return _csv_response(_query("projects"), "projects.csv")


@router.get("/meeting_types.csv", summary="Export meeting_types table")
def export_meeting_types():
    return _csv_response(_query("meeting_types"), "meeting_types.csv")


@router.get("/meetings.csv", summary="Export meetings table")
def export_meetings():
    return _csv_response(_query("meetings"), "meetings.csv")


@router.get("/locations.csv", summary="Export locations table with project info")
def export_locations():
    raw = _query(
        "locations",
        select="location_id, location_name, location_type, address, description, latitude, longitude, projects(project_name, status)",
        order="location_id",
    )
    rows = []
    for row in raw:
        project = row.pop("projects") or {}
        rows.append({
            **row,
            "project_name": project.get("project_name"),
            "project_status": project.get("status"),
        })
    return _csv_response(rows, "locations.csv")


@router.get("/documents.csv", summary="Export documents table")
def export_documents():
    return _csv_response(_query("documents"), "documents.csv")
