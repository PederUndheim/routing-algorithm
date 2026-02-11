from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling


ResamplingName = Literal["nearest", "bilinear", "cubic", "average"]


def resample_raster_to_reference(
    *,
    src_path: Path,
    ref_path: Path,
    dst_path: Path,
    resampling: ResamplingName = "bilinear",
    dst_nodata: float = -9999.0,
    dst_dtype: str = "float32",
    compress: str = "LZW",
) -> Path:
    """
    Reproject + resample src raster to match ref raster grid exactly:
    - same CRS
    - same transform
    - same width/height

    This is the rasterio equivalent of: "warp to template".
    """

    resampling_map = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "average": Resampling.average,
    }
    rs = resampling_map.get(resampling, Resampling.bilinear)

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(ref_path) as ref:
        ref_profile = ref.profile.copy()
        dst_crs = ref.crs
        dst_transform = ref.transform
        dst_height = ref.height
        dst_width = ref.width

    with rasterio.open(src_path) as src:
        src_band1 = src.read(1)
        src_nodata = src.nodata

        # destination array
        dst_data = np.full((dst_height, dst_width), dst_nodata, dtype=np.dtype(dst_dtype))

        reproject(
            source=src_band1,
            destination=dst_data,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=dst_nodata,
            resampling=rs,
        )

    # write with ref grid metadata
    ref_profile.update(
        dtype=dst_dtype,
        count=1,
        nodata=dst_nodata,
        compress=compress,
    )

    # Optional but nice for performance
    if "tiled" not in ref_profile:
        ref_profile["tiled"] = True

    with rasterio.open(dst_path, "w", **ref_profile) as dst:
        dst.write(dst_data, 1)

    return dst_path
