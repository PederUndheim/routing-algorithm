from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

DEFAULT_BUFFER_M = 5000.0

class LatLng(BaseModel):
    lat: float
    lng: float


TrackInfluenceMode = Literal["off", "forest_only", "balanced", "strong"]
CorridorMode = Literal["conservative", "balanced", "explorative"]

class RouteRequest(BaseModel):
    name: Optional[str] = "adhoc"
    start: LatLng
    stops: list[LatLng] = Field(default_factory=list, max_length=3)
    end: LatLng
    buffer_m: float = Field(DEFAULT_BUFFER_M, ge=0.0, le=50000.0)
    lambda_weight: float = Field(ge=0.0, le=1.0)
    smooth_threshold: float = Field(ge=0.0, le=100.0)
    avoid_lake: bool = False
    avoid_glacier: bool = False
    track_influence_mode: TrackInfluenceMode = "balanced"
    corridor_mode: CorridorMode = "balanced"