from pathlib import Path
from .area_paths import AreaPaths

def get_input_rasters(p: AreaPaths) -> dict[str, Path]:
    return {
        "dem": p.runtime_area_root / "dem.tif",                                                         # meters above sea level

        "slope": p.input / "slope.tif",                                                     # degrees (0-90)
        "curvature": p.input / "windshelter.tif",                                           # curvature (-1, 1), (from "ridges" to "bowls")
        "pra_runout_combined": p.input / "pra_runout_combined.tif",                         # avalance cost raster with runout (1-7.2) and release (7.2-99)

        "travel_distance": p.input / "travel_distance.tif",                              # for building pra_runout_combined
        "pra_raw": p.input / "pra_raw.tif",                                                 # for building pra_runout_combined
        "forest": p.input / "forest.tif",                                           # for building tractorroads_trails_in_forest

        "road": p.input / "road.tif",                                                       # 1 where roads
        "tractorroad_trail": p.input / "tractorroad_trail.tif",                             # 1 where tractor roads or trails
        "tractorroad_trail_forest": p.input / "tractorroad_trail_in_forest.tif",            # 1 where tractor roads or trails in forest
        "river": p.input / "river.tif",                                                     # 1 where rivers
        "ocean": p.input / "ocean.tif",                                                     # 1 where ocean
        "lake": p.input / "lake.tif",                                                       # 1 where lakes
        "glacier": p.input / "glacier.tif",                                                 # 1 where glaciers
        "bridge": p.input / "bridge.tif",                                                   # 1 where bridges

        "tracks": p.input / f"tracks.tif",                                                  # real tracks usage raster
    }

