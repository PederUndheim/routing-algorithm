from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Optional

import geopandas as gpd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pyproj import Transformer
import os

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import init_grass, ensure_base_rasters, run_routing_for_tour

app = FastAPI(title="Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_grass_lock = Lock()

WGS84 = "EPSG:4326"
NATIVE = "EPSG:25833"
_to_native = Transformer.from_crs(WGS84, NATIVE, always_xy=True)

# Loaded once on startup
AREA_ID = os.environ.get("AREA_ID", "isfjorden_01")
_paths = None
_inputs = None


class LatLng(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    start: LatLng
    end: LatLng
    lambda_weight: float = Field(0.5, ge=0.0, le=1.0)
    smooth_threshold: float = Field(7.5, ge=0.0, le=100.0)
    name: Optional[str] = "adhoc"


def export_wgs84_geojson(native_geojson_path: str | Path) -> dict:
    gdf = gpd.read_file(native_geojson_path)
    gdf_wgs84 = gdf.to_crs(WGS84)
    return gdf_wgs84.__geo_interface__


@app.on_event("startup")
def _startup():
    global _paths, _inputs

    _paths, _inputs = load_area(AREA_ID)

    if not _paths.cost_surface.exists():
        raise RuntimeError(
            f"Cost surface not found at {_paths.cost_surface}. Build it first for area '{AREA_ID}'."
        )

    init_grass()

    ensure_base_rasters(
        area_id=AREA_ID,
        dem_path=_inputs["dem"],
        cost_surface_path=_paths.cost_surface,
    )


@app.post("/route")
def route(req: RouteRequest):
    if _paths is None or _inputs is None:
        raise HTTPException(status_code=500, detail="API not initialized")

    sx, sy = _to_native.transform(req.start.lng, req.start.lat)
    ex, ey = _to_native.transform(req.end.lng, req.end.lat)

    try:
        with _grass_lock:
            res = run_routing_for_tour(
                paths=_paths,
                inputs=_inputs,
                tour_name=req.name or "adhoc",
                start_coords=(sx, sy),
                end_coords=(ex, ey),
                lambda_weight=req.lambda_weight,
                smooth_threshold=req.smooth_threshold,
            )
    except Exception as e:
        msg = str(e)
        if "No start points found in vector map" in msg:
            raise HTTPException(422, "Start point is outside the cost surface area.")
        if "No end points found in vector map" in msg:
            raise HTTPException(422, "End point is outside the cost surface area.")
        raise HTTPException(500, f"Routing failed. {msg}")

    geojson = export_wgs84_geojson(res["path_geojson_native"])
    return {
        "route": geojson,
        "meta": {
            "area_id": AREA_ID,
            "start_native": (sx, sy),
            "end_native": (ex, ey),
            "outputs": {k: str(v) for k, v in res.items()},
        },
    }
