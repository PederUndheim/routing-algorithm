import rasterio
import numpy as np

from typing import Dict
from pathlib import Path

from backend import config
from backend.file_handler.area_paths import AreaPaths

OUTPUT_NODATA = -9999.0

# Parameters to weibull-fit for travel distance danger
LAMBDA = 0.016   # m^-1
ALPHAW = 0.82    # shape param

def _linear_rescale_on_mask(src, mask, in_min, in_max, out_min, out_max):
    """Linearly rescale values of src on mask from [in_min,in_max] → [out_min,out_max]."""
    out = src.astype(np.float32, copy=True)
    if not np.any(mask): 
        return out
    
    rng = float(in_max - in_min)
    if rng <= 0:
        out[mask] = np.float32(0.5 * (out_min + out_max))
        return out
    
    v = np.clip(src, in_min, in_max)
    scaled = (v - in_min) / rng
    out_vals = out_min + scaled * (out_max - out_min)
    out[mask] = out_vals[mask].astype(np.float32)
    return out


def build_pra_runout_layer(paths: AreaPaths, inputs: Dict[str, Path]) -> Path:

    # Target ranges
    runout_min = config.PRA_RUNOUT_COMBINED_PARAMS["runout_min"]
    runout_max = config.PRA_RUNOUT_COMBINED_PARAMS["runout_max"]
    release_min = config.PRA_RUNOUT_COMBINED_PARAMS["release_min"]
    release_max = config.PRA_RUNOUT_COMBINED_PARAMS["release_max"]
    
    # Paths from area inputs
    travel_distance_path = inputs["travel_distance"]
    pra_raw_path = inputs["pra_raw"]

    # Output path in this area
    output_path = paths.input / "pra_runout_combined.tif"

    with rasterio.open(str(travel_distance_path)) as td_src, rasterio.open(str(pra_raw_path)) as pra_src:
        distance = td_src.read(1).astype(np.float32)
        pra_raw = pra_src.read(1).astype(np.float32)

        # Initialize output with NoData
        out = np.full(distance.shape, OUTPUT_NODATA, dtype=np.float32)

        # Masks
        is_release = (pra_raw >= 0.15)
        is_runout = (~is_release) & (distance < 10000) & (distance > 0)

        # RELEASE: PRA [0.15..0.99] -> [release_min..release_max]
        release_scaled = _linear_rescale_on_mask(
            pra_raw, is_release, 0.15, 0.99, release_min, release_max
        )
        out[is_release] = release_scaled[is_release]

        # RUNOUT: f(x) then [0..0.99] -> [runout_min..runout_max]
        fx = np.exp(-np.power(LAMBDA * distance.astype(np.float64), ALPHAW)).astype(np.float32)
        runout_scaled = _linear_rescale_on_mask(
            fx, is_runout, 0.0, 0.99, runout_min, runout_max
        )
        out[is_runout] = runout_scaled[is_runout]

        # Write output (use pra_raw as reference for georeferencing)
        meta = pra_src.meta.copy()
        meta.update(dtype="float32", count=1, compress="lzw", nodata=OUTPUT_NODATA)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(str(output_path), "w", **meta) as dst:
            dst.write(out, 1)

    print("Raster saved:", output_path)
    return output_path