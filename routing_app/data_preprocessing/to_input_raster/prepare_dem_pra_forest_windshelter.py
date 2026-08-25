from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject
from shapely.geometry import box

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.to_raster import make_template_raster_for_area


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


def collect_by_var(dem_pra_forest_windshelter: Path) -> Dict[str, List[Path]]:
    out = {v.name: [] for v in VARS}
    for tile_dir in sorted(p for p in dem_pra_forest_windshelter.iterdir() if p.is_dir()):
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


def resampling_for(var_name: str) -> Resampling:
    # Juster PRA_raw hvis den egentlig er en maske (da nearest)
    if var_name in {"forest"}:
        return Resampling.nearest
    if var_name in {"DEM", "windshelter", "PRA_raw"}:
        return Resampling.bilinear
    return Resampling.nearest


def main() -> None:
    cfg = load_config()

    # Dette er “kilden” du mosaikker fra (tilpass om du vil lese fra cfg)
    dem_pra_forest_windshelter = cfg.national_root / "dem_pra_forest_windshelter"

    # Les study areas via config
    study = gpd.read_file(cfg.study_areas).to_crs(cfg.crs)
    if "area_id" not in study.columns:
        raise ValueError("study_areas must have area_id")
    if study["area_id"].isna().any():
        raise ValueError("study_areas has NULL area_id values")

    rasters = collect_by_var(dem_pra_forest_windshelter)

    # Precompute footprints for quick intersects
    fp = {v.name: [(p, footprint(p)) for p in rasters[v.name]] for v in VARS}

    for _, row in study.iterrows():
        area_id = str(row["area_id"])
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        out_dir = cfg.areas_root / area_id / "input"
        out_dir.mkdir(parents=True, exist_ok=True)

        area_where = f"area_id = '{area_id}'"
        template = cfg.areas_cache_root / area_id / "template.tif"
        template.parent.mkdir(parents=True, exist_ok=True)

        # 1) Ensure template exists (samme logikk som resten av pipelinen)
        if not template.exists():
            make_template_raster_for_area(
                area_polygon_gpkg=cfg.study_areas,
                area_where=area_where,
                out_template=template,
                crs_epsg=cfg.crs_epsg,
                pixel_size=cfg.pixel_size,
                nodata=cfg.nodata,
            )

        with rasterio.open(template) as tmpl:
            tmpl_profile = tmpl.profile.copy()
            tmpl_crs = tmpl.crs
            tmpl_transform = tmpl.transform
            tmpl_h, tmpl_w = tmpl.height, tmpl.width

            for v in VARS:
                candidates = [p for (p, g) in fp[v.name] if g.intersects(geom)]
                if not candidates:
                    print(f"{area_id} {v.name}: no intersecting rasters")
                    continue

                srcs = [rasterio.open(p) for p in candidates]
                try:
                    # 2) Mosaic tiles (i mosaikkens eget grid)
                    mosaic, mosaic_transform = merge(
                        srcs,
                        method="max",
                        nodata=cfg.nodata,
                    )

                    # 3) Warp mosaic -> template grid (garanterer identisk extent)
                    warped = np.full(
                        (mosaic.shape[0], tmpl_h, tmpl_w),
                        cfg.nodata,
                        dtype=mosaic.dtype,
                    )

                    # Anta samme CRS i alle candidates (kan evt validere i en assert)
                    src_crs = srcs[0].crs

                    for b in range(mosaic.shape[0]):
                        reproject(
                            source=mosaic[b],
                            destination=warped[b],
                            src_transform=mosaic_transform,
                            src_crs=src_crs,
                            dst_transform=tmpl_transform,
                            dst_crs=tmpl_crs,
                            dst_width=tmpl_w,
                            dst_height=tmpl_h,
                            resampling=resampling_for(v.name),
                            src_nodata=cfg.nodata,
                            dst_nodata=cfg.nodata,
                        )

                    # 4) Apply area mask, but keep template shape (crop=False)
                    profile = tmpl_profile.copy()
                    profile.update(
                        driver="GTiff",
                        dtype=warped.dtype,
                        count=warped.shape[0],
                        nodata=cfg.nodata,
                    )

                    with MemoryFile() as memfile:
                        with memfile.open(**profile) as mem:
                            mem.write(warped)
                            out_arr, out_transform = mask(
                                mem,
                                [geom],
                                crop=False,
                                nodata=cfg.nodata,
                                filled=True,
                            )

                    # 5) Write output with template-aligned metadata
                    out_profile = profile.copy()
                    out_profile.update(
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
