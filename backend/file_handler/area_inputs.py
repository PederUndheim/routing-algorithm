from pathlib import Path
from .area_paths import AreaPaths

def get_input_rasters(p: AreaPaths) -> dict[str, Path]:
    return {
        "dem": p.input / "dem.tif",                                                         # meters above sea level

        "slope": p.input / "slope.tif",                                                     # degrees (0-90)
        "curvature": p.input / "windshelter.tif",                                           # curvature (-1, 1), (from "ridges" to "bowls")
        "pra_runout_combined": p.input / "pra_runout_combined.tif",                         # avalance cost raster with runout (1-7.2) and release (7.2-99)

        "travel_distance": p.input / "FP_travel_distance.tif",                              # for building pra_runout_combined
        "pra_raw": p.input / "pra_raw.tif",                                                 # for building pra_runout_combined
        "forest": p.input / "number_of_stems_ha.tif",                                       # for building tractorroads_trails_in_forest

        "roads": p.input / "roads.tif",                                                     # 1 where roads
        "tractorroads_trails": p.input / "tractorroads_trails.tif",                         # 1 where tractor roads or trails
        "tractorroads_trails_forest": p.input / "tractorroads_trails_in_forest.tif",        # 1 where tractor roads or trails in forest
        "rivers": p.input / "river.tif",                                                    # 1 where rivers
        "bridges": p.input / "bridge.tif",                                                  # 1 where bridges

        "tracks": p.input / f"tracks_{p.area_id}.tif",                                      # real tracks usage raster for Isfjorden area
    }

