from __future__ import annotations

from pathlib import Path

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas
from data_preprocessing.utils.to_raster import _which, _run


RIVER_CLASS = 1
BRIDGE_CLASS = 2


def combine_rasters(river: Path, bridge: Path, out: Path) -> Path:
    """
    Creates a classified river-with-bridge raster:
    0 = no river
    1 = river
    2 = bridge crossing on river
    """
    gdal_calc = _which("gdal_calc.py")

    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        gdal_calc,
        "-A", str(river),
        "-B", str(bridge),
        f"--calc=(({RIVER_CLASS})*(A>0)*(B<=0)) + (({BRIDGE_CLASS})*(B>0))",
        "--type=Byte",
        "--NoDataValue=0",
        "--overwrite",
        "--outfile", str(out),
    ]

    _run(cmd)
    return out


def main() -> None:
    cfg = load_config()

    for area in iter_areas(cfg.study_areas, cfg.crs_epsg):
        print(f"\n=== River with bridge for {area.area_id} ===")

        input_dir = cfg.areas_root / area.area_id / "input"
        river = input_dir / "river.tif"
        bridge = input_dir / "bridge.tif"
        out = input_dir / "river_with_bridge.tif"

        if not river.exists():
            print(f"Skipping {area.area_id}: river.tif missing")
            continue

        if not bridge.exists():
            print(f"Skipping {area.area_id}: bridge.tif missing")
            continue

        combine_rasters(river, bridge, out)
        print("Wrote:", out)


if __name__ == "__main__":
    main()