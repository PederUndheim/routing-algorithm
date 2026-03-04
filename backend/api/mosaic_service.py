from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import hashlib

import rasterio

from backend.file_handler.area_context import load_area

import grass.script as gs


WGS84 = "EPSG:4326"
NATIVE = "EPSG:25833"


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


def build_or_get_mosaic(area_ids: List[str], *, kind: str) -> str:
    """
    kind: "cost" | "dem"
    Returns a GRASS raster name.
    """
    if kind not in {"cost", "dem"}:
        raise ValueError("kind must be 'cost' or 'dem'")

    if not area_ids:
        raise ValueError("area_ids is empty")
    
    print("MOSAIC_SERVICE_VERSION=2026-03-03-A")

    # Single area: import and return base raster
    if len(area_ids) == 1:
        area_id = area_ids[0]
        paths, inputs = load_area(area_id)

        if kind == "cost":
            tif_path = Path(paths.cost_surface)
            base = f"cost__{safe_grass_name(area_id)}"
        else:
            tif_path = Path(paths.dem)
            base = f"dem__{safe_grass_name(area_id)}"

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

        if kind == "cost":
            tif_path = Path(paths.cost_surface)
            base = f"cost__{safe_grass_name(area_id)}"
        else:
            tif_path = Path(paths.dem) if getattr(paths, "dem", None) else Path(inputs["dem"])
            base = f"dem__{safe_grass_name(area_id)}"

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