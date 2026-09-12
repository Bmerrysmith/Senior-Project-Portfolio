"""
RFC 7946-compliant GeoJSON response models.
Geometry is a discriminated union keyed on the 'type' field,
which gives clean serialization and fast Pydantic validation.
"""
from typing import Annotated, Any, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: list[float]  # [lon, lat]


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]  # [[lon, lat], ...]


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]]  # [[[lon, lat], ...]] — outer ring first


# Discriminated union so Pydantic selects the right model without ambiguity
Geometry = Annotated[
    Union[PointGeometry, LineStringGeometry, PolygonGeometry],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Feature and FeatureCollection
# ---------------------------------------------------------------------------

class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: Optional[int] = None
    geometry: Geometry
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    name: Optional[str] = None
    features: list[GeoJSONFeature]
