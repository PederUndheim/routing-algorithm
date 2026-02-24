from __future__ import annotations

import shutil
from pathlib import Path

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas

DEM_SRC_NAME = "dem.tif"              # or "DEM.tif"
COST_SRC_NAME = "cost_surface.tif"    # or your actual name


def copy2(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    cfg = load_config()

    project_root = Path(__file__).resolve().parents[2]
    runtime_root = project_root / "data" / "runtime" / "areas"

    # Recreate runtime folder fresh
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0

    for area in iter_areas(cfg.study_areas, cfg.crs_epsg):
        area_id = area.area_id

        src_input_dir = cfg.areas_root / area_id / "input"
        src_cost_surface_dir = cfg.areas_root / area_id / "output" / "cost_surface"
        dem_src = src_input_dir / DEM_SRC_NAME
        cost_src = src_cost_surface_dir / COST_SRC_NAME

        dst_area_dir = runtime_root / area_id
        dem_dst = dst_area_dir / "dem.tif"
        cost_dst = dst_area_dir / "cost_surface.tif"

        if not dem_src.exists():
            print(f"Skip {area_id}: missing DEM {dem_src}")
            skipped += 1
            continue

        if not cost_src.exists():
            print(f"Skip {area_id}: missing cost {cost_src}")
            skipped += 1
            continue

        copy2(dem_src, dem_dst)
        copy2(cost_src, cost_dst)

        print(f"Exported {area_id}: dem.tif and cost_surface.tif")
        exported += 1

    print(f"\nDone. Exported {exported} areas. Skipped {skipped}.")
    print("Runtime root:", runtime_root)


if __name__ == "__main__":
    main()