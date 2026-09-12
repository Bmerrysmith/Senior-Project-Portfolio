from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.schemas import Project, ProjectDetail, ProjectStatus

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/", response_model=list[Project], summary="List all projects")
def list_projects(
    status: Optional[ProjectStatus] = Query(None, description="Filter by project status"),
    store: CSVStore = Depends(get_store),
):
    return store.get_projects(status=status)


@router.get("/{project_id}", response_model=ProjectDetail, summary="Get a project with meeting and location counts")
def get_project(project_id: int, store: CSVStore = Depends(get_store)):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return {
        **project,
        "meeting_count": len(store.get_meetings(project_id=project_id)),
        "location_count": len(store.get_locations(project_id=project_id)),
    }
