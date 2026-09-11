"""Raw raster dumps -> one national dataset per theme.

A VRT is the default: it costs a few MB and no data duplication, and GDAL
reads through it as if it were one raster. Materialize a COG only when you
want a single portable file (see to_cog).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from osgeo import gdal

from skimap import config

gdal.UseExceptions()


def _run(cmd: Sequence[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def build_vrt(sources: Sequence[Path], out_path: Path) -> Path:
    """Virtual mosaic over `sources`.

    Source paths are written relative to the VRT, so moving the whole tree
    keeps it working - but moving the VRT away from its tiles breaks it.
    Keep the .vrt next to the tiles it points at.
    """
    if not sources:
        raise ValueError("No source rasters given")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    listing = out_path.with_suffix(".sources.txt")
    listing.write_text(
        "\n".join(os.path.relpath(s, out_path.parent) for s in sources),
        encoding="utf-8",
    )

    cwd = os.getcwd()
    try:
        os.chdir(out_path.parent)
        _run(["gdalbuildvrt", "-input_file_list", listing.name, "-overwrite", out_path.name])
    finally:
        os.chdir(cwd)

    listing.unlink()
    return out_path


_INT_RANGE = {"Int16": (-32768, 32767), "UInt16": (0, 65535), "Byte": (0, 255)}


def to_cog(
    src: Path,
    out_path: Path,
    *,
    dtype: str | None = None,
    scale: float | None = None,
    compress: str = "DEFLATE",
    predictor: int | None = None,
    srcwin: Sequence[int] | None = None,
    resampling: str = "CUBIC",
) -> Path:
    """Materialize a virtual or tiled source as one compressed COG.

    Worth it when the sources overlap: the overlap is written once, so the
    result is smaller than the tiles it replaces.

    `resampling` builds the internal overviews. CUBIC is right for a
    continuous surface; use NEAREST for anything where an averaged pixel
    would be a value that does not exist. A cost surface is the second kind
    - blending a 5000 barrier with the 4 next to it invents a walkable
    coastline that is only there at low zoom.

    `scale` stores a float source as integers, `stored = value / scale`, and
    records the factor as the band's scale so readers recover the real
    value. Source nodata falls outside the representable range and clamps to
    the low end, which becomes the output nodata - so pick a `scale` that
    leaves the extremes of the dtype unused by real data.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if predictor is None:
        # 3 is the floating-point predictor; using 2 on float data barely
        # compresses, and 3 on integers is invalid.
        out_type = dtype
        if out_type is None:
            # Hold the dataset in a name: chaining off gdal.Open() frees it
            # before the band is read, and the band goes stale mid-expression.
            ds = gdal.Open(str(src))
            out_type = gdal.GetDataTypeName(ds.GetRasterBand(1).DataType)
            ds = None
        predictor = 3 if out_type.startswith("Float") else 2

    cmd = [
        "gdal_translate", src, out_path,
        "-of", "COG",
        "-co", f"COMPRESS={compress}",
        "-co", f"PREDICTOR={predictor}",
        "-co", f"RESAMPLING={resampling}",
        "-co", "BIGTIFF=YES",
        "-co", "NUM_THREADS=ALL_CPUS",
    ]
    if dtype:
        cmd += ["-ot", dtype]
    if scale is not None:
        if dtype not in _INT_RANGE:
            raise ValueError(f"scale needs an integer dtype, got {dtype!r}")
        lo, hi = _INT_RANGE[dtype]
        cmd += [
            "-scale", lo * scale, hi * scale, lo, hi,
            "-a_scale", scale,
            "-a_nodata", lo,
        ]
    if srcwin:
        cmd += ["-srcwin", *srcwin]
    _run(cmd)
    return out_path


def _bounds(path: Path) -> tuple[float, float, float, float]:
    ds = gdal.Open(str(path))
    gt = ds.GetGeoTransform()
    w, h = ds.RasterXSize, ds.RasterYSize
    out = (gt[0], gt[3] + h * gt[5], gt[0] + w * gt[1], gt[3])
    ds = None
    return out


def _snap_bounds(minx: float, miny: float, maxx: float, maxy: float) -> tuple[float, float, float, float]:
    """Grow bounds outward to the national pixel lattice."""
    import math

    ox, oy = config.RASTER_ORIGIN
    p = config.PIXEL_SIZE
    return (
        ox + math.floor((minx - ox) / p) * p,
        oy + math.floor((miny - oy) / p) * p,
        ox + math.ceil((maxx - ox) / p) * p,
        oy + math.ceil((maxy - oy) / p) * p,
    )


def warp_mosaic(
    sources: Sequence[Path],
    out_path: Path,
    *,
    resampling: str = "near",
    dtype: str | None = None,
    src_nodata: float | str | None = None,
    dst_nodata: float | str | None = None,
    compress: str = "DEFLATE",
    predictor: int = 2,
) -> Path:
    """Warp sources onto config.RASTER_ORIGIN's lattice and write one COG.

    Needed when sources do not share a pixel grid - a VRT cannot mosaic
    those, it can only stack them and let one win.

    Note this snaps with an explicit -te on the national lattice rather than
    -tap: -tap would snap to whole multiples of the pixel size, which is a
    different lattice from the one the DEM and friends already use.
    """
    if not sources:
        raise ValueError("No source rasters given")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmps: list[Path] = []

    bounds = [_bounds(s) for s in sources]
    te = _snap_bounds(
        min(b[0] for b in bounds), min(b[1] for b in bounds),
        max(b[2] for b in bounds), max(b[3] for b in bounds),
    )
    print(f"target grid: x {te[0]:.0f}..{te[2]:.0f}  y {te[1]:.0f}..{te[3]:.0f} "
          f"(offset {te[0] % config.PIXEL_SIZE:g}, {te[1] % config.PIXEL_SIZE:g})")

    # One gdalwarp per source, NOT one call with many: `gdalwarp -of VRT`
    # silently keeps only the first source. Warping each separately with the
    # same -tr/-tap puts them all on one lattice, which is what lets
    # gdalbuildvrt mosaic them without resampling or half-pixel rounding.
    try:
        for i, src in enumerate(sources):
            tmp = out_path.with_suffix(f".warp{i}.vrt")
            cmd = [
                "gdalwarp", "-of", "VRT",
                "-t_srs", f"EPSG:{config.CRS_EPSG}",
                "-tr", config.PIXEL_SIZE, config.PIXEL_SIZE,
                "-te", *te,
                "-r", resampling,
                "-overwrite",
            ]
            # Pass src_nodata="None" to ignore a source's own declaration -
            # some files declare a value their band type cannot even hold.
            if src_nodata is not None:
                cmd += ["-srcnodata", src_nodata]
            if dst_nodata is not None:
                cmd += ["-dstnodata", dst_nodata]
            cmd += [src, tmp]
            _run(cmd)
            tmps.append(tmp)

        mosaic = out_path.with_suffix(".mosaic.vrt")
        _run(["gdalbuildvrt", "-overwrite", mosaic, *tmps])
        tmps.append(mosaic)

        to_cog(mosaic, out_path, dtype=dtype, compress=compress, predictor=predictor)
    finally:
        for t in tmps:
            t.unlink(missing_ok=True)
    return out_path


def describe(path: Path) -> dict:
    """Size, dtype, resolution and value range of a raster. Stats are approximate."""
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    gt = ds.GetGeoTransform()
    lo, hi, mean, std = band.ComputeStatistics(True)  # approx_ok, uses overviews
    info = {
        "size_px": (ds.RasterXSize, ds.RasterYSize),
        "pixel_m": (gt[1], abs(gt[5])),
        "dtype": gdal.GetDataTypeName(band.DataType),
        "nodata": band.GetNoDataValue(),
        "epsg": ds.GetSpatialRef().GetAuthorityCode(None) if ds.GetSpatialRef() else None,
        "min": lo,
        "max": hi,
        "mean": mean,
        "std": std,
    }
    ds = None
    return info
