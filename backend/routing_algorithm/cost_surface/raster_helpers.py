from pathlib import Path
from typing import Union

import numpy as np
import rasterio

PathLike = Union[str, Path]


def read_raster(path: PathLike) -> tuple[np.ndarray, dict]:
    """Read raster as float32, propagate nodata as np.nan."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Raster not found: {p}")

    with rasterio.open(str(p)) as src:
        arr = src.read(1)
        profile = src.profile
        nodata = src.nodata

    arr = arr.astype(np.float32, copy=False)
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return arr, profile


def read_mask(path: PathLike) -> np.ndarray:
    """Return boolean mask (True where feature exists)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mask raster not found: {p}")

    with rasterio.open(str(p)) as src:
        band = src.read(1)
        nodata = src.nodata

    if nodata is not None:
        band = np.where(band == nodata, 0, band)
    return (band != 0)


def debug_layer_save(arr: np.ndarray, filename: str, profile: dict, output_dir: Path):
    """Save an intermediate array for debugging and visualization."""
    debug_dir = output_dir
    debug_dir.mkdir(parents=True, exist_ok=True)
    output_path = debug_dir / filename

    prof = profile.copy()
    prof.update(dtype=arr.dtype, count=1, compress='lzw', nodata=None)
    with rasterio.open(output_path, 'w', **prof) as dst:
        dst.write(arr, 1)
    print(f"Debug layer saved to {output_path}")