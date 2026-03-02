from pathlib import Path
import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.warp import calculate_default_transform, reproject, Resampling



def corridor_tif_to_png(tif_path: Path, png_path: Path, threshold: float = 0.95) -> None:
    with rasterio.open(tif_path) as ds:
        arr = ds.read(1).astype(np.float32)
        nodata = ds.nodata

    mask = np.zeros(arr.shape, dtype=np.uint8)
    if nodata is not None:
        arr[arr == nodata] = np.nan

    mask[(~np.isnan(arr)) & (arr > threshold)] = 255

    # RGBA: color corridor pixels, transparent elsewhere
    rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
    rgba[..., 0] = 0x36  # R
    rgba[..., 1] = 0x7E  # G
    rgba[..., 2] = 0x98  # B
    rgba[..., 3] = mask  # alpha

    Image.fromarray(rgba, mode="RGBA").save(png_path)

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
                resampling=Resampling.nearest,
            )


def corridor_tif_3857_to_png(tif_3857: Path, png_path: Path, threshold: float = 0.95) -> None:
    with rasterio.open(tif_3857) as ds:
        arr = ds.read(1).astype(np.float32)
        nodata = ds.nodata

    if nodata is not None:
        arr = np.where(np.isclose(arr, nodata), np.nan, arr)

    mask = ((~np.isnan(arr)) & (arr > threshold)).astype(np.uint8) * 255

    rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
    rgba[..., 0] = 0x36
    rgba[..., 1] = 0x7E
    rgba[..., 2] = 0x98
    rgba[..., 3] = mask

    Image.fromarray(rgba, mode="RGBA").save(png_path)


def tif_3857_bounds_wgs84(tif_3857: Path) -> dict:
    with rasterio.open(tif_3857) as ds:
        b = ds.bounds

    to_wgs = Transformer.from_crs(WEBM, WGS84, always_xy=True)
    west, south = to_wgs.transform(b.left, b.bottom)
    east, north = to_wgs.transform(b.right, b.top)
    return {"west": west, "south": south, "east": east, "north": north}