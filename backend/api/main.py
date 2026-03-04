from __future__ import annotations

import os
import uuid
import traceback
import geopandas as gpd
import shutil
from pathlib import Path
from threading import Lock
from typing import List, Tuple
from shapely.geometry import Point, box

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from pyproj import Transformer

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import init_grass, run_routing_for_tour
from backend.routing_algorithm.routing.grass_env import setup_grass_python_path
from backend.api.models import RouteRequest
from backend.api.deps import get_corridor_storage
from backend.api.runtime import get_settings
from backend.api.mosaic_service import build_or_get_mosaic, set_region_local
from backend.api.corridor_to_png import warp_tif_to_3857, corridor_tif_3857_to_png, tif_3857_bounds_wgs84

setup_grass_python_path()
import grass.script as gs



app = FastAPI(title="Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://pederundheim.github.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

_grass_lock = Lock()

WGS84 = "EPSG:4326"
NATIVE = "EPSG:25833"
_to_native = Transformer.from_crs(WGS84, NATIVE, always_xy=True)

AREAS_GPKG = Path("data_preprocessing/data_cache/outlines/study_areas.gpkg")
AREAS_LAYER = "study_areas"

def _get_output_root() -> Path:
    if get_settings().env == "prod":
        return Path(os.getenv("OUTPUT_ROOT", "/tmp/routing_outputs")).resolve()

    override = os.getenv("OUTPUT_ROOT")
    if override:
        return Path(override).resolve()

    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "data" ).resolve()


def _export_wgs84_geojson(native_geojson_path: str | Path) -> dict:
    gdf = gpd.read_file(native_geojson_path)
    return gdf.to_crs(WGS84).__geo_interface__


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


def _areas_for_bbox(gdf: gpd.GeoDataFrame, start_xy, end_xy, buffer_m) -> List[str]:
    minx = min(start_xy[0], end_xy[0]) - buffer_m
    maxx = max(start_xy[0], end_xy[0]) + buffer_m
    miny = min(start_xy[1], end_xy[1]) - buffer_m
    maxy = max(start_xy[1], end_xy[1]) + buffer_m

    bbox_native = box(minx, miny, maxx, maxy)
    bbox_poly = gpd.GeoSeries([bbox_native], crs=NATIVE).to_crs(gdf.crs).iloc[0]
    hits = gdf[gdf.intersects(bbox_poly)]
    return sorted({str(x) for x in hits["area_id"].tolist()})



@app.on_event("startup")
def _startup():
    try:
        app.state.output_root = _get_output_root()
        app.state.output_root.mkdir(parents=True, exist_ok=True)
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
    OUTPUT_ROOT =  _get_output_root()
    if get_settings().env != "local":
        raise HTTPException(403, "Output retrieval is only allowed in local environment")
    p = (OUTPUT_ROOT / relpath).resolve()
    if OUTPUT_ROOT not in p.parents:
        raise HTTPException(400, "Bad path")
    if not p.exists():
        raise HTTPException(404, "Not found")

    resp = FileResponse(str(p), filename=p.name)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.delete("/runs_output/{run_id}")
def delete_run(run_id: str, request: Request):
    storage = get_corridor_storage(request)

    try:
        storage.delete_run(run_id=run_id)
    except Exception as e:
        return {"ok": False, "run_id": run_id, "error": str(e)}

    return {"ok": True, "run_id": run_id}


@app.post("/route")
def route(req: RouteRequest, request: Request):
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=500, detail="API not initialized")

    areas_gdf: gpd.GeoDataFrame = app.state.areas_gdf

    sx, sy = _to_native.transform(req.start.lng, req.start.lat)
    ex, ey = _to_native.transform(req.end.lng, req.end.lat)

    start_xy = (sx, sy)
    end_xy = (ex, ey)

    try:
        with _grass_lock:
            # NOTE: wipes all rasters in the current mapset
            gs.run_command("g.remove", type="raster", pattern="*", flags="f", quiet=True)

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

            dem_mosaic = build_or_get_mosaic(area_ids, kind="dem")
            cost_mosaic = build_or_get_mosaic(area_ids, kind="cost")

            set_region_local(cost_mosaic, start_xy, end_xy, req.buffer_m)

            any_paths, any_inputs = load_area(area_ids[0])

            run_id = uuid.uuid4().hex

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
                output_mode="run",
                run_id=run_id,
                output_root=request.app.state.output_root,
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

    # Route GeoJSON (WGS84)
    geojson = _export_wgs84_geojson(res["path_geojson_native"])

    # Corridor outputs
    corridor_tif = Path(res["corridor_tif"])
    corridor_dir = corridor_tif.parent

    corridor_tif_3857 = corridor_dir / "corridor_3857.tif"
    corridor_png = corridor_dir / "corridor.png"

    # 1) generate png from tif
    warp_tif_to_3857(corridor_tif, corridor_tif_3857)
    corridor_tif_3857_to_png(corridor_tif_3857, corridor_png)
    bounds = tif_3857_bounds_wgs84(corridor_tif_3857)

    # 2) store
    storage = get_corridor_storage(request)

    png_url = storage.put_corridor_png(run_id=run_id, png_path=corridor_png)

    tif_url = None
    if get_settings().env == "local":
        tif_url = storage.put_corridor_tif(run_id=run_id, tif_path=corridor_tif)
    else:
        # skipping uploading tif in prod mode
        # tif_url = storage.put_corridor_tif(run_id=run_id, tif_path=corridor_tif)
        tif_url = None
    if get_settings().env == "prod":
        run_dir = (request.app.state.output_root / "runs_output" / run_id)
        shutil.rmtree(run_dir, ignore_errors=True)

    return {
        "run_id": run_id,
        "route": geojson,
        "corridor": {
            "png_url": png_url,
            "bounds": bounds,
            "tif_url": tif_url,  # optional
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