from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas


def _find_gdaldem() -> str:
    gdaldem = os.environ.get("GDALDEM") or shutil.which("gdaldem")
    if not gdaldem:
        raise RuntimeError(
            "Could not find gdaldem on PATH. Install GDAL (brew install gdal) "
            "or set GDALDEM to full path of gdaldem."
        )
    return gdaldem


def make_slope_for_area(area_dir: Path, *, force: bool = False) -> Path:
    dem = area_dir / "input" / "DEM.tif"
    out = area_dir / "input" / "slope.tif"

    if not dem.exists():
        raise FileNotFoundError(f"Missing DEM: {dem}")

    if out.exists() and not force:
        return out

    gdaldem = _find_gdaldem()

    if out.exists() and force:
        out.unlink()

    cmd = [
        gdaldem, "slope",
        str(dem),
        str(out),
        "-s", "1.0",
        "-compute_edges",
        "-of", "GTiff",
        "-co", "COMPRESS=DEFLATE",
        "-co", "TILED=YES",
        "-co", "BIGTIFF=IF_SAFER",
    ]
    subprocess.run(cmd, check=True)
    return out


def main(
    *,
    region: Optional[str] = None,
    area_ids: Optional[Sequence[str]] = None,
    force: bool = False,
) -> None:
    cfg = load_config()

    ok = skipped = missing = failed = 0

    for area in iter_areas(cfg.study_areas, crs_epsg=cfg.crs_epsg, region=region, area_ids=area_ids):
        area_dir = cfg.areas_root / area.area_id
        dem = area_dir / "input" / "DEM.tif"
        out = area_dir / "input" / "slope.tif"

        if not dem.exists():
            print(f"SKIP (missing DEM): {area.area_id}")
            missing += 1
            continue

        if out.exists() and not force:
            skipped += 1
            continue

        try:
            make_slope_for_area(area_dir, force=force)
            print(f"OK: {area.area_id} -> {out}")
            ok += 1
        except Exception as e:
            print(f"FAILED: {area.area_id}: {e}")
            failed += 1

    print(f"Done. OK={ok} skipped={skipped} missing_dem={missing} failed={failed}")


if __name__ == "__main__":
    main(force=True)

