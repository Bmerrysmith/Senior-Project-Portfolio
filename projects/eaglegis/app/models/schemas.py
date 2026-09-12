"""
Domain models mirroring the Supabase schema.
When you wire up the database, swap the dict returns in MockStore
for ORM objects — these Pydantic models stay the same.
"""
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, field_validator

# --- Constrained string types (match DB CHECK constraints) ---
DocumentType = Literal[
    "Agenda", "Staff Report", "Resolution", "Ordinance",
    "Minutes", "Presentation", "Public Notice", "Packet",
]
LocationType = Literal["Trail", "Road", "Infrastructure", "Park", "Development"]
MeetingStatus = Literal["Accepted", "Pending", "Rejected", "Tabled", "Cancelled"]
ProjectStatus = Literal["Active", "Completed", "Pending", "On Hold"]


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(BaseModel):
    project_id: int
    project_name: str
    description: Optional[str] = None
    start_year: Optional[int] = None
    status: ProjectStatus

    model_config = {"from_attributes": True}


class ProjectDetail(Project):
    meeting_count: int = 0
    location_count: int = 0


# ---------------------------------------------------------------------------
# MeetingType
# ---------------------------------------------------------------------------

class MeetingType(BaseModel):
    type_id: int
    type_name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------

class Meeting(BaseModel):
    meeting_id: int
    project_id: int
    type_id: int
    meeting_date: date
    meeting_year: int
    location: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    action_taken: Optional[str] = None
    status: MeetingStatus
    approved_by_council_date: Optional[date] = None
    doc_ref_code: Optional[str] = None
    filename: Optional[str] = None
    notes: Optional[str] = None
    location_id: Optional[int] = None

    model_config = {"from_attributes": True}


class MeetingDetail(Meeting):
    project_name: Optional[str] = None
    meeting_type_name: Optional[str] = None
    documents: list["Document"] = []


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class Location(BaseModel):
    location_id: int
    project_id: int
    location_name: str
    location_type: LocationType
    address: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    model_config = {"from_attributes": True}


class LocationDetail(Location):
    project_name: Optional[str] = None
    meeting_count: int = 0


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document(BaseModel):
    document_id: int
    meeting_id: int
    title: str
    document_type: Optional[DocumentType] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    upload_date: Optional[date] = None
    notes: Optional[str] = None
    doc_date: Optional[date] = None
    link_status: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# MeetingAction
# ---------------------------------------------------------------------------

class MeetingAction(BaseModel):
    action_id: int
    meeting_id: int
    sequence: int
    kind: str
    reference_code: Optional[str] = None
    amount_usd: Optional[float] = None
    raw_text: str

    model_config = {"from_attributes": True}


# Resolve forward reference in MeetingDetail
MeetingDetail.model_rebuild()
