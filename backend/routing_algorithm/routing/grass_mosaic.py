from __future__ import annotations

from pathlib import Path
from typing import List
import hashlib

import rasterio
import grass.script as gs

from backend.file_handler.area_context import load_area


OPTIONAL_MASK_KINDS = {"lake", "glacier", "river", "river_with_bridge"}
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


def ensure_raster_imported(tif_path: Path, raster_name: str, *, force_overwrite: bool = False) -> None:
    if grass_raster_exists(raster_name) and not force_overwrite:
        return

    if not tif_path.exists():
        raise FileNotFoundError(f"Missing raster source tif: {tif_path}")

    gs.run_command(
        "r.in.gdal",
        input=str(tif_path),
        output=raster_name,
        overwrite=force_overwrite,
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
        runtime_mask = paths.runtime_area_root / f"{kind}.tif"
        if runtime_mask.exists():
            return runtime_mask
        return paths.input / f"{kind}.tif"
    raise ValueError(f"Unsupported mosaic kind: {kind}")


def _base_name_for_kind(area_id: str, kind: str) -> str:
    return f"{kind}__{safe_grass_name(area_id)}"


def build_or_get_mosaic(area_ids: List[str], *, kind: str, force_import: bool = False) -> str:
    if kind not in {"cost", "dem", *OPTIONAL_MASK_KINDS, *OPTIONAL_TRACK_KINDS}:
        raise ValueError(
            "kind must be 'cost', 'dem', 'lake', 'glacier', 'river', 'river_with_bridge', 'tracks' or 'forest'"
        )

    if not area_ids:
        raise ValueError("area_ids is empty")

    if len(area_ids) == 1:
        area_id = area_ids[0]
        paths, inputs = load_area(area_id)

        tif_path = _source_tif_for_kind(paths, inputs, kind)
        base = _base_name_for_kind(area_id, kind)

        ensure_raster_imported(tif_path, base, force_overwrite=force_import)
        return base

    mosaic = mosaic_name(kind, area_ids)

    if grass_raster_exists(mosaic) and raster_has_data(mosaic):
        return mosaic

    input_maps: List[str] = []
    tif_paths: List[Path] = []

    for area_id in area_ids:
        paths, inputs = load_area(area_id)

        tif_path = _source_tif_for_kind(paths, inputs, kind)
        base = _base_name_for_kind(area_id, kind)

        ensure_raster_imported(tif_path, base, force_overwrite=force_import)
        input_maps.append(base)
        tif_paths.append(tif_path)

    set_region_to_tif_union(tif_paths)

    gs.run_command(
        "r.buildvrt",
        input=",".join(input_maps),
        output=mosaic,
        overwrite=True,
        quiet=True,
    )

    return mosaic
