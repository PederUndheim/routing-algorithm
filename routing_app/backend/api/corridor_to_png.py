from pathlib import Path
import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.warp import calculate_default_transform, reproject, Resampling

WEBM = "EPSG:3857"
WGS84 = "EPSG:4326"


def warp_tif_to_3857(src_tif: Path, dst_tif: Path) -> None:
    with rasterio.open(src_tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, WEBM, src.width, src.height, *src.bounds
        )
        dst_profile = src.profile.copy()
        dst_profile.update(
            crs=WEBM,
            transform=transform,
            width=width,
            height=height,
            compress="deflate",
        )

        with rasterio.open(dst_tif, "w", **dst_profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=WEBM,
                resampling=Resampling.bilinear,
            )


def corridor_tif_3857_to_png(tif_3857: Path, png_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(tif_3857) as ds:
        arr = ds.read(1).astype(np.float32)
        nodata = ds.nodata

    # Mask nodata only
    if nodata is not None:
        valid_mask = ~np.isclose(arr, nodata)
    else:
        valid_mask = np.isfinite(arr)

    # Replace invalid values with 0 just for scaling
    arr_clean = np.where(valid_mask, arr, 0.0)

    # Normalize full value range
    vmin = np.nanmin(arr_clean[valid_mask])
    vmax = np.nanmax(arr_clean[valid_mask])

    norm = (arr_clean - vmin) / (vmax - vmin + 1e-9)
    norm = np.clip(norm, 0.0, 1.0)

    alpha = (norm * 255).astype(np.uint8)

    rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)

    rgba[..., 0] = 0x36
    rgba[..., 1] = 0x7E
    rgba[..., 2] = 0x98
    rgba[..., 3] = np.where(valid_mask, alpha, 0)

    Image.fromarray(rgba, mode="RGBA").save(png_path, optimize=True)


def tif_3857_bounds_wgs84(tif_3857: Path) -> dict:
    with rasterio.open(tif_3857) as ds:
        b = ds.bounds

    to_wgs = Transformer.from_crs(WEBM, WGS84, always_xy=True)
    west, south = to_wgs.transform(b.left, b.bottom)
    east, north = to_wgs.transform(b.right, b.top)
    return {"west": west, "south": south, "east": east, "north": north}