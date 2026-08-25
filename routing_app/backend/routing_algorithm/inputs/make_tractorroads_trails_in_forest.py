from pathlib import Path
import rasterio
import numpy as np

OUTPUT_NODATA = -9999.0


def build_tractor_trails_in_forest(paths, inputs):
    """
    Build a mask where tractor roads/trails are kept only inside forest.

    Expects:
      inputs["tractorroad_trail"]
      inputs["forest"]

    Writes:
      paths.input / "tractorroad_trail_in_forest.tif"
    """

    tractorroad_trail_path = inputs["tractorroad_trail"]
    forest_path = inputs["forest"]

    out_path = paths.input / "tractorroad_trail_in_forest.tif"

    with rasterio.open(str(tractorroad_trail_path)) as tt_src, rasterio.open(str(forest_path)) as for_src:
        tractorroad_trail = tt_src.read(1).astype(np.float32, copy=False)
        forest = for_src.read(1).astype(np.float32, copy=False)

        if tractorroad_trail.shape != forest.shape:
            raise ValueError("tractorroad_trail and forest must have same shape")

        # Start with all NoData
        out = np.full(tractorroad_trail.shape, OUTPUT_NODATA, dtype=np.float32)

        # Keep tractorroads/trails only where forest exists
        mask = forest > 0
        out[mask] = tractorroad_trail[mask]

        # Write output (copy georeferencing from tractorroads/trails)
        meta = tt_src.meta.copy()
        meta.update(dtype="float32", count=1, compress="lzw", nodata=OUTPUT_NODATA)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(str(out_path), "w", **meta) as dst:
            dst.write(out, 1)

    print("Raster saved:", out_path)
    return out_path