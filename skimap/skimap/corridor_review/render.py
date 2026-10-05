r"""A corridor GeoTIFF, drawn in its own exposure colour, for a web map.

`route_one` writes a Float32 corridor on the EPSG:25833 grid: 1 on the
optimal line, falling to 0 at the edge of the slack band, nodata outside it.
Leaflet places an image by stretching it between two corners and does that in
Web Mercator, so the raster is warped to EPSG:3857 here rather than handed
over as it is - pinning a 25833 grid to WGS84 corners leans the corridor off
its own route by hundreds of metres this far north.

The colour is the point. Every panel in the review draws its corridor in the
class exposure.classify() gave it, so a glance across three panels shows both
where the lines went and what each one costs you: a green band and a black
band are telling you different things about the same tour. Styles come from
the four data/styles_arcgis colour files this repo already keeps beside each
other, so re-styling in ArcGIS Pro re-styles the review.

## Why this is not app.backend.corridor

That module does the same warp and reads the same .lyrx files, and this began
as a copy of it. It is not imported because the dependency would run the
wrong way: `app` imports `skimap`, and skimap importing back out of app would
make the package unusable without the web app beside it. The difference in
behaviour is small but real - that one always draws blue, because the app
does not score exposure, and this one takes the class as an argument.

If a third caller ever needs this, the answer is to lift it into skimap
proper and have both defer to it, not to copy it a second time.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, osr

from skimap import lyrx, paths

gdal.UseExceptions()

WEBMERCATOR_EPSG = 3857
WGS84_EPSG = 4326

# A corridor is a picture here, not a measurement, and a long tour's band can
# run to thousands of cells a side. Past this it is downsampled: it saves
# megabytes per panel and nothing is legible at that scale anyway. Lower than
# the app's 2048 because the review shows three or more of these at once.
MAX_PIXELS = 1280

CACHE = paths.DATA / "review" / "cache"


def _stale(cached: Path, *sources: Path) -> bool:
    """True if any source is newer than the cached file.

    A model is a path to output on disk, and that output gets rebuilt - a
    variant re-routed on a corrected config writes new corridors into the
    same directory. Keyed on model and fid alone, the cache would go on
    serving pictures of the corridors that used to be there, with nothing on
    screen to say so. That is worse than no cache: you would be comparing
    models using an image of a surface that no longer exists.
    """
    try:
        stamp = cached.stat().st_mtime
    except OSError:
        return True
    for source in sources:
        try:
            if source.stat().st_mtime > stamp:
                return True
        except OSError:
            continue
    return False


@lru_cache(maxsize=None)
def _style(colour: str) -> tuple[np.ndarray, np.ndarray]:
    """Upper bounds and RGBA rows from one colour's .lyrx, as aligned arrays.

    A class covers everything above the previous bound up to and including its
    own, which is what searchsorted's "left" side gives back.

    Which colour space a break is written in is Pro's choice, not the style
    author's - black.lyrx is a grey ramp and comes back as CIMHSVColor while
    its neighbours are CIMRGBColor - so the stops go through lyrx.rgba255
    rather than being read as RGB.
    """
    path = paths.STYLES / f"{colour}.lyrx"
    if not path.is_file():
        raise SystemExit(f"No style for {colour!r} at {path}")

    # utf-8-sig: ArcGIS Pro writes these with a BOM.
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    colorizer = document["layerDefinitions"][0]["colorizer"]

    kind = colorizer.get("type")
    if kind != "CIMRasterClassifyColorizer":
        raise ValueError(
            f"{path.name} is a {kind}; this reads CIMRasterClassifyColorizer"
        )

    breaks = colorizer.get("classBreaks") or []
    if not breaks:
        raise KeyError(f"{path.name} has a classify colorizer with no classBreaks")

    bounds, colours = [], []
    for entry in breaks:
        try:
            colours.append(lyrx.rgba255(entry["color"]))
        except (KeyError, ValueError) as error:
            raise ValueError(f"{path.name}: {error}") from error
        bounds.append(float(entry["upperBound"]))

    return (np.array(bounds, dtype=np.float64),
            np.rint(np.array(colours, dtype=np.float64)).astype(np.uint8))


def cached_png(model: str, fid: int, corridor_tif: Path,
               colour: str) -> tuple[Path, dict]:
    """The overlay for one corridor, rendering it only if it is not cached.

    Returns the PNG and its WGS84 bounds. The bounds are the warped raster's
    own corners - where the picture goes, not where the route is - and do not
    depend on the colour, so they are cached once per tour and shared by every
    class the corridor might be drawn in.
    """
    out_dir = CACHE / model
    png = out_dir / f"{fid}_{colour}.png"
    meta = out_dir / f"{fid}.json"

    if (png.is_file() and meta.is_file()
            and not _stale(png, Path(corridor_tif))):
        return png, json.loads(meta.read_text(encoding="utf-8"))

    out_dir.mkdir(parents=True, exist_ok=True)
    bounds = to_png(corridor_tif, png, colour=colour)
    meta.write_text(json.dumps(bounds), encoding="utf-8")
    return png, bounds


def cached_bounds(model: str, fid: int, corridor_tif: Path) -> dict:
    """Where a corridor's picture goes, without drawing it.

    The page needs bounds for all of a tour's panels before it can place any
    overlay, but rendering every PNG first would put three or four warps in
    the way of each keystroke. A VRT warp resolves the output geotransform
    from the transformer alone and reads no pixels, so this is metadata work.

    Written to the same `<fid>.json` that cached_png uses, so whichever runs
    first saves the other the trouble.
    """
    meta = CACHE / model / f"{fid}.json"
    if meta.is_file() and not _stale(meta, Path(corridor_tif)):
        return json.loads(meta.read_text(encoding="utf-8"))

    warped = gdal.Warp("", str(corridor_tif), format="VRT",
                       dstSRS=f"EPSG:{WEBMERCATOR_EPSG}", resampleAlg="bilinear")
    bounds = _bounds_wgs84(warped)

    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(bounds), encoding="utf-8")
    return bounds


def to_png(corridor_tif: Path, png_path: Path, *, colour: str = "blue") -> dict:
    """Write `corridor_tif` as an RGBA PNG in `colour`. Returns WGS84 bounds."""
    warped = gdal.Warp("", str(corridor_tif), format="MEM",
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
    # Warping bilinearly across the nodata edge leaves a fringe of values just
    # under 0; they are not corridor and must not be drawn as its rim.
    inside &= scores > 0.0

    _write_rgba(png_path, _colorize(np.clip(scores, 0.0, 1.0), inside, colour))
    return _bounds_wgs84(warped)


def _colorize(scores: np.ndarray, inside: np.ndarray, colour: str) -> np.ndarray:
    bounds, colours = _style(colour)
    classes = np.searchsorted(bounds, scores, side="left")
    np.clip(classes, 0, len(bounds) - 1, out=classes)
    rgba = colours[classes]
    # Outside the corridor nothing is drawn at all.
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


# --- GPS tracks ----------------------------------------------------------

# Magenta, because it has to sit on top of two ramps that already use most of
# the spectrum: NVE's slope runs green-yellow-orange-red, and a corridor is
# drawn in one of green/blue/red/black. Nothing in either is this hue.
TRACK_RGB = (255, 60, 224)

# Alpha carries the normalized density, but floored where there is any track
# at all - lifted from lab._tracks, and for its reason. The national scale
# starts at the 60th percentile of positive pixels, so a single passage
# normalizes to zero; on a plain ramp it would look identical to ground
# nobody has walked, and "somebody went here and it earned no discount" is
# exactly the case the overlay exists to show.
TRACK_ALPHA_FLOOR = 0.16
TRACK_ALPHA_SPAN = 0.62

TRACKS_CACHE = "_tracks"


def tracks_overlay(fid: int, corridor_tifs: list[Path]) -> Optional[tuple[Path, dict]]:
    """The GPS tracks over one tour, as an overlay, or None where there are none.

    Drawn once per tour over the union of its corridors' extents rather than
    once per panel: Leaflet places an image by its own bounds, so one picture
    lands correctly in every panel regardless of how far each model's
    corridor happens to reach.

    A tour can have no tracks near it, and that is an answer rather than a
    failure - so it is cached like any other, or every visit re-warps a
    national raster to find the same nothing. It is not the common case
    though: the national rasters reach about 56% of the *tiles*, but tours
    are digitized where people ski and tracks are where people went, so the
    two select for the same ground. Every tour in a 19-tour spread had them.
    """
    import numpy as np

    from skimap import config
    from skimap.data_preprocessing import tracks as track_scale

    out_dir = CACHE / TRACKS_CACHE
    png = out_dir / f"{fid}.png"
    meta_path = out_dir / f"{fid}.json"

    # The overlay's extent is the union of this tour's corridors, so rebuilt
    # corridors change it as well as the track raster itself.
    sources = [Path(p) for p in corridor_tifs]
    try:
        sources.append(paths.layer("tracks"))
    except FileNotFoundError:
        pass

    if meta_path.is_file() and not _stale(meta_path, *sources):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("empty"):
            return None
        if png.is_file():
            return png, meta

    extent = _union_extent(corridor_tifs)
    if extent is None:
        return None
    west, south, east, north = extent

    resolution = max(east - west, north - south) / MAX_PIXELS
    width = max(1, round((east - west) / resolution))
    height = max(1, round((north - south) / resolution))

    try:
        source = paths.layer("tracks")
    except FileNotFoundError:
        return None

    # "max", not bilinear: a track is one or two cells wide, and averaging it
    # down to this resolution would fade the thing being drawn out of the
    # picture. Taking the strongest cell in each output pixel keeps a thin
    # line visible at the width it is actually seen at.
    warped = gdal.Warp("", str(source), format="MEM", dstSRS=f"EPSG:{WEBMERCATOR_EPSG}",
                       outputBounds=(west, south, east, north),
                       width=width, height=height, resampleAlg="max", dstNodata=0)

    raw = warped.GetRasterBand(1).ReadAsArray()
    if raw is None:
        return None
    raw = np.nan_to_num(raw.astype(np.float64), nan=0.0)

    # What counts as a track at all is config's call, not this module's.
    present = raw >= float(config.TRACKS["min_density"])
    out_dir.mkdir(parents=True, exist_ok=True)

    bounds = _bounds_from_extent(west, south, east, north)
    if not present.any():
        meta_path.write_text(json.dumps({**bounds, "empty": True}), encoding="utf-8")
        return None

    unit = track_scale.normalize(raw, track_scale.load_scale())
    alpha = np.where(present, TRACK_ALPHA_FLOOR + TRACK_ALPHA_SPAN * unit, 0.0)

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for index, value in enumerate(TRACK_RGB):
        rgba[..., index] = value
    rgba[..., 3] = np.rint(np.clip(alpha, 0.0, 1.0) * 255.0).astype(np.uint8)

    _write_rgba(png, rgba)
    meta_path.write_text(json.dumps(bounds), encoding="utf-8")
    return png, bounds


def _union_extent(corridor_tifs: list[Path]) -> Optional[tuple[float, float, float, float]]:
    """The Web Mercator extent covering every one of these corridors.

    VRT warps, so this resolves each output geotransform from the transformer
    and reads no pixels.
    """
    boxes = []
    for path in corridor_tifs:
        if not Path(path).is_file():
            continue
        warped = gdal.Warp("", str(path), format="VRT",
                           dstSRS=f"EPSG:{WEBMERCATOR_EPSG}", resampleAlg="near")
        origin_x, pixel_w, _, origin_y, _, pixel_h = warped.GetGeoTransform()
        boxes.append((
            origin_x,
            origin_y + pixel_h * warped.RasterYSize,   # pixel_h is negative
            origin_x + pixel_w * warped.RasterXSize,
            origin_y,
        ))
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _bounds_from_extent(west: float, south: float,
                        east: float, north: float) -> dict:
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


def clear_cache(model: Optional[str] = None) -> int:
    """Delete rendered overlays. Returns how many files went."""
    root = CACHE / model if model else CACHE
    if not root.is_dir():
        return 0
    gone = 0
    for path in sorted(root.rglob("*")):
        if path.is_file():
            path.unlink()
            gone += 1
    return gone
