from __future__ import annotations

import os
import json
import geopandas as gpd
import gpxpy
import gpxpy.gpx
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from pyproj import Transformer

from backend.routing_algorithm.routing.core import init_grass
from backend.api.models import RouteRequest
from backend.api.storage_deps import get_corridor_storage
from backend.api.env_settings import get_settings
from backend.api.route_service import run_route_request
from backend.api.corridor_to_png import warp_tif_to_3857, corridor_tif_3857_to_png, tif_3857_bounds_wgs84

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
    if gdf.crs is None:
        gdf = gdf.set_crs(NATIVE, allow_override=True)
    else:
        minx, miny, maxx, maxy = gdf.total_bounds
        looks_like_lonlat = (
            -180.0 <= minx <= 180.0
            and -180.0 <= maxx <= 180.0
            and -90.0 <= miny <= 90.0
            and -90.0 <= maxy <= 90.0
        )
        if gdf.crs.to_string() == WGS84 and not looks_like_lonlat:
            gdf = gdf.set_crs(NATIVE, allow_override=True)
    return gdf.to_crs(WGS84).__geo_interface__


def _geojson_to_gpx(geojson_dict: dict) -> str:
    """Convert GeoJSON LineString to GPX format."""
    gpx = gpxpy.gpx.GPX()
    
    try:
        # Extract coordinates from GeoJSON
        features = geojson_dict.get("features", [])
        if not features:
            raise ValueError("No features in GeoJSON")
        
        # Create track segment
        track = gpxpy.gpx.GPXTrack()
        segment = gpxpy.gpx.GPXTrackSegment()

        for feature in features:
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])

            if geom_type == "LineString":
                lines = [coords]
            elif geom_type == "MultiLineString":
                lines = coords
            else:
                continue

            for line in lines:
                for coord in line:
                    if len(coord) >= 2:
                        lng, lat = coord[0], coord[1]
                        segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lng))
        
        if segment.points:
            track.segments.append(segment)
            gpx.tracks.append(track)
        
        return gpx.to_xml()
    except Exception as e:
        raise ValueError(f"Error converting GeoJSON to GPX: {str(e)}")


def _load_area_index() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(AREAS_GPKG, layer=AREAS_LAYER)
    if gdf.crs is None:
        raise RuntimeError("Area index layer has no CRS")
    if "area_id" not in gdf.columns:
        raise RuntimeError("Area index layer must contain column 'area_id'")
    return gdf[["area_id", "geometry"]].copy()



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
    stop_xy = [
        _to_native.transform(stop.lng, stop.lat)
        for stop in req.stops
    ]

    start_xy = (sx, sy)
    end_xy = (ex, ey)
    all_points_xy = [start_xy, *stop_xy, end_xy]

    route_ctx = run_route_request(
        req=req,
        areas_gdf=areas_gdf,
        all_points_xy=all_points_xy,
        start_xy=start_xy,
        end_xy=end_xy,
        output_root=request.app.state.output_root,
        grass_lock=_grass_lock,
    )

    run_id = route_ctx["run_id"]
    res = route_ctx["res"]
    area_ids = route_ctx["area_ids"]
    dem_mosaic = route_ctx["dem_mosaic"]
    cost_mosaic = route_ctx["cost_mosaic"]

    # Route GeoJSON (WGS84)
    geojson = _export_wgs84_geojson(res["path_geojson_native"])

    # Persist route artifacts so downloads work in prod across replicas/restarts.
    path_geojson_native = Path(res["path_geojson_native"])
    route_dir = path_geojson_native.parent
    route_geojson_wgs84_path = route_dir / "route.geojson"
    route_gpx_path = route_dir / "route.gpx"

    route_geojson_wgs84_path.write_text(json.dumps(geojson), encoding="utf-8")
    route_gpx_path.write_text(_geojson_to_gpx(geojson), encoding="utf-8")

    # Corridor outputs
    corridor_tifs = {
        mode: Path(path_str)
        for mode, path_str in res.get("corridor_tifs", {}).items()
    }
    selected_mode = req.corridor_mode

    corridor_png_urls: dict[str, str] = {}
    corridor_tif_urls: dict[str, str | None] = {}
    bounds = None

    # 1) generate all png variants from their tif outputs
    for mode, corridor_tif in corridor_tifs.items():
        corridor_dir = corridor_tif.parent
        corridor_tif_3857 = corridor_dir / f"corridor_{mode}_3857.tif"
        corridor_png = corridor_dir / f"corridor_{mode}.png"

        warp_tif_to_3857(corridor_tif, corridor_tif_3857)
        corridor_tif_3857_to_png(corridor_tif_3857, corridor_png)

        if bounds is None:
            bounds = tif_3857_bounds_wgs84(corridor_tif_3857)

        corridor_png_urls[mode] = str(corridor_png)

    # 2) store
    storage = get_corridor_storage(request)

    corridor_png_urls = {
        mode: storage.put_corridor_png(run_id=run_id, png_path=Path(png_path))
        for mode, png_path in corridor_png_urls.items()
    }
    route_geojson_url = storage.put_route_geojson(
        run_id=run_id,
        geojson_path=route_geojson_wgs84_path,
    )
    route_gpx_url = storage.put_route_gpx(
        run_id=run_id,
        gpx_path=route_gpx_path,
    )

    if get_settings().env == "local":
        corridor_tif_urls = {
            mode: storage.put_corridor_tif(run_id=run_id, tif_path=corridor_tif)
            for mode, corridor_tif in corridor_tifs.items()
        }
    else:
        corridor_tif_urls = {mode: None for mode in corridor_tifs}


    return {
        "run_id": run_id,
        "route": geojson,
        "corridor": {
            "mode": selected_mode,
            "png_url": corridor_png_urls.get(selected_mode),
            "png_urls": corridor_png_urls,
            "bounds": bounds,
            "tif_url": corridor_tif_urls.get(selected_mode),
            "tif_urls": corridor_tif_urls,
        },
        "downloads": {
            "geojson_url": route_geojson_url,
            "gpx_url": route_gpx_url,
        },
        "meta": {
            "area_ids": area_ids,
            "dem_mosaic_raster": dem_mosaic,
            "cost_mosaic_raster": cost_mosaic,
            "start_native": start_xy,
            "end_native": end_xy,
            "selected_corridor_mode": selected_mode,
            "outputs": {k: str(v) for k, v in res.items()},
        },
    }


@app.get("/runs_output/{run_id}/route.gpx")
def download_route_gpx(run_id: str, request: Request):
    """Download route as GPX file."""
    try:
        run_dir = request.app.state.output_root / "runs_output" / run_id / "route"
        path_gpx = run_dir / "route.gpx"

        if path_gpx.exists():
            return FileResponse(
                path=str(path_gpx),
                media_type="application/gpx+xml",
                filename="route.gpx",
            )

        # Backward compatibility: older runs may only have native path.geojson.
        path_geojson_native = run_dir / "path.geojson"
        if path_geojson_native.exists():
            geojson_dict = _export_wgs84_geojson(path_geojson_native)
            gpx_content = _geojson_to_gpx(geojson_dict)
            return Response(
                content=gpx_content,
                media_type="application/gpx+xml",
                headers={"Content-Disposition": "attachment; filename=route.gpx"},
            )

        # Prod fallback for clients still calling this endpoint.
        if get_settings().env == "prod":
            storage = get_corridor_storage(request)
            return RedirectResponse(storage.get_route_gpx_url(run_id=run_id), status_code=307)

        raise HTTPException(404, f"Route GPX not found for run_id={run_id}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in route.gpx endpoint: {str(e)}")
        raise HTTPException(500, f"Failed to generate GPX: {str(e)}")


@app.get("/runs_output/{run_id}/route.geojson")
def download_route_geojson(run_id: str, request: Request):
    """Download route as GeoJSON file in WGS84."""
    try:
        run_dir = request.app.state.output_root / "runs_output" / run_id / "route"
        path_geojson_wgs84 = run_dir / "route.geojson"

        if path_geojson_wgs84.exists():
            return FileResponse(
                path=str(path_geojson_wgs84),
                media_type="application/geo+json",
                filename="route.geojson",
            )

        # Backward compatibility: older runs may only have native path.geojson.
        path_geojson_native = run_dir / "path.geojson"
        if path_geojson_native.exists():
            geojson_dict = _export_wgs84_geojson(path_geojson_native)
            response = JSONResponse(geojson_dict)
            response.headers["Content-Disposition"] = "attachment; filename=route.geojson"
            return response

        # Prod fallback for clients still calling this endpoint.
        if get_settings().env == "prod":
            storage = get_corridor_storage(request)
            return RedirectResponse(storage.get_route_geojson_url(run_id=run_id), status_code=307)

        raise HTTPException(404, f"Route GeoJSON not found for run_id={run_id}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in route.geojson endpoint: {str(e)}")
        raise HTTPException(500, f"Failed to retrieve GeoJSON: {str(e)}")