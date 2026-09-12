from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.data import pin_comments_store
from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.schemas import Location, LocationDetail, LocationType

router = APIRouter(prefix="/locations", tags=["Locations"])


class PinCommentUpdate(BaseModel):
    text: str = Field(..., max_length=8000)
    updated_by: str = Field(default="admin", max_length=120)


def _require_admin(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> str:
    if not settings.admin_key:
        raise HTTPException(
            status_code=503,
            detail="Admin API is not configured (set EAGLE_ADMIN_KEY).",
        )
    if not x_admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="Invalid or missing admin key.")
    return x_admin_key


@router.get("/", response_model=list[Location], summary="List project locations")
def list_locations(
    project_id: Optional[int] = Query(None, description="Filter by project"),
    location_type: Optional[LocationType] = Query(None, description="Filter by feature type"),
    store: CSVStore = Depends(get_store),
):
    return store.get_locations(project_id=project_id, location_type=location_type)


@router.get("/{location_id}", response_model=LocationDetail, summary="Get a location with project name and meeting count")
def get_location(location_id: int, store: CSVStore = Depends(get_store)):
    location = store.get_location(location_id)
    if not location:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")

    project = store.get_project(location["project_id"])
    loc_meetings = store.get_meetings(
        project_id=location["project_id"],
        location_id=location_id,
    )
    return {
        **location,
        "project_name": project["project_name"] if project else None,
        "meeting_count": len(loc_meetings),
    }


@router.get("/admin/verify", tags=["Admin"], summary="Verify admin key")
def verify_admin(_admin: str = Depends(_require_admin)) -> dict[str, bool]:
    return {"ok": True}


@router.get("/admin/pin-comments", tags=["Admin"], summary="List all admin pin comments")
def list_pin_comments(_admin: str = Depends(_require_admin)) -> dict:
    return pin_comments_store.load_pin_comments()


@router.get("/admin/pin-comments/{location_id}", tags=["Admin"], summary="Get admin note for one pin")
def get_admin_pin_comment(location_id: int, _admin: str = Depends(_require_admin)) -> dict:
    return pin_comments_store.get_pin_comment(location_id)


@router.put("/admin/pin-comments/{location_id}", tags=["Admin"], summary="Create or update admin note for a pin")
def upsert_admin_pin_comment(
    location_id: int,
    body: PinCommentUpdate,
    _admin: str = Depends(_require_admin),
) -> dict:
    return pin_comments_store.upsert_pin_comment(
        location_id,
        body.text,
        updated_by=body.updated_by,
    )


@router.delete("/admin/pin-comments/{location_id}", tags=["Admin"], summary="Remove admin note for a pin")
def delete_admin_pin_comment(location_id: int, _admin: str = Depends(_require_admin)) -> dict[str, bool]:
    pin_comments_store.delete_pin_comment(location_id)
    return {"deleted": True}
