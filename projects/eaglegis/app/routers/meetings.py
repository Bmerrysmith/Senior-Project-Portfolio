from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.schemas import Meeting, MeetingDetail, MeetingStatus

router = APIRouter(prefix="/meetings", tags=["Meetings"])


@router.get("/", response_model=list[Meeting], summary="List meetings with optional filters")
def list_meetings(
    project_id: Optional[int] = Query(None, description="Filter by project"),
    year: Optional[int] = Query(None, ge=2015, le=2030, description="Filter by meeting year"),
    status: Optional[MeetingStatus] = Query(None, description="Filter by outcome status"),
    type_id: Optional[int] = Query(None, description="Filter by meeting type ID"),
    store: CSVStore = Depends(get_store),
):
    return store.get_meetings(
        project_id=project_id,
        year=year,
        status=status,
        type_id=type_id,
    )


@router.get("/{meeting_id}", response_model=MeetingDetail, summary="Get a meeting with project context and documents")
def get_meeting(meeting_id: int, store: CSVStore = Depends(get_store)):
    meeting = store.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

    project = store.get_project(meeting["project_id"])
    meeting_type = store.get_meeting_type(meeting["type_id"])
    documents = store.get_documents(meeting_id=meeting_id)

    return {
        **meeting,
        "project_name": project["project_name"] if project else None,
        "meeting_type_name": meeting_type["type_name"] if meeting_type else None,
        "documents": documents,
    }
