"""Merge the per-tile cost surfaces into one national raster."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from skimap import paths
from skimap.data_preprocessing import rasters


def build_mosaic(out_path: Path = paths.COST_SURFACE / "cost_surface.vrt",
                 tiles_root: Optional[Path] = None) -> Path:
    """VRT over every tile's cost_surface.tif. Tiles do not overlap, so no
    resolution rule is needed.

    `tiles_root` mosaics a variant build - a surface built with some layer
    turned off, for measuring what that layer contributes - instead of the
    production tiles.
    """
    root = tiles_root or paths.TILES
    tiles = sorted(root.glob("*/cost_surface.tif"))
    if not tiles:
        raise FileNotFoundError(
            f"No tiles under {root}. Build them with 'python -m skimap.cli cost'."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"{len(tiles)} tiles -> {out_path}")
    return rasters.build_vrt(tiles, out_path)


def to_cog(vrt: Path, out_path: Path) -> Path:
    """Materialize the VRT as a single cloud-optimized GeoTIFF.

    This is also the only form ArcGIS will open - it does not read GDAL VRT.

    dtype and nodata come off the tiles, so this stays a straight copy: the
    cost values were already clipped and rounded per tile and must not be
    rescaled again here.

    NEAREST overviews, not the COG driver's default CUBIC: cost is a scale
    where most of the country sits at 4 and the sea sits at 5000, so an
    interpolated overview pixel is a value that exists nowhere in the data
    and reads as a passable shore.
    """
    return rasters.to_cog(vrt, out_path, compress="DEFLATE", resampling="NEAREST")


