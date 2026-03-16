from __future__ import annotations

import shutil
from pathlib import Path

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas

DEM_SRC_NAME = "dem.tif"             
COST_SRC_NAME = "cost_surface.tif"
LAKE_SRC_NAME = "lake.tif"
GLACIER_SRC_NAME = "glacier.tif"
RIVER_SRC_NAME = "river.tif"
RIVER_WITH_BRIDGE_SRC_NAME = "river_with_bridge.tif"
TRACKS_SRC_NAME = "tracks.tif"
FOREST_SRC_NAME = "forest.tif"


def copy2(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    cfg = load_config()

    project_root = Path(__file__).resolve().parents[2]
    runtime_root = project_root / "data" / "runtime" / "areas"

    runtime_root.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0

    for area in iter_areas(cfg.study_areas, cfg.crs_epsg):
        area_id = area.area_id

        src_input_dir = cfg.areas_root / area_id / "input"
        src_cost_surface_dir = cfg.areas_root / area_id / "output" / "cost_surface"
        dem_src = src_input_dir / DEM_SRC_NAME
        cost_src = src_cost_surface_dir / COST_SRC_NAME
        lake_src = src_input_dir / LAKE_SRC_NAME
        glacier_src = src_input_dir / GLACIER_SRC_NAME
        river_src = src_input_dir / RIVER_SRC_NAME
        river_with_bridge_src = src_input_dir / RIVER_WITH_BRIDGE_SRC_NAME
        tracks_src = src_input_dir / TRACKS_SRC_NAME
        forest_src = src_input_dir / FOREST_SRC_NAME

        dst_area_dir = runtime_root / area_id
        dem_dst = dst_area_dir / "dem.tif"
        cost_dst = dst_area_dir / "cost_surface.tif"
        lake_dst = dst_area_dir / "lake.tif"
        glacier_dst = dst_area_dir / "glacier.tif"
        river_dst = dst_area_dir / "river.tif"
        river_with_bridge_dst = dst_area_dir / "river_with_bridge.tif"
        tracks_dst = dst_area_dir / "tracks.tif"
        forest_dst = dst_area_dir / "forest.tif"

        if not dem_src.exists():
            print(f"Skip {area_id}: missing DEM {dem_src}")
            skipped += 1
            continue

        if not cost_src.exists():
            print(f"Skip {area_id}: missing cost {cost_src}")
            skipped += 1
            continue

        if not lake_src.exists():
            print(f"Skip {area_id}: missing lake mask {lake_src}")
            skipped += 1
            continue

        if not glacier_src.exists():
            print(f"Skip {area_id}: missing glacier mask {glacier_src}")
            skipped += 1
            continue

        if not river_src.exists():
            print(f"Skip {area_id}: missing river mask {river_src}")
            skipped += 1
            continue

        if not river_with_bridge_src.exists():
            print(f"Skip {area_id}: missing river_with_bridge raster {river_with_bridge_src}")
            skipped += 1
            continue

        if not tracks_src.exists():
            print(f"Skip {area_id}: missing tracks raster {tracks_src}")
            skipped += 1
            continue

        if not forest_src.exists():
            print(f"Skip {area_id}: missing forest raster {forest_src}")
            skipped += 1
            continue

        copy2(dem_src, dem_dst)
        copy2(cost_src, cost_dst)
        copy2(lake_src, lake_dst)
        copy2(glacier_src, glacier_dst)
        copy2(river_src, river_dst)
        copy2(river_with_bridge_src, river_with_bridge_dst)
        copy2(tracks_src, tracks_dst)
        copy2(forest_src, forest_dst)

        print(
            f"Exported {area_id}: dem.tif, cost_surface.tif, lake.tif, glacier.tif, river.tif, river_with_bridge.tif, "
            "tracks.tif, forest.tif"
        )
        exported += 1

    print(f"\nDone. Exported {exported} areas. Skipped {skipped}.")
    print("Runtime root:", runtime_root)


if __name__ == "__main__":
    main()