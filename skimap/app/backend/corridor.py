"""The corridor raster, turned into something a browser can draw.

`route_one` writes a Float32 GeoTIFF on the EPSG:25833 grid beside every
line: 1 on the optimal route, falling to 0 at the edge of the slack band,
nodata outside it. Leaflet draws a picture by stretching it between two
corners, and it does that stretching in Web Mercator - so the raster is
warped to EPSG:3857 here rather than handed over as it is. Pinning a 25833
grid to WGS84 corners instead would lean the corridor off its own route by
hundreds of metres this far north.

Colours come from `data/styles_arcgis/blue.lyrx`, so the app draws a corridor
the same way ArcGIS does and re-styling the layer in Pro changes both. That
file is a CIMRasterClassifyColorizer - twenty equal-interval classes over the
0..1 score, light blue at the bottom to navy at the top, with alpha rising
from nothing across the first three so the band fades out at its edge.

Why this does not call skimap.lyrx, whose whole job is reading these: that
module only reads CIMRasterStretchColorizer, and it drops alpha on purpose -
both deliberate, and both exactly wrong here. It also returns matplotlib
objects, which is a lot to load into a web server for a colour lookup. If it
ever grows classify support that keeps alpha, this should defer to it.

GDAL does the warp and writes the PNG. skimap's other option, rasterio plus
Pillow, is not in the QGIS-bundled Python.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from skimap import lyrx, paths

gdal.UseExceptions()

WEBMERCATOR_EPSG = 3857
WGS84_EPSG = 4326

# One of blue/green/red/black, the four this repo keeps beside each other -
# they are the exposure classes a routed corridor gets sorted into. The app
# does not score exposure, so it always draws the blue one.
STYLE = "blue.lyrx"

# An overlay is a picture, not a measurement, and a long tour's corridor can
# run to thousands of cells a side. Past this it is downsampled: it saves
# megabytes per route and nothing is legible at that scale anyway.
MAX_PIXELS = 2048


@lru_cache(maxsize=None)
def _style(name: str = STYLE) -> tuple[np.ndarray, np.ndarray]:
    """(upper bounds, RGBA rows) from a .lyrx, as two aligned arrays.

    A class covers everything above the previous bound up to and including
    its own, which is what searchsorted's "left" side gives back.
    """
    path = paths.STYLES / name
    # utf-8-sig: ArcGIS Pro writes these with a BOM.
    document = json.loads(path.read_text(encoding="utf-8-sig"))

    colorizer = document["layerDefinitions"][0]["colorizer"]
    kind = colorizer.get("type")
    if kind != "CIMRasterClassifyColorizer":
        raise ValueError(
            f"{name} is a {kind}; this reads CIMRasterClassifyColorizer. "
            "skimap.lyrx reads the stretch ones."
        )

    breaks = colorizer.get("classBreaks") or []
    if not breaks:
        raise KeyError(f"{name} has a classify colorizer with no classBreaks")

    bounds, colours = [], []
    for entry in breaks:
        # Pro picks the colour space per stop - a grey ramp saves as HSV, a
        # coloured one as RGB - so the stops go through lyrx rather than
        # being read as RGB and rejected the moment blue.lyrx is re-styled.
        try:
            colours.append(lyrx.rgba255(entry["color"]))
        except (KeyError, ValueError) as error:
            raise ValueError(f"{name}: {error}") from error
        bounds.append(float(entry["upperBound"]))

    return (np.array(bounds, dtype=np.float64),
            np.rint(np.array(colours, dtype=np.float64)).astype(np.uint8))


def to_png(corridor_tifs: Path | list[Path], png_path: Path) -> dict:
    """Write the corridor as an RGBA PNG. Returns its WGS84 bounds.

    Several GeoTIFFs - one per terrain leg of a route - are drawn as one
    picture; see `_merge`. The bounds are what Leaflet needs to place the
    image; they are the warped raster's own corners, so they describe where
    the picture goes, not where the route is.
    """
    if isinstance(corridor_tifs, Path):
        corridor_tifs = [corridor_tifs]
    source = (str(corridor_tifs[0]) if len(corridor_tifs) == 1
              else _merge(corridor_tifs))
    warped = gdal.Warp("", source, format="MEM",
                       dstSRS=f"EPSG:{WEBMERCATOR_EPSG}", resampleAlg="bilinear")

    longest = max(warped.RasterXSize, warped.RasterYSize)
    if longest > MAX_PIXELS:
        scale = MAX_PIXELS / longest
        warped = gdal.Translate(
            "", warped, format="MEM", resampleAlg="bilinear",
            width=max(1, int(warped.RasterXSize * scale)),
            height=max(1, int(warped.RasterYSize * scale)),
        )

    band = warped.GetRasterBand(1)
    scores = band.ReadAsArray().astype(np.float64)

    nodata = band.GetNoDataValue()
    inside = np.isfinite(scores)
    if nodata is not None:
        inside &= ~np.isclose(scores, nodata)
    # Warping bilinearly across the nodata edge leaves a fringe of values
    # just under 0; they are not corridor and must not be drawn as its rim.
    inside &= scores > 0.0

    _write_rgba(png_path, _colorize(np.clip(scores, 0.0, 1.0), inside))
    return _bounds_wgs84(warped)


def _merge(tifs: list[Path]) -> gdal.Dataset:
    """Several corridor GeoTIFFs as one, still on their own grid, taking the
    higher score wherever two overlap - a leg that comes back over the
    ground another went out on keeps the better reading of it.

    The legs can lie far apart with a drive between them, so the merged grid
    is coarsened up front to at most MAX_PIXELS a side rather than built
    full size only for to_png to shrink it.
    """
    sources = [gdal.Open(str(tif)) for tif in tifs]
    west, south, east, north = np.inf, np.inf, -np.inf, -np.inf
    cell = np.inf
    for source in sources:
        x0, w, _, y0, _, h = source.GetGeoTransform()
        west, north = min(west, x0), max(north, y0)
        east = max(east, x0 + w * source.RasterXSize)
        south = min(south, y0 + h * source.RasterYSize)   # h is negative
        cell = min(cell, w)
    cell = max(cell, max(east - west, north - south) / MAX_PIXELS)

    merged = None
    for source in sources:
        on_grid = gdal.Warp("", source, format="MEM", outputBounds=(west, south, east, north),
                            xRes=cell, yRes=cell, resampleAlg="bilinear",
                            dstNodata=np.nan, outputType=gdal.GDT_Float32)
        scores = on_grid.GetRasterBand(1).ReadAsArray()
        # fmax keeps whichever is a number, so nodata on one never hides the
        # other's corridor.
        merged = scores if merged is None else np.fmax(merged, scores)

    out = gdal.GetDriverByName("MEM").Create("", merged.shape[1], merged.shape[0], 1,
                                             gdal.GDT_Float32)
    out.SetGeoTransform((west, cell, 0.0, north, 0.0, -cell))
    out.SetProjection(sources[0].GetProjection())
    band = out.GetRasterBand(1)
    band.SetNoDataValue(np.nan)
    band.WriteArray(merged)
    return out


def _colorize(scores: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Scores to an (h, w, 4) RGBA image, through the style's class breaks."""
    bounds, colours = _style()

    classes = np.searchsorted(bounds, scores, side="left")
    np.clip(classes, 0, len(bounds) - 1, out=classes)

    rgba = colours[classes]
    # Outside the corridor nothing is drawn at all - the style's own
    # noDataColor is transparent white, which comes to the same thing.
    rgba[~inside] = 0
    return rgba


def _write_rgba(png_path: Path, rgba: np.ndarray) -> None:
    """The PNG driver is copy-only, so the image is built in memory first."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = rgba.shape[:2]

    image = gdal.GetDriverByName("MEM").Create("", width, height, 4, gdal.GDT_Byte)
    for index in range(4):
        image.GetRasterBand(index + 1).WriteArray(rgba[..., index])

    gdal.GetDriverByName("PNG").CreateCopy(str(png_path), image)


def _bounds_wgs84(dataset: gdal.Dataset) -> dict:
    origin_x, pixel_w, _, origin_y, _, pixel_h = dataset.GetGeoTransform()
    west, north = origin_x, origin_y
    east = origin_x + pixel_w * dataset.RasterXSize
    south = origin_y + pixel_h * dataset.RasterYSize   # pixel_h is negative

    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(WEBMERCATOR_EPSG)
    target.ImportFromEPSG(WGS84_EPSG)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)

    west_deg, south_deg, _ = transform.TransformPoint(west, south)
    east_deg, north_deg, _ = transform.TransformPoint(east, north)
    return {"west": west_deg, "south": south_deg,
            "east": east_deg, "north": north_deg}
