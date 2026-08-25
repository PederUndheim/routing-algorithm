"""Reading tile windows out of the national layers, and writing tile output.

Every national layer shares one grid, so a tile is a plain pixel window -
no warping, no resampling, no per-tile GDAL process.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal

from skimap import config, paths
from skimap.grid import Tile

gdal.UseExceptions()

TILE_PX = int(config.TILE_SIZE / config.PIXEL_SIZE)


def window(ds: gdal.Dataset, tile: Tile) -> tuple[int, int]:
    """Pixel offset of a tile's south-west corner within a national layer.

    Tile corners sit on the tile lattice and layers on the raster lattice,
    exactly half a pixel apart (see config.RASTER_ORIGIN), so this division
    always lands on .5.

    It must therefore floor, never round. Layers have different origins, so
    the integer part differs between them - and round() breaks ties to even,
    which would snap .5 up for one layer and down for another and shift them
    a pixel apart. That misalignment is invisible per layer and only shows up
    as masks disagreeing: trails-in-forest landing outside forest, bridges
    off their rivers.
    """
    gt = ds.GetGeoTransform()
    px = (tile.x0 - gt[0]) / config.PIXEL_SIZE
    py = (gt[3] - (tile.y0 + config.TILE_SIZE)) / config.PIXEL_SIZE
    return math.floor(px), math.floor(py)


def tile_origin(tile: Tile) -> tuple[float, float]:
    """North-west corner of the CELLS a tile reads, not of its polygon.

    window() floors onto the raster lattice, so the cells a tile actually
    covers begin half a pixel outside the tile polygon. Output has to be
    georeferenced where those cells really are. Writing it at the polygon
    corner instead moves every value half a pixel - invisible within one
    tile, since the array is unchanged, and visible the moment the surface
    is laid over anything else: barriers land beside their own coastline
    and r.walk pairs elevation with the friction of a neighbouring cell.

    This is what config.RASTER_ORIGIN means by tile templates sitting 5 m
    off the tile polygons. Every national layer shares one lattice, so the
    answer is the same whichever of them a tile was read from.
    """
    ox, oy = config.RASTER_ORIGIN
    p = config.PIXEL_SIZE
    top = tile.y0 + config.TILE_SIZE
    return (ox + math.floor((tile.x0 - ox) / p) * p,
            oy + math.ceil((top - oy) / p) * p)


def read_tile(name: str, tile: Tile, *, fill: float = np.nan) -> np.ndarray:
    """Read one layer over one tile as float32 in REAL units.

    No national layer carries a band scale or offset any more: slope,
    pra_runout and windshelter are all written as Float32 in the units they
    mean, so they read the same here as they do in QGIS. The scale/offset
    handling below stays regardless - it is two metadata lookups, and it is
    the difference between a rescaled layer being read correctly and being
    read 1000x out with nothing on screen to say so.

    Nodata becomes `fill`. Tiles that fall partly outside a layer's extent
    are padded with `fill` rather than failing: a layer need not cover the
    whole country.
    """
    ds = gdal.Open(str(paths.layer(name)))
    band = ds.GetRasterBand(1)
    px, py = window(ds, tile)

    out = np.full((TILE_PX, TILE_PX), fill, dtype=np.float32)

    # Clip the request to the layer, then place it in the right spot.
    sx0, sy0 = max(px, 0), max(py, 0)
    sx1, sy1 = min(px + TILE_PX, ds.RasterXSize), min(py + TILE_PX, ds.RasterYSize)
    if sx1 > sx0 and sy1 > sy0:
        arr = band.ReadAsArray(sx0, sy0, sx1 - sx0, sy1 - sy0).astype(np.float32)

        nodata = band.GetNoDataValue()
        if nodata is not None:
            arr = np.where(arr == np.float32(nodata), np.float32(fill), arr)

        scale, offset = band.GetScale(), band.GetOffset()
        if scale is not None and scale != 1.0:
            arr *= np.float32(scale)
        if offset:
            arr += np.float32(offset)

        out[sy0 - py:sy1 - py, sx0 - px:sx1 - px] = arr

    ds = None
    return out


def read_mask(name: str, tile: Tile) -> np.ndarray:
    """Read one layer over one tile as a boolean mask (True where present)."""
    return read_tile(name, tile, fill=0.0) > 0


def write_tile(array: np.ndarray, tile: Tile, out_path: Path, *,
               dtype: str = "UInt16", nodata: Optional[float] = None) -> Path:
    """Write a tile-shaped array, georeferenced on the RASTER lattice.

    On the raster lattice, not the tile lattice - see tile_origin(). The two
    are half a pixel apart and the cells are the raster lattice's.

    The predictor follows the dtype: 3 is the floating-point one, 2 is
    horizontal differencing for integers. They are not interchangeable -
    2 on float data is outside the TIFF spec and compresses badly.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(
        str(out_path), TILE_PX, TILE_PX, 1, gdal.GetDataTypeByName(dtype),
        options=["TILED=YES", "COMPRESS=DEFLATE",
                 "PREDICTOR=%d" % (3 if dtype.startswith("Float") else 2),
                 "NUM_THREADS=ALL_CPUS"],
    )
    x0, y0 = tile_origin(tile)
    ds.SetGeoTransform((x0, config.PIXEL_SIZE, 0.0, y0, 0.0, -config.PIXEL_SIZE))

    srs = gdal.osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    ds.SetProjection(srs.ExportToWkt())

    band = ds.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    band.WriteArray(array)
    band.FlushCache()
    ds = None
    return out_path
