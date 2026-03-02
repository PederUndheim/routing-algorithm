from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

DEFAULT_BUFFER_M = 5000.0

class LatLng(BaseModel):
    lat: float
    lng: float

class RouteRequest(BaseModel):
    start: LatLng
    end: LatLng
    lambda_weight: float 
    smooth_threshold: float
    name: Optional[str] = "adhoc"
    buffer_m: float = Field(DEFAULT_BUFFER_M, ge=0.0, le=50000.0)