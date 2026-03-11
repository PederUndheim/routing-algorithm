from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import hashlib

import rasterio

from backend.file_handler.area_context import load_area
from backend import config

import grass.script as gs


WGS84 = "EPSG:4326"
NATIVE = "EPSG:25833"
OPTIONAL_MASK_KINDS = {"lake", "glacier"}
OPTIONAL_TRACK_KINDS = {"tracks", "forest"}


def safe_grass_name(s: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in s)
    if out and out[0].isdigit():
        out = "_" + out
    return out


def grass_raster_exists(name: str) -> bool:
    found = gs.find_file(name, element="cell")
    return bool(found and found.get("name"))


def raster_has_data(name: str) -> bool:
    txt = gs.read_command("r.univar", map=name, flags="g").strip().splitlines()
    d = dict(line.split("=", 1) for line in txt if "=" in line)
    return int(float(d.get("n", "0"))) > 0


def ensure_raster_imported(tif_path: Path, raster_name: str) -> None:
    if grass_raster_exists(raster_name):
        return
    
    if not tif_path.exists():
        raise FileNotFoundError(f"Missing raster source tif: {tif_path}")

    gs.run_command(
        "r.in.gdal",
        input=str(tif_path),
        output=raster_name,
        overwrite=False,
        quiet=True,
    )


def set_region_to_tif_union(tif_paths: List[Path]) -> None:
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


def mosaic_name(prefix: str, area_ids: List[str]) -> str:
    key = ",".join(area_ids).encode("utf-8")
    h = hashlib.sha1(key).hexdigest()[:10]
    return f"{prefix}_mosaic_{h}"


def _source_tif_for_kind(paths, inputs, kind: str) -> Path:
    if kind == "cost":
        return Path(paths.cost_surface)
    if kind == "dem":
        return Path(paths.dem) if getattr(paths, "dem", None) else Path(inputs["dem"])
    if kind in OPTIONAL_MASK_KINDS | OPTIONAL_TRACK_KINDS:
        # In prod we ship runtime data into the image, so prefer runtime rasters.
        runtime_mask = paths.runtime_area_root / f"{kind}.tif"
        if runtime_mask.exists():
            return runtime_mask
        # Local fallback while developing before exporting runtime artifacts.
        return paths.input / f"{kind}.tif"
    raise ValueError(f"Unsupported mosaic kind: {kind}")


def _base_name_for_kind(area_id: str, kind: str) -> str:
    return f"{kind}__{safe_grass_name(area_id)}"


def build_or_get_mosaic(area_ids: List[str], *, kind: str) -> str:
    """
    kind: "cost" | "dem" | "lake" | "glacier" | "tracks" | "forest"
    Returns a GRASS raster name.
    """
    if kind not in {"cost", "dem", *OPTIONAL_MASK_KINDS, *OPTIONAL_TRACK_KINDS}:
        raise ValueError(
            "kind must be 'cost', 'dem', 'lake', 'glacier', 'tracks' or 'forest'"
        )

    if not area_ids:
        raise ValueError("area_ids is empty")
    
    print("MOSAIC_SERVICE_VERSION=2026-03-03-A")

    # Single area: import and return base raster
    if len(area_ids) == 1:
        area_id = area_ids[0]
        paths, inputs = load_area(area_id)

        tif_path = _source_tif_for_kind(paths, inputs, kind)
        base = _base_name_for_kind(area_id, kind)

        ensure_raster_imported(tif_path, base)
        return base

    # Multi area mosaic
    mosaic = mosaic_name(kind, area_ids)

    if grass_raster_exists(mosaic) and raster_has_data(mosaic):
        return mosaic

    input_maps: List[str] = []
    tif_paths: List[Path] = []

    for area_id in area_ids:
        paths, inputs = load_area(area_id)

        tif_path = _source_tif_for_kind(paths, inputs, kind)
        base = _base_name_for_kind(area_id, kind)

        ensure_raster_imported(tif_path, base)
        input_maps.append(base)
        tif_paths.append(tif_path)

    # Ensure GRASS region covers all tifs before building VRT
    set_region_to_tif_union(tif_paths)

    # Fast virtual mosaic
    gs.run_command(
        "r.buildvrt",
        input=",".join(input_maps),
        output=mosaic,
        overwrite=True,
        quiet=True,
    )

    return mosaic


def _raster_max(name: str) -> float:
    txt = gs.read_command("r.univar", map=name, flags="g").strip().splitlines()
    d = dict(line.split("=", 1) for line in txt if "=" in line)
    n = float(d.get("n", "0") or "0")
    if n <= 0:
        return 0.0
    return float(d.get("max", "0") or "0")


def compose_tracks_influence_for_request(
    area_ids: List[str],
    *,
    base_cost_name: str,
    track_influence_mode: str,
) -> str:
    mode = track_influence_mode.lower()
    if mode not in config.TRACK_INFLUENCE_PARAMS:
        raise ValueError(f"Unsupported track_influence_mode: {track_influence_mode}")

    mode_params = config.TRACK_INFLUENCE_PARAMS[mode]
    w_outside = float(mode_params["w_outside"])
    w_forest = float(mode_params["w_forest"])
    if w_outside <= 0.0 and w_forest <= 0.0:
        return base_cost_name

    tracks_name = build_or_get_mosaic(area_ids, kind="tracks")
    forest_name = build_or_get_mosaic(area_ids, kind="forest")
    tracks_max = _raster_max(tracks_name)

    if tracks_max <= 0.0:
        return base_cost_name

    request_cost_name = mosaic_name(f"cost_tracks_{mode}", area_ids)

    w_expr = (
        f"({w_outside} + ({w_forest} - {w_outside}) * "
        f"if(isnull({forest_name}), 0, if({forest_name} > 0, 1, 0)))"
    )
    t_expr = (
        f"if(isnull({tracks_name}), 0, "
        f"min(max({tracks_name}, 0) / {tracks_max:.6f}, 1))"
    )

    gs.mapcalc(
        f"{request_cost_name} = max(1, min(99, {base_cost_name} * (1 - ({w_expr}) * ({t_expr}))))",
        overwrite=True,
    )

    return request_cost_name


def compose_cost_surface_for_request(
    area_ids: List[str],
    *,
    base_cost_name: str,
    avoid_lake: bool,
    avoid_glacier: bool,
    track_influence_mode: str,
) -> str:
    with_tracks = compose_tracks_influence_for_request(
        area_ids,
        base_cost_name=base_cost_name,
        track_influence_mode=track_influence_mode,
    )

    if not avoid_lake and not avoid_glacier:
        return with_tracks

    mask_names: List[str] = []
    if avoid_lake:
        mask_names.append(build_or_get_mosaic(area_ids, kind="lake"))
    if avoid_glacier:
        mask_names.append(build_or_get_mosaic(area_ids, kind="glacier"))

    combined_mask = " + ".join(
        f"if(isnull({name}), 0, {name})" for name in mask_names
    )
    request_cost_name = mosaic_name("cost_req", area_ids)

    gs.mapcalc(
        f"{request_cost_name} = if(({combined_mask}) > 0, 99, {with_tracks})",
        overwrite=True,
    )

    return request_cost_name


def set_region_local(
    mosaic_raster: str,
    start_xy: Tuple[float, float],
    end_xy: Tuple[float, float],
    buffer_m: float,
) -> None:
    # Align first
    gs.run_command("g.region", raster=mosaic_raster, quiet=True)

    # Then shrink to bbox window
    minx = min(start_xy[0], end_xy[0]) - buffer_m
    maxx = max(start_xy[0], end_xy[0]) + buffer_m
    miny = min(start_xy[1], end_xy[1]) - buffer_m
    maxy = max(start_xy[1], end_xy[1]) + buffer_m

    gs.run_command("g.region", n=maxy, s=miny, e=maxx, w=minx, quiet=True)