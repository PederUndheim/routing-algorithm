from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import shutil
import tempfile


@dataclass(frozen=True)
class RasterizeSpec:
    src_vector: Path
    src_layer: str | None = None 
    burn_value: float | None = 1.0
    attribute: str | None = None  # if set, uses -a instead of -burn
    where: str | None = None
    all_touched: bool = True
    dtype: str = "Byte"           # Byte, UInt16, Float32, etc.
    nodata: float = 0.0           # nodata for masks
    init: float = 0.0             # initial value for raster
    out_name: str = "out.tif"     # file name inside output dir


def _which(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"{name} not found. Install gdal (brew install gdal) and ensure it is on PATH.")
    return p


def _run(cmd: list[str]) -> None:
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)



def make_template_raster_for_area(
    *,
    area_polygon_gpkg: Path,
    area_where: str,
    out_template: Path,
    crs_epsg: int,
    pixel_size: float,
    nodata: float,
) -> Path:
    """
    Creates an aligned template raster for one study area polygon.
    The raster is cropped to the polygon extent and masked to polygon (outside = nodata).
    """
    gdalwarp = _which("gdalwarp")
    gdal_rasterize = _which("gdal_rasterize")

    out_template.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        raw = td / "template_raw.tif"

        # 1) Rasterize the polygon to create a raster with the right extent/resolution
        # -tr sets resolution
        # -tap aligns pixels to resolution grid
        # -te comes implicitly from rasterize using vector extent, but we want exact crop+mask,
        # so we rasterize full extent first, then cutline mask via warp below.
        cmd_rast = [
            gdal_rasterize,
            "-of", "GTiff",
            "-a_nodata", str(nodata),
            "-init", str(nodata),
            "-ot", "Float32",
            "-tr", str(pixel_size), str(pixel_size),
            "-tap",
            "-a_srs", f"EPSG:{crs_epsg}",
            "-burn", "1",
        ]

        if area_where:
            cmd_rast += ["-where", area_where]

        cmd_rast += [
            str(area_polygon_gpkg),
            str(raw),
        ]
        _run(cmd_rast)

        # 2) Mask to polygon and enforce CRS using cutline
        # -crop_to_cutline ensures tight bounds
        cmd_warp = [
            gdalwarp,
            "-t_srs", f"EPSG:{crs_epsg}",
            "-cutline", str(area_polygon_gpkg),
            "-cwhere", area_where,
            "-crop_to_cutline",
            "-dstnodata", str(nodata),
            "-tr", str(pixel_size), str(pixel_size),
            "-tap",
            "-overwrite",
            str(raw),
            str(out_template),
        ]
        _run(cmd_warp)

    return out_template


def rasterize_vector_to_template(
    *,
    spec: RasterizeSpec,
    template: Path,
    out_raster: Path,
    crs_epsg: int,
) -> Path:
    gdal_rasterize = _which("gdal_rasterize")

    out_raster.parent.mkdir(parents=True, exist_ok=True)

    # Read template grid (extent + size) so gdal_rasterize can create an aligned output
    gdalinfo = _which("gdalinfo")
    info = subprocess.run(
        [gdalinfo, "-json", str(template)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    import json
    j = json.loads(info)
    size_x, size_y = j["size"]
    ulx, uly = j["cornerCoordinates"]["upperLeft"]
    lrx, lry = j["cornerCoordinates"]["lowerRight"]

    cmd = [
        gdal_rasterize,
        "-of", "GTiff",
        "-ot", spec.dtype,
        "-a_nodata", str(spec.nodata),
        "-init", str(spec.init),
        "-a_srs", f"EPSG:{crs_epsg}",
        "-te", str(ulx), str(lry), str(lrx), str(uly),
        "-ts", str(size_x), str(size_y),
    ]

    if spec.all_touched:
        cmd += ["-at"]

    if spec.where:
        cmd += ["-where", spec.where]

    if spec.attribute:
        cmd += ["-a", spec.attribute]
    else:
        cmd += ["-burn", str(spec.burn_value)]

    if spec.src_layer:
        cmd += ["-l", spec.src_layer]

    cmd += [str(spec.src_vector), str(out_raster)]

    _run(cmd)
    return out_raster



def apply_area_mask(
    *,
    src_raster: Path,
    area_polygon_gpkg: Path,
    area_where: str,
    out_raster: Path,
    crs_epsg: int,
    nodata: float,
) -> Path:
    """
    Masks a raster to the study area polygon (outside becomes nodata).
    """
    gdalwarp = _which("gdalwarp")
    out_raster.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        gdalwarp,
        "-t_srs", f"EPSG:{crs_epsg}",
        "-cutline", str(area_polygon_gpkg),
        "-cwhere", area_where,
        "-crop_to_cutline",
        "-dstnodata", str(nodata),
        "-overwrite",
        str(src_raster),
        str(out_raster),
    ]
    _run(cmd)
    return out_raster
