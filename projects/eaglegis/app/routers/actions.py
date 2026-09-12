from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.schemas import MeetingAction

router = APIRouter(prefix="/actions", tags=["Meeting Actions"])


@router.get("/", response_model=list[MeetingAction], summary="List structured meeting actions")
def list_actions(
    meeting_id: Optional[int] = Query(None, description="Filter by meeting id"),
    kind: Optional[str] = Query(None, description='Filter by kind, e.g. "Approved Contract"'),
    store: CSVStore = Depends(get_store),
):
    return store.get_actions(meeting_id=meeting_id, kind=kind)


@router.get("/{action_id}", response_model=MeetingAction)
def get_action(action_id: int, store: CSVStore = Depends(get_store)):
    action = store.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    return action
