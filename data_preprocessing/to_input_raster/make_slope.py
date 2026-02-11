from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess

def make_slope(area_dir: Path) -> Path:
    dem = area_dir / "input" / "DEM.tif"
    out = area_dir / "input" / "slope.tif"

    if not dem.exists():
        raise FileNotFoundError(f"Missing DEM: {dem}")

    if out.exists():
        return out

    gdaldem = os.environ.get("GDALDEM") or shutil.which("gdaldem")
    if not gdaldem:
        raise RuntimeError(
            "Could not find gdaldem on PATH. Install GDAL (brew install gdal) "
            "or set GDALDEM to full path of gdaldem."
        )

    cmd = [
        gdaldem, "slope",
        str(dem),
        str(out),
        "-s", "1.0",
        "-compute_edges",
    ]
    subprocess.run(cmd, check=True)
    return out