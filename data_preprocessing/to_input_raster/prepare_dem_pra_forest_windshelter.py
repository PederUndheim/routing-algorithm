from __future__ import annotations

import numpy as np
from rasterio.io import MemoryFile

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
from shapely.geometry import box

@dataclass(frozen=True)
class VarDef:
    name: str
    pattern: str

VARS = [
    VarDef("DEM", r"^DEM_.*\.tif$"),
    VarDef("PRA_raw", r"^PRA_raw_.*\.tif$"),
    VarDef("forest", r"^SKOG_.*\.tif$"),
    VarDef("windshelter", r"^windshelter_.*\.tif$"),
]

TARGET_EPSG = "EPSG:25833"
NODATA = -9999

STUDY = Path("data/raw/study_areas.gpkg")
ROUTES_ROOT = Path("data/raw/dem_pra_forest_windshelter")   # contains 00021/, 00042/, ...
OUT_ROOT = Path("data/areas")

def collect_by_var(routes_root: Path) -> Dict[str, List[Path]]:
    out = {v.name: [] for v in VARS}
    for tile_dir in sorted(p for p in routes_root.iterdir() if p.is_dir()):
        for v in VARS:
            rx = re.compile(v.pattern, re.IGNORECASE)
            matches = [p for p in tile_dir.iterdir() if p.is_file() and rx.match(p.name)]
            if matches:
                out[v.name].append(matches[0])
    return out

def footprint(path: Path):
    with rasterio.open(path) as ds:
        b = ds.bounds
        return box(b.left, b.bottom, b.right, b.top)

def main():
    study = gpd.read_file(STUDY).to_crs(TARGET_EPSG)
    if "area_id" not in study.columns:
        raise ValueError("study_areas must have area_id")
    if study["area_id"].isna().any():
        raise ValueError("study_areas has NULL area_id values")

    rasters = collect_by_var(ROUTES_ROOT)

    # Precompute footprints for quick intersects
    fp = {v.name: [(p, footprint(p)) for p in rasters[v.name]] for v in VARS}

    for _, row in study.iterrows():
        area_id = str(row["area_id"])
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        out_dir = OUT_ROOT / area_id / "input"
        out_dir.mkdir(parents=True, exist_ok=True)

        for v in VARS:
            candidates = [p for (p, g) in fp[v.name] if g.intersects(geom)]
            if not candidates:
                print(f"{area_id} {v.name}: no intersecting rasters")
                continue

            # Open all candidates and merge by max (pixelwise)
            srcs = [rasterio.open(p) for p in candidates]
            try:
                mosaic, transform = merge(
                    srcs,
                    method="max",     # highest value wins in overlaps
                    nodata=NODATA
                )

                # rasterio.merge returns shape: (bands, rows, cols)
                # Build an in-memory dataset so we can use rasterio.mask.mask cleanly
                profile = srcs[0].profile.copy()
                profile.update(
                    driver="GTiff",
                    height=mosaic.shape[1],
                    width=mosaic.shape[2],
                    transform=transform,
                    crs=TARGET_EPSG,
                    nodata=NODATA,
                    count=mosaic.shape[0],
                )

                with MemoryFile() as memfile:
                    with memfile.open(**profile) as mem:
                        mem.write(mosaic)

                        # Clip to polygon (this gives exact clipping and correct transform)
                        out_arr, out_transform = mask(
                            mem,
                            [geom],
                            crop=True,
                            nodata=NODATA,
                            filled=True
                        )

                # Write clipped output
                out_profile = profile.copy()
                out_profile.pop("blockxsize", None)
                out_profile.pop("blockysize", None)

                out_profile.update(
                    height=out_arr.shape[1],
                    width=out_arr.shape[2],
                    transform=out_transform,
                    compress="DEFLATE",
                    tiled=True,
                    blockxsize=256,
                    blockysize=256,
                    BIGTIFF="IF_SAFER",
                )

                out_path = out_dir / f"{v.name}.tif"
                with rasterio.open(out_path, "w", **out_profile) as dst:
                    dst.write(out_arr)

                print(f"{area_id} {v.name}: wrote {out_path}")


            finally:
                for s in srcs:
                    s.close()

if __name__ == "__main__":
    main()
