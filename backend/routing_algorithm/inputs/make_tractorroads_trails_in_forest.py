from pathlib import Path
import rasterio
import numpy as np

OUTPUT_NODATA = -9999.0


def build_tractor_trails_in_forest(paths, inputs):
    """
    Build a mask where tractor roads/trails are kept only inside forest.

    Expects:
      inputs["tractorroads_trails"]
      inputs["forest"]

    Writes:
      paths.input / "tractorroads_trails_in_forest.tif"
    """

    tractorroads_trails_path = inputs["tractorroads_trails"]
    forest_path = inputs["forest"]

    out_path = paths.input / "tractorroads_trails_in_forest.tif"

    with rasterio.open(str(tractorroads_trails_path)) as tt_src, rasterio.open(str(forest_path)) as for_src:
        tractorroads_trails = tt_src.read(1).astype(np.float32, copy=False)
        forest = for_src.read(1).astype(np.float32, copy=False)

        if tractorroads_trails.shape != forest.shape:
            raise ValueError("tractorroads_trails and forest must have same shape")

        # Start with all NoData
        out = np.full(tractorroads_trails.shape, OUTPUT_NODATA, dtype=np.float32)

        # Keep tractorroads/trails only where forest exists
        mask = forest > 0
        out[mask] = tractorroads_trails[mask]

        # Write output (copy georeferencing from tractorroads/trails)
        meta = tt_src.meta.copy()
        meta.update(dtype="float32", count=1, compress="lzw", nodata=OUTPUT_NODATA)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(str(out_path), "w", **meta) as dst:
            dst.write(out, 1)

    print("Raster saved:", out_path)
    return out_path