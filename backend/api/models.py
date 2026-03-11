from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

DEFAULT_BUFFER_M = 5000.0

class LatLng(BaseModel):
    lat: float
    lng: float

class RouteRequest(BaseModel):
    name: Optional[str] = "adhoc"
    start: LatLng
    end: LatLng
    buffer_m: float = Field(DEFAULT_BUFFER_M, ge=0.0, le=50000.0)
    lambda_weight: float = Field(ge=0.0, le=1.0)
    smooth_threshold: float = Field(ge=0.0, le=100.0)
    avoid_lake: bool = False
    avoid_glacier: bool = False