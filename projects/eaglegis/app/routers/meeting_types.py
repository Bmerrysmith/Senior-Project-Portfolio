from fastapi import APIRouter, Depends, HTTPException
from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.schemas import MeetingType

router = APIRouter(prefix="/meeting-types", tags=["Meeting Types"])


@router.get("/", response_model=list[MeetingType], summary="List all meeting types")
def list_meeting_types(store: CSVStore = Depends(get_store)):
    return store.get_meeting_types()


@router.get("/{type_id}", response_model=MeetingType)
def get_meeting_type(type_id: int, store: CSVStore = Depends(get_store)):
    mt = store.get_meeting_type(type_id)
    if not mt:
        raise HTTPException(status_code=404, detail=f"Meeting type {type_id} not found")
    return mt
