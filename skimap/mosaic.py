"""Merge the per-tile cost surfaces into one national raster."""

from __future__ import annotations

from pathlib import Path

from skimap import config, paths
from skimap.data_preprocessing import rasters


def build_mosaic(out_path: Path = paths.OUTPUT / "cost_surface.vrt") -> Path:
    """VRT over every tile's cost_surface.tif. Tiles do not overlap, so no
    resolution rule is needed."""
    tiles = sorted(paths.TILES.glob("*/cost_surface.tif"))
    if not tiles:
        raise FileNotFoundError(
            f"No tiles under {paths.TILES}. Build them with 'python -m skimap.cli cost'."
        )
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


