"""
Pipeline-level validation schemas.

These are stricter than ``app.models.schemas`` (which describe the API
serving contract). They:

  * coerce / parse raw CSV strings (``"null"`` -> ``None``, ``"2024"`` -> int)
  * enforce required fields (``meeting_date``, ``meeting_year``)
  * enforce FK existence against reference data (project_id, type_id, location_id)
  * enforce that ``meeting_year`` matches the year of ``meeting_date``

Validation returns a tuple ``(rows, rejects)`` where rejects carry the
original raw row plus a list of human-readable error messages so we
can surface them in the run manifest and an operator can fix the source.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.pipeline import config

NULL_TOKENS = {"", "null", "NULL", "None", "NA", "N/A"}


def _none_if_null(v: Any) -> Any:
    if isinstance(v, str) and v.strip() in NULL_TOKENS:
        return None
    return v


def _parse_int(v: Any) -> Optional[int]:
    v = _none_if_null(v)
    if v is None:
        return None
    if isinstance(v, int):
        return v
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        raise ValueError(f"not an integer: {v!r}")


def _parse_date(v: Any) -> Optional[date]:
    v = _none_if_null(v)
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, TypeError):
        raise ValueError(f"not an ISO date (YYYY-MM-DD): {v!r}")


def _parse_float(v: Any) -> Optional[float]:
    v = _none_if_null(v)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        raise ValueError(f"not a float: {v!r}")


def _reference_module():
    # Lazy import avoids circular import when reference.py validates locations.
    from app.pipeline import reference
    return reference


def in_estero_bbox(lat: float, lon: float) -> bool:
    bbox = config.ESTERO_BBOX
    return (
        bbox["min_lat"] <= lat <= bbox["max_lat"]
        and bbox["min_lon"] <= lon <= bbox["max_lon"]
    )


def validate_coordinates(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude out of range: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"longitude out of range: {lon}")
    if not in_estero_bbox(lat, lon):
        raise ValueError(
            f"coordinates outside ESTERO_BBOX: lat={lat}, lon={lon}"
        )


class MeetingRow(BaseModel):
    """A validated, typed row for app/data/silver/meetings.csv."""

    model_config = {"str_strip_whitespace": True}

    meeting_id: int
    project_id: int
    type_id: int
    meeting_date: date
    meeting_year: int
    location: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    action_taken: Optional[str] = None
    status: str = "Accepted"
    approved_by_council_date: Optional[date] = None
    doc_ref_code: Optional[str] = None
    filename: Optional[str] = None
    notes: Optional[str] = None
    location_id: Optional[int] = None

    @field_validator(
        "meeting_id", "project_id", "type_id", "meeting_year", "location_id",
        mode="before",
    )
    @classmethod
    def _ints(cls, v: Any) -> Any:
        return _parse_int(v)

    @field_validator("meeting_date", "approved_by_council_date", mode="before")
    @classmethod
    def _dates(cls, v: Any) -> Any:
        return _parse_date(v)

    @field_validator(
        "location", "start_time", "end_time", "action_taken",
        "doc_ref_code", "filename", "notes",
        mode="before",
    )
    @classmethod
    def _strs(cls, v: Any) -> Any:
        return _none_if_null(v)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: Any) -> Any:
        v = _none_if_null(v)
        return v if v else "Accepted"

    @model_validator(mode="after")
    def _check(self) -> "MeetingRow":
        reference = _reference_module()
        if self.meeting_year != self.meeting_date.year:
            raise ValueError(
                f"meeting_year {self.meeting_year} does not match "
                f"meeting_date year {self.meeting_date.year}"
            )
        if self.project_id not in reference.project_ids():
            raise ValueError(f"unknown project_id={self.project_id}")
        if self.type_id not in reference.meeting_type_ids():
            raise ValueError(f"unknown type_id={self.type_id}")
        if self.location_id is not None and self.location_id not in reference.location_ids():
            raise ValueError(f"unknown location_id={self.location_id}")
        return self


class LocationRow(BaseModel):
    """A validated row for app/data/reference/locations.yaml."""

    model_config = {"str_strip_whitespace": True}

    location_id: int
    project_id: int
    location_name: str
    location_type: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    latitude: float
    longitude: float

    @field_validator("location_id", "project_id", mode="before")
    @classmethod
    def _ints(cls, v: Any) -> Any:
        return _parse_int(v)

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def _floats(cls, v: Any) -> Any:
        return _parse_float(v)

    @field_validator("location_name", mode="before")
    @classmethod
    def _name(cls, v: Any) -> Any:
        v = _none_if_null(v)
        if not v:
            raise ValueError("location_name is required")
        return v

    @field_validator("location_type", "address", "description", mode="before")
    @classmethod
    def _strs(cls, v: Any) -> Any:
        return _none_if_null(v)

    @model_validator(mode="after")
    def _check(self) -> "LocationRow":
        validate_coordinates(self.latitude, self.longitude)
        return self


class DocumentRow(BaseModel):
    """A validated, typed row for app/data/silver/documents.csv."""

    model_config = {"str_strip_whitespace": True}

    document_id: int
    meeting_id: int
    title: str = Field(default="Untitled")
    file_url: Optional[str] = None
    doc_date: Optional[date] = None
    meeting_date: Optional[date] = None
    meeting_year: Optional[int] = None
    status: Optional[str] = None
    type_name: Optional[str] = None
    link_status: Optional[str] = None

    @field_validator("document_id", "meeting_id", "meeting_year", mode="before")
    @classmethod
    def _ints(cls, v: Any) -> Any:
        return _parse_int(v)

    @field_validator("doc_date", "meeting_date", mode="before")
    @classmethod
    def _dates(cls, v: Any) -> Any:
        return _parse_date(v)

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, v: Any) -> Any:
        v = _none_if_null(v)
        return v if v else "Untitled"

    @field_validator("file_url", "status", "type_name", "link_status", mode="before")
    @classmethod
    def _strs(cls, v: Any) -> Any:
        return _none_if_null(v)


def validate_rows(
    raw_rows: list[dict],
    model: type[BaseModel],
) -> tuple[list[BaseModel], list[dict]]:
    """
    Validate a list of raw dict rows against a Pydantic model.

    Returns ``(valid_rows, rejects)`` where each reject is::

        {"row": <original dict>, "errors": ["<human msg>", ...]}
    """
    valid: list[BaseModel] = []
    rejects: list[dict] = []
    for raw in raw_rows:
        try:
            valid.append(model.model_validate(raw))
        except ValidationError as exc:
            rejects.append({
                "row": raw,
                "errors": [
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()
                ],
            })
        except ValueError as exc:
            rejects.append({"row": raw, "errors": [str(exc)]})
    return valid, rejects
