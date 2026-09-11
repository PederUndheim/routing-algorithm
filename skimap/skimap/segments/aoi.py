"""The window an area is painted into, and reading and writing on it.

Everything read here - the corridors, the outline, the DEM - sits on
config.RASTER_ORIGIN's lattice, so a window is a plain pixel offset in each
and reading one is a crop and a pad. No warping, no GDAL process per layer.

The shared lattice matters more here than in skimap.raster, which reads one
layer at a time. Painting takes a colour from one raster and an opacity from
another and multiplies them per cell, so half a cell of drift between two
corridors is not a subtle inaccuracy - it is a fringe of the wrong colour
drawn down one side of every boundary, with nothing on screen to say it came
from georeferencing rather than from the terrain. `read` therefore checks
the offset it computed is a whole number of cells rather than rounding to
one, and names the file that was off when it is not.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from osgeo import gdal, ogr, osr

from skimap import config

gdal.UseExceptions()
ogr.UseExceptions()


@dataclass(frozen=True)
class Window:
    """A pixel-aligned rectangle: north-west corner and a size in cells."""

    x0: float
    y1: float
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def geotransform(self) -> tuple[float, float, float, float, float, float]:
        p = config.PIXEL_SIZE
        return (self.x0, p, 0.0, self.y1, 0.0, -p)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        p = config.PIXEL_SIZE
        return (self.x0, self.y1 - self.height * p, self.x0 + self.width * p, self.y1)

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Cell-centre coordinates, as two full-size arrays."""
        p = config.PIXEL_SIZE
        return np.meshgrid(self.x0 + (np.arange(self.width) + 0.5) * p,
                           self.y1 - (np.arange(self.height) + 0.5) * p)

    def __str__(self) -> str:
        x0, y0, x1, y1 = self.bounds
        return f"{self.width} x {self.height} px ({x0:.0f} {y0:.0f} {x1:.0f} {y1:.0f})"


def srs() -> osr.SpatialReference:
    s = osr.SpatialReference()
    s.ImportFromEPSG(config.CRS_EPSG)
    return s


def snap(bounds: tuple[float, float, float, float], *, pad_m: float = 0.0) -> Window:
    """The smallest lattice-aligned window covering `bounds`, plus a pad.

    Outward on all four sides, so the window never crops what was asked for -
    which is why clipping to an outline needs `mask` as well as this.
    """
    ox, oy = config.RASTER_ORIGIN
    p = config.PIXEL_SIZE
    xmin, ymin, xmax, ymax = bounds
    x0 = ox + math.floor((xmin - pad_m - ox) / p) * p
    y0 = oy + math.floor((ymin - pad_m - oy) / p) * p
    x1 = ox + math.ceil((xmax + pad_m - ox) / p) * p
    y1 = oy + math.ceil((ymax + pad_m - oy) / p) * p
    return Window(x0, y1, int(round((x1 - x0) / p)), int(round((y1 - y0) / p)))


def open_layer(path: Path, layer: Optional[str] = None):
    """A vector layer, with its CRS checked rather than reprojected.

    An outline drawn in the wrong projection lands somewhere plausible and
    renders a window of empty terrain, which reads as "no corridors here"
    rather than as the mistake it is.
    """
    ds = ogr.Open(str(path))
    if ds is None:
        raise FileNotFoundError(f"Cannot open {path}")
    lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
    if lyr is None:
        raise KeyError(f"No layer {layer!r} in {path}")
    ref = lyr.GetSpatialRef()
    if ref is not None and not ref.IsSame(srs()):
        raise ValueError(
            f"{Path(path).name} is in {ref.GetName() or 'an unknown CRS'}, not "
            f"EPSG:{config.CRS_EPSG}. Reproject it - nothing here warps."
        )
    return ds, lyr


def from_vector(path: Path, *, layer: Optional[str] = None, pad_m: float = 0.0) -> Window:
    """A window covering a vector file's extent."""
    ds, lyr = open_layer(path, layer)
    xmin, xmax, ymin, ymax = lyr.GetExtent()
    ds = None
    return snap((xmin, ymin, xmax, ymax), pad_m=pad_m)


def union(path: Path, *, layer: Optional[str] = None) -> ogr.Geometry:
    """Every feature in a layer dissolved into one geometry.

    Cloned before the datasource closes - an OGR geometry borrowed from a
    feature is freed with it, and using one afterwards reads freed memory.
    """
    ds, lyr = open_layer(path, layer)
    merged = ogr.Geometry(ogr.wkbMultiPolygon)
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is not None and not geom.IsEmpty():
            merged.AddGeometry(geom.Clone())
    out = merged.UnionCascaded()
    ds = None
    return out


def _offset(window: Window, ds: gdal.Dataset, path: Path) -> tuple[int, int]:
    p = config.PIXEL_SIZE
    g = ds.GetGeoTransform()
    if abs(g[1] - p) > 1e-6 or abs(abs(g[5]) - p) > 1e-6:
        raise ValueError(
            f"{path.name} is {g[1]:g} m, not {p:g} m. Everything painted onto one "
            "window has to share the lattice; resample it first."
        )
    fx, fy = (window.x0 - g[0]) / p, (g[3] - window.y1) / p
    if abs(fx - round(fx)) > 1e-3 or abs(fy - round(fy)) > 1e-3:
        raise ValueError(
            f"{path.name} is off the lattice by ({fx % 1:.3f}, {fy % 1:.3f}) px. "
            f"Its origin is ({g[0]:.1f}, {g[3]:.1f}); config.RASTER_ORIGIN is "
            f"{config.RASTER_ORIGIN}."
        )
    return int(round(fx)), int(round(fy))


def read(window: Window, path: Path, *, fill: float = 0.0) -> np.ndarray:
    """One raster on the window as float32; nodata and outside both `fill`.

    Padded rather than failing where the window runs off the source: one
    tour's corridor covers a few km of an area that may be much larger.
    """
    path = Path(path)
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    px, py = _offset(window, ds, path)

    out = np.full(window.shape, float(fill), dtype=np.float32)
    sx0, sy0 = max(px, 0), max(py, 0)
    sx1 = min(px + window.width, ds.RasterXSize)
    sy1 = min(py + window.height, ds.RasterYSize)
    if sx1 > sx0 and sy1 > sy0:
        arr = band.ReadAsArray(sx0, sy0, sx1 - sx0, sy1 - sy0).astype(np.float32)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            arr = np.where(arr == np.float32(nodata), np.float32(fill), arr)
        out[sy0 - py:sy1 - py, sx0 - px:sx1 - px] = np.nan_to_num(arr)
    ds = None
    return out


def overlaps(window: Window, path: Path) -> bool:
    """Whether a raster's extent meets the window. Cheap; says nothing about data."""
    ds = gdal.Open(str(path))
    g = ds.GetGeoTransform()
    x0, y1 = g[0], g[3]
    x1, y0 = x0 + g[1] * ds.RasterXSize, y1 + g[5] * ds.RasterYSize
    ds = None
    wx0, wy0, wx1, wy1 = window.bounds
    return x0 < wx1 and x1 > wx0 and y0 < wy1 and y1 > wy0


def mask(window: Window, path: Path, *, layer: Optional[str] = None) -> np.ndarray:
    """A polygon burned onto the window, True inside."""
    ds = gdal.GetDriverByName("MEM").Create("", window.width, window.height, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(window.geotransform)
    ds.SetProjection(srs().ExportToWkt())
    opts = {"burnValues": [1]}
    if layer:
        opts["layers"] = [layer]
    gdal.Rasterize(ds, str(path), **opts)
    out = ds.GetRasterBand(1).ReadAsArray().astype(bool)
    ds = None
    return out


def burn(window: Window, geom: ogr.Geometry) -> np.ndarray:
    """One geometry as a boolean mask, exactly as drawn."""
    src = ogr.GetDriverByName("MEM").CreateDataSource("burn")
    lyr = src.CreateLayer("burn", srs(), ogr.wkbPolygon)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    lyr.CreateFeature(feat)
    feat = None

    ds = gdal.GetDriverByName("MEM").Create("", window.width, window.height, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(window.geotransform)
    ds.SetProjection(srs().ExportToWkt())
    gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1])
    out = ds.GetRasterBand(1).ReadAsArray().astype(bool)
    ds = src = None
    return out


def write(window: Window, array: np.ndarray, out_path: Path, *,
          nodata: float = 0.0) -> tuple[Path, bool]:
    """Write a Float32 raster. Returns (path written, whether it landed).

    Built beside the target and moved into place, never straight over it.
    gdal.Create deletes the existing file first, so a raster open in ArcGIS -
    which holds a lock on it - leaves you with neither the new file nor the
    old one. Observed: a 796 KB corridor truncated to 266 bytes that way.

    A blocked write keeps the .tmp.tif and reports False rather than raising,
    so one locked layer does not lose the other two.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.tif")

    ds = gdal.GetDriverByName("GTiff").Create(
        str(tmp), window.width, window.height, 1, gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3",
                 "SPARSE_OK=TRUE", "BIGTIFF=IF_SAFER", "NUM_THREADS=ALL_CPUS"],
    )
    ds.SetGeoTransform(window.geotransform)
    ds.SetProjection(srs().ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(array.astype(np.float32))
    band.FlushCache()
    ds.BuildOverviews("AVERAGE", [2, 4, 8, 16])
    ds = None

    try:
        os.replace(tmp, out_path)
        return out_path, True
    except OSError:
        return tmp, False


def merge_max(window: Window, paths: Iterable[Path]) -> np.ndarray:
    """Several corridors on one window, overlaps taking the maximum.

    MAX for the reason routing.merge_corridors gives: a corridor is a
    membership score, and a cell two tours both pass through is no more "in a
    corridor" than its best one makes it.
    """
    out = np.zeros(window.shape, dtype=np.float32)
    for path in paths:
        if overlaps(window, path):
            out = np.maximum(out, read(window, path))
    return out
