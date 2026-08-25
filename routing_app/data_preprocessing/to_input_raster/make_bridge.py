from __future__ import annotations

from pathlib import Path

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas
from data_preprocessing.utils.to_raster import _which, _run



def intersect_rasters(river: Path, tractor: Path, out: Path) -> Path:
    """
    Creates intersection raster:
    1 where river>0 AND tractorroad_trail>0
    0 elsewhere
    """
    gdal_calc = _which("gdal_calc.py")

    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        gdal_calc,
        "-A", str(river),
        "-B", str(tractor),
        "--calc=(A>0)*(B>0)",
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

        print(f"\n=== Bridge calculation for {area.area_id} ===")

        area_dir = cfg.areas_root / area.area_id
        input_dir = area_dir / "input"

        river = input_dir / "river.tif"
        tractor = input_dir / "tractorroad_trail.tif"
        out = input_dir / "bridge.tif"

        if not river.exists():
            print(f"Skipping {area.area_id}: river.tif missing")
            continue

        if not tractor.exists():
            print(f"Skipping {area.area_id}: tractorroad_trail.tif missing")
            continue

        intersect_rasters(river, tractor, out)

        print("Wrote:", out)


if __name__ == "__main__":
    main()
