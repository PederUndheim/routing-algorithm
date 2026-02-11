import numpy as np
import rasterio
from backend import config
from rasterio.warp import reproject, Resampling

def resample_tif_to_reference(src_path: str, ref_path: str, dst_path: str, resampling="bilinear"):
    resampling_map = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "average": Resampling.average,
    }
    rs = resampling_map.get(resampling, Resampling.bilinear)

    with rasterio.open(ref_path) as ref:
        ref_profile = ref.profile
        dst_crs = ref.crs
        dst_transform = ref.transform
        dst_height = ref.height
        dst_width = ref.width

    with rasterio.open(src_path) as src:
        src_data = src.read(1).astype(np.float32, copy=False)
        src_nodata = src.nodata

        dst_data = np.full((dst_height, dst_width), np.nan, dtype=np.float32)

        reproject(
            source=src_data,
            destination=dst_data,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=np.nan,
            resampling=rs,
        )

    out_profile = ref_profile.copy()
    out_profile.update(dtype=rasterio.float32, count=1, nodata=np.nan, compress="lzw")

    with rasterio.open(dst_path, "w", **out_profile) as dst:
        dst.write(dst_data, 1)

    print(f"Resampled raster written to {dst_path}")

    return dst_path


if __name__ == "__main__":
    resample_tif_to_reference(
        src_path="backend/data/raster/raw/tracks/tracks_isfjorden.tif",
        ref_path=config.REF_RASTER,
        dst_path="backend/data/raster/processed/tracks_resampled/tracks_isfjorden_resampled.tif",
        resampling="bilinear"
    )