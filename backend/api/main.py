from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Optional, List, Tuple
import hashlib
import traceback

import geopandas as gpd
import rasterio
from shapely.geometry import Point, box

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from urllib.parse import quote
from pydantic import BaseModel, Field
from pyproj import Transformer
import os

from backend.routing_algorithm.routing.grass_env import setup_grass_python_path
setup_grass_python_path()
import grass.script as gs

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import init_grass, run_routing_for_tour

app = FastAPI(title="Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://PederUndheim.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

_grass_lock = Lock()

WGS84 = "EPSG:4326"
NATIVE = "EPSG:25833"
_to_native = Transformer.from_crs(WGS84, NATIVE, always_xy=True)

# Config
AREAS_GPKG = Path("data_preprocessing/data_cache/outlines/study_areas.gpkg")
AREAS_LAYER = "study_areas"
DEFAULT_BUFFER_M = 5000.0

OUTPUT_ROOT = Path("data").resolve()



class LatLng(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    start: LatLng
    end: LatLng
    lambda_weight: float = Field(0.5, ge=0.0, le=1.0)
    smooth_threshold: float = Field(7.5, ge=0.0, le=100.0)
    name: Optional[str] = "adhoc"
    buffer_m: float = Field(DEFAULT_BUFFER_M, ge=0.0, le=50000.0)


def export_wgs84_geojson(native_geojson_path: str | Path) -> dict:
    gdf = gpd.read_file(native_geojson_path)
    gdf_wgs84 = gdf.to_crs(WGS84)
    return gdf_wgs84.__geo_interface__
    


def _safe_grass_name(s: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in s)
    if out and out[0].isdigit():
        out = "_" + out
    return out


def _load_area_index() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(AREAS_GPKG, layer=AREAS_LAYER)
    if gdf.crs is None:
        raise RuntimeError("Area index layer has no CRS")
    if "area_id" not in gdf.columns:
        raise RuntimeError("Area index layer must contain column 'area_id'")
    return gdf[["area_id", "geometry"]].copy()

def _areas_containing_point(gdf: gpd.GeoDataFrame, xy: Tuple[float, float]) -> List[str]:
    pt_native = Point(xy[0], xy[1])
    pt = gpd.GeoSeries([pt_native], crs=NATIVE).to_crs(gdf.crs).iloc[0]
    hits = gdf[gdf.contains(pt)]
    return sorted({str(x) for x in hits["area_id"].tolist()})

def _set_region_to_tif_union(tif_paths: List[Path]) -> None:
    if not tif_paths:
        raise ValueError("No tif paths provided to set region")

    left = bottom = float("inf")
    right = top = float("-inf")
    res = None

    for p in tif_paths:
        with rasterio.open(p) as ds:
            b = ds.bounds
            left = min(left, b.left)
            bottom = min(bottom, b.bottom)
            right = max(right, b.right)
            top = max(top, b.top)
            if res is None:
                res = ds.res[0]

    gs.run_command("g.region", n=top, s=bottom, e=right, w=left, res=res, quiet=True)



def _areas_for_bbox(gdf: gpd.GeoDataFrame, start_xy, end_xy, buffer_m) -> List[str]:
    minx = min(start_xy[0], end_xy[0]) - buffer_m
    maxx = max(start_xy[0], end_xy[0]) + buffer_m
    miny = min(start_xy[1], end_xy[1]) - buffer_m
    maxy = max(start_xy[1], end_xy[1]) + buffer_m

    bbox_native = box(minx, miny, maxx, maxy)
    bbox_poly = gpd.GeoSeries([bbox_native], crs=NATIVE).to_crs(gdf.crs).iloc[0]
    hits = gdf[gdf.intersects(bbox_poly)]
    return sorted({str(x) for x in hits["area_id"].tolist()})


def _grass_raster_exists(name: str) -> bool:
    found = gs.find_file(name, element="cell")
    return bool(found and found.get("name"))

def _raster_has_data(name: str) -> bool:
    txt = gs.read_command("r.univar", map=name, flags="g").strip().splitlines()
    d = dict(line.split("=", 1) for line in txt if "=" in line)
    return int(float(d.get("n", "0"))) > 0


def _ensure_raster_imported(tif_path: Path, raster_name: str) -> None:
    if _grass_raster_exists(raster_name):
        return

    gs.run_command(
        "r.in.gdal",
        input=str(tif_path),
        output=raster_name,
        overwrite=False,
        quiet=True,
    )


def _mosaic_name(prefix: str, area_ids: List[str]) -> str:
    key = ",".join(area_ids).encode("utf-8")
    h = hashlib.sha1(key).hexdigest()[:10]
    return f"{prefix}_mosaic_{h}"


def _build_or_get_mosaic(area_ids: List[str], *, kind: str) -> str:
    if kind not in {"cost", "dem"}:
        raise ValueError("kind must be 'cost' or 'dem'")

    # If only one area, import and return base raster name
    if len(area_ids) == 1:
        area_id = area_ids[0]
        paths, inputs = load_area(area_id)

        if kind == "cost":
            tif_path = paths.cost_surface
            base = f"cost__{_safe_grass_name(area_id)}"
        else:
            tif_path = Path(inputs["dem"])
            base = f"dem__{_safe_grass_name(area_id)}"

        _ensure_raster_imported(tif_path, base)
        return base

    mosaic = _mosaic_name(kind, area_ids)

    if _grass_raster_exists(mosaic):
        if _raster_has_data(mosaic):
            return mosaic
        # cached bad mosaic, delete it
        #gs.run_command("g.remove", type="raster", name=mosaic, flags="f", quiet=True)


    input_maps: List[str] = []
    tif_paths: List[Path] = []

    for area_id in area_ids:
        paths, inputs = load_area(area_id)

        if kind == "cost":
            tif_path = paths.cost_surface
            base = f"cost__{_safe_grass_name(area_id)}"
        else:
            tif_path = Path(inputs["dem"])
            base = f"dem__{_safe_grass_name(area_id)}"

        _ensure_raster_imported(tif_path, base)
        input_maps.append(base)
        tif_paths.append(tif_path)  # <-- THIS WAS MISSING

    # IMPORTANT: set region to cover all tifs BEFORE building mosaic
    _set_region_to_tif_union(tif_paths)

    # Build virtual mosaic (fast + robust)
    gs.run_command(
        "r.buildvrt",
        input=",".join(input_maps),
        output=mosaic,
        overwrite=True,   # allow rebuild if needed
        quiet=True,
    )

    return mosaic


def _set_region_local(mosaic_raster: str, start_xy: Tuple[float, float], end_xy: Tuple[float, float], buffer_m: float) -> None:
    # Align first
    gs.run_command("g.region", raster=mosaic_raster, quiet=True)

    # Then shrink to bbox window
    minx = min(start_xy[0], end_xy[0]) - buffer_m
    maxx = max(start_xy[0], end_xy[0]) + buffer_m
    miny = min(start_xy[1], end_xy[1]) - buffer_m
    maxy = max(start_xy[1], end_xy[1]) + buffer_m

    gs.run_command("g.region", n=maxy, s=miny, e=maxx, w=minx, quiet=True)


def _safe_rel_to_output_root(p: str | Path) -> str:
    p = Path(p).resolve()
    if OUTPUT_ROOT not in p.parents and p != OUTPUT_ROOT:
        raise HTTPException(500, "Output path outside OUTPUT_ROOT")
    return str(p.relative_to(OUTPUT_ROOT))


@app.on_event("startup")
def _startup():
    try:
        app.state.areas_gdf = _load_area_index()
        init_grass()
        app.state.ready = True
        print("API initialized OK")
    except Exception as e:
        app.state.ready = False
        print("API startup failed:", e)
        raise


@app.get("/health")
def health():
    return {"ready": bool(getattr(app.state, "ready", False))}



@app.get("/outputs/{relpath:path}")
def get_output(relpath: str):
    p = (OUTPUT_ROOT / relpath).resolve()
    if OUTPUT_ROOT not in p.parents:
        raise HTTPException(400, "Bad path")
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(str(p), media_type="image/tiff", filename=p.name)


@app.post("/route")
def route(req: RouteRequest, request: Request):

    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=500, detail="API not initialized")
    areas_gdf = app.state.areas_gdf

    sx, sy = _to_native.transform(req.start.lng, req.start.lat)
    ex, ey = _to_native.transform(req.end.lng, req.end.lat)

    start_xy = (sx, sy)
    end_xy = (ex, ey)

    try:
        with _grass_lock:
            gs.run_command(
                "g.remove",
                type="raster",
                pattern="*",
                flags="f",
                quiet=True,
            )
            bbox_ids = _areas_for_bbox(areas_gdf, start_xy, end_xy, req.buffer_m)

            start_ids = _areas_containing_point(areas_gdf, start_xy)
            end_ids = _areas_containing_point(areas_gdf, end_xy)

            if not start_ids:
                raise HTTPException(422, "Start point is outside all available areas.")
            if not end_ids:
                raise HTTPException(422, "End point is outside all available areas.")

            area_ids = sorted(set(bbox_ids) | set(start_ids) | set(end_ids))
            if not area_ids:
                raise HTTPException(422, "No areas selected for routing.")


            dem_mosaic = _build_or_get_mosaic(area_ids, kind="dem")
            cost_mosaic = _build_or_get_mosaic(area_ids, kind="cost")


            _set_region_local(cost_mosaic, start_xy, end_xy, req.buffer_m)

            # Use any one area's paths/inputs just for output folders
            # (later you can make a dedicated output area like "adhoc")
            any_paths, any_inputs = load_area(area_ids[0])

            res = run_routing_for_tour(
                paths=any_paths,
                inputs=any_inputs,
                tour_name=req.name or "adhoc",
                start_coords=start_xy,
                end_coords=end_xy,
                lambda_weight=req.lambda_weight,
                smooth_threshold=req.smooth_threshold,
                cost_surface_override=cost_mosaic,
                dem_override=dem_mosaic,
            )

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        msg = str(e)
        if "No start points found in vector map" in msg:
            raise HTTPException(422, "Start point is outside the routable area.")
        if "No end points found in vector map" in msg:
            raise HTTPException(422, "End point is outside the routable area.")
        raise HTTPException(500, f"Routing failed. {msg}")

    geojson = export_wgs84_geojson(res["path_geojson_native"])
    corridor_rel = _safe_rel_to_output_root(res["corridor_tif"])
    corridor_url = request.url_for("get_output", relpath=corridor_rel)

    return {
        "route": geojson,
        "corridor": {
            "tif_url": str(corridor_url),
        },
        "meta": {
            "area_ids": area_ids,
            "dem_mosaic_raster": dem_mosaic,
            "cost_mosaic_raster": cost_mosaic,
            "start_native": start_xy,
            "end_native": end_xy,
            "outputs": {k: str(v) for k, v in res.items()},
        },
    }
