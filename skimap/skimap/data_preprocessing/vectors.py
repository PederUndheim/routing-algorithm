"""Raw vector dumps (FGDB, shapefile) -> one GeoPackage per theme.

Whole layers are carried over, not pre-filtered: which features count is a
cost-surface decision and lives in config.VECTOR_LAYERS, so it can change
without re-running this.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Sequence

from osgeo import ogr

from skimap import config

ogr.UseExceptions()


def _run(cmd: Sequence[str]) -> None:
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def list_layers(src: Path) -> list[tuple[str, int, str]]:
    """(name, feature count, geometry type) for each layer in a source."""
    ds = ogr.Open(str(src))
    if ds is None:
        raise RuntimeError(f"Could not open {src}")
    out = []
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayerByIndex(i)
        out.append((lyr.GetName(), lyr.GetFeatureCount(), ogr.GeometryTypeToName(lyr.GetGeomType())))
    ds = None
    return out


def to_gpkg(
    src: Path,
    out_path: Path,
    *,
    layer: Optional[str] = None,
    out_layer: Optional[str] = None,
    where: Optional[str] = None,
    assign_srs: bool = False,
    encoding: Optional[str] = None,
) -> Path:
    """Convert one layer into a GeoPackage in CRS_EPSG, 2D, with an index.

    `assign_srs` stamps CRS_EPSG on data that declares no SRS rather than
    reprojecting it - the FKB FGDB exports are already UTM33 but ship
    without a spatial reference, and reprojecting from "unknown" fails.

    Z is dropped: every consumer rasterizes these, and 3D coordinates only
    make the file bigger.

    `encoding` overrides a shapefile's .cpg when it lies. Note this does NOT
    help NVDB: its text was already transliterated to ASCII before export
    (the DBF literally holds "Kj2rvegen", "Kj.rebane"), so no encoding
    recovers it. Only its text fields are affected, and nothing here reads
    them - the filters in config.VECTOR_LAYERS are pure ASCII.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_layer = out_layer or out_path.stem

    cmd = ["ogr2ogr"]
    if encoding:
        cmd += ["-oo", f"ENCODING={encoding}"]
    cmd += [
        "-f", "GPKG", out_path, src,
        "-nln", out_layer,
        "-dim", "XY",
        "-nlt", "PROMOTE_TO_MULTI",
        "-lco", "SPATIAL_INDEX=YES",
        "-overwrite",
        "-progress",
    ]
    cmd += ["-a_srs" if assign_srs else "-t_srs", f"EPSG:{config.CRS_EPSG}"]
    if where:
        cmd += ["-where", where]
    if layer:
        cmd += [layer]

    _run(cmd)
    return out_path
