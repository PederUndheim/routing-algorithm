from __future__ import annotations

import json
import os
import traceback
import secrets
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import List, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import geopandas as gpd
import numpy as np
import rasterio
from fastapi import HTTPException
from shapely.geometry import Point, box

from backend import config
from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import run_routing_for_tour
from backend.routing_algorithm.routing.grass_env import setup_grass_python_path
from backend.api.models import RouteRequest
from backend.routing_algorithm.routing.grass_mosaic import build_or_get_mosaic
from backend.routing_algorithm.routing.cost_surface_request import compose_cost_surface_for_request

setup_grass_python_path()
import grass.script as gs


NATIVE = "EPSG:25833"

try:
    RUN_ID_TIMEZONE = ZoneInfo("Europe/Oslo")
except ZoneInfoNotFoundError:
    RUN_ID_TIMEZONE = timezone.utc


def _new_run_id() -> str:
    ts = datetime.now(RUN_ID_TIMEZONE).strftime("%d%m%Y_%H%M%S")
    suffix = secrets.token_hex(2)
    return f"{ts}_{suffix}"


def _areas_containing_point(gdf: gpd.GeoDataFrame, xy: Tuple[float, float]) -> List[str]:
    pt_native = Point(xy[0], xy[1])
    pt = gpd.GeoSeries([pt_native], crs=NATIVE).to_crs(gdf.crs).iloc[0]
    hits = gdf[gdf.contains(pt)]
    return sorted({str(x) for x in hits["area_id"].tolist()})


def _areas_for_points_bbox(gdf: gpd.GeoDataFrame, points_xy: List[Tuple[float, float]], buffer_m: float) -> List[str]:
    xs = [point[0] for point in points_xy]
    ys = [point[1] for point in points_xy]
    bbox_native = box(min(xs) - buffer_m, min(ys) - buffer_m, max(xs) + buffer_m, max(ys) + buffer_m)
    bbox_poly = gpd.GeoSeries([bbox_native], crs=NATIVE).to_crs(gdf.crs).iloc[0]
    hits = gdf[gdf.intersects(bbox_poly)]
    return sorted({str(x) for x in hits["area_id"].tolist()})


def _set_region_for_points(mosaic_raster: str, points_xy: List[Tuple[float, float]], buffer_m: float) -> None:
    gs.run_command("g.region", raster=mosaic_raster, quiet=True)
    xs = [point[0] for point in points_xy]
    ys = [point[1] for point in points_xy]
    gs.run_command(
        "g.region",
        n=max(ys) + buffer_m,
        s=min(ys) - buffer_m,
        e=max(xs) + buffer_m,
        w=min(xs) - buffer_m,
        quiet=True,
    )


def _merge_native_route_geojson(paths: List[Path], dst_path: Path) -> Path:
    features: list[dict] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        features.extend(data.get("features", []))

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return dst_path


def _merge_corridor_tifs(src_paths: List[Path], dst_path: Path) -> Path:
    if not src_paths:
        raise ValueError("No corridor tif paths to merge")

    with rasterio.open(src_paths[0]) as ref:
        profile = ref.profile.copy()
        nodata = ref.nodata if ref.nodata is not None else -9999.0
        merged = np.full((ref.height, ref.width), nodata, dtype=np.float32)
        any_valid = np.zeros((ref.height, ref.width), dtype=bool)
        ref_crs = ref.crs
        ref_transform = ref.transform

    for path in src_paths:
        with rasterio.open(path) as ds:
            arr = ds.read(1).astype(np.float32)
            if arr.shape != merged.shape:
                raise ValueError("Corridor rasters must share the same shape for merging")
            if ds.crs != ref_crs:
                raise ValueError("Corridor rasters must share the same CRS for merging")
            if ds.transform != ref_transform:
                raise ValueError("Corridor rasters must share the same transform for merging")

            valid = np.isfinite(arr) & (~np.isclose(arr, nodata))
            merged = np.where(valid & any_valid, np.maximum(merged, arr), merged)
            merged = np.where(valid & (~any_valid), arr, merged)
            any_valid |= valid

    profile.update(dtype="float32", count=1, compress="deflate", nodata=nodata)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(merged.astype(np.float32), 1)
    return dst_path


def run_route_request(
    *,
    req: RouteRequest,
    areas_gdf: gpd.GeoDataFrame,
    all_points_xy: List[Tuple[float, float]],
    start_xy: Tuple[float, float],
    end_xy: Tuple[float, float],
    output_root: Path,
    grass_lock: Lock,
) -> dict:
    try:
        with grass_lock:
            run_id = _new_run_id()
            print(f"[route] run_id={run_id} pid={os.getpid()} request_start")

            gs.run_command("g.remove", type="raster", name="MASK", flags="f", quiet=True)
            gs.run_command("g.remove", type="raster", pattern="*", flags="f", quiet=True)
            gs.run_command("g.remove", type="vector", pattern="*", flags="f", quiet=True)

            bbox_ids = _areas_for_points_bbox(areas_gdf, all_points_xy, req.buffer_m)
            start_ids = _areas_containing_point(areas_gdf, start_xy)
            end_ids = _areas_containing_point(areas_gdf, end_xy)
            stop_ids = [_areas_containing_point(areas_gdf, xy) for xy in all_points_xy[1:-1]]

            if not start_ids:
                raise HTTPException(422, "Start point is outside all available areas.")
            if not end_ids:
                raise HTTPException(422, "End point is outside all available areas.")
            for index, ids in enumerate(stop_ids, start=1):
                if not ids:
                    raise HTTPException(422, f"Stop {index} is outside all available areas.")

            area_ids = sorted(
                set(bbox_ids)
                | set(start_ids)
                | set(end_ids)
                | {area_id for ids in stop_ids for area_id in ids}
            )
            if not area_ids:
                raise HTTPException(422, "No areas selected for routing.")

            dem_mosaic = build_or_get_mosaic(area_ids, kind="dem")
            base_cost_mosaic = build_or_get_mosaic(area_ids, kind="cost")
            cost_mosaic = compose_cost_surface_for_request(
                area_ids,
                base_cost_name=base_cost_mosaic,
                avoid_lake=req.avoid_lake,
                avoid_glacier=req.avoid_glacier,
                avoid_river=req.avoid_river,
                track_influence_mode=req.track_influence_mode,
            )

            _set_region_for_points(cost_mosaic, all_points_xy, req.buffer_m)

            any_paths, any_inputs = load_area(area_ids[0])

            leg_route_paths: List[Path] = []
            leg_corridor_tifs: dict[str, List[Path]] = {mode: [] for mode in config.CORRIDOR_MODE_PARAMS}
            total_legs = len(all_points_xy) - 1
            single_leg = total_legs == 1
            single_leg_res: dict | None = None

            for leg_index, (leg_start, leg_end) in enumerate(zip(all_points_xy[:-1], all_points_xy[1:]), start=1):
                output_suffix = None if single_leg else f"leg_{leg_index}"
                leg_res = run_routing_for_tour(
                    paths=any_paths,
                    inputs=any_inputs,
                    tour_name=req.name or "adhoc",
                    start_coords=leg_start,
                    end_coords=leg_end,
                    lambda_weight=req.lambda_weight,
                    smooth_threshold=req.smooth_threshold,
                    corridor_mode=req.corridor_mode,
                    cost_surface_override=cost_mosaic,
                    dem_override=dem_mosaic,
                    preserve_region=True,
                    output_mode="run",
                    run_id=run_id,
                    output_root=output_root,
                    output_suffix=output_suffix,
                )
                if single_leg:
                    single_leg_res = leg_res
                else:
                    leg_route_paths.append(Path(leg_res["path_geojson_native"]))
                    for mode_name, tif_path in leg_res.get("corridor_tifs", {}).items():
                        leg_corridor_tifs.setdefault(mode_name, []).append(Path(tif_path))

            output_base = Path(output_root).resolve() / "runs_output" / run_id
            route_dir = output_base / "route"
            corridor_dir = output_base / "corridor"

            if single_leg:
                if single_leg_res is None:
                    raise RuntimeError("Single-leg routing produced no result")

                merged_route_path = Path(single_leg_res["path_geojson_native"])
                merged_corridor_tifs = {
                    mode_name: Path(path)
                    for mode_name, path in single_leg_res.get("corridor_tifs", {}).items()
                }
            else:
                merged_route_path = _merge_native_route_geojson(leg_route_paths, route_dir / "path.geojson")
                merged_corridor_tifs = {
                    mode_name: _merge_corridor_tifs(tif_paths, corridor_dir / f"corridor_{mode_name}.tif")
                    for mode_name, tif_paths in leg_corridor_tifs.items()
                    if tif_paths
                }

            res = {
                "path_geojson_native": str(merged_route_path),
                "corridor_tif": str(merged_corridor_tifs[req.corridor_mode]),
                "corridor_tifs": {mode: str(path) for mode, path in merged_corridor_tifs.items()},
                "legs": len(leg_route_paths),
            }

            return {
                "run_id": run_id,
                "res": res,
                "area_ids": area_ids,
                "dem_mosaic": dem_mosaic,
                "cost_mosaic": cost_mosaic,
            }

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
