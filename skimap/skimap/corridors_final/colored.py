"""data/colored_corridors from the final corridor set.

`corridor_review colored-corridors` paints one corridor per old tour. Once
the final set is built, the corridors are the merged, renumbered ones: a
tour digitized in two pieces is one corridor in one colour, the most severe
of its pieces (build.Corridor.colour). This paints those, through the same
overlap.write_classes, so the four class rasters - and everything that
reads them: the app's tiles, corridor_track_coverage - describe exactly the
set in corridors_final.gpkg.

It reads the built output, not the review. What gets coloured is then
always what was built, with the ids it was built with, never a fresh
decision that might have moved since.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from osgeo import ogr

from skimap import overlap, paths
from skimap.corridors_final import build as build_module

ogr.UseExceptions()


def write(final_dir: Optional[Path] = None, out_dir: Optional[Path] = None, *,
          allow_draft: bool = False) -> dict[str, Path]:
    final_dir = Path(final_dir) if final_dir else paths.CORRIDORS_FINAL
    out_dir = Path(out_dir) if out_dir else paths.COLORED_CORRIDORS

    summary = json.loads((final_dir / build_module.SUMMARY).read_text(encoding="utf-8"))
    if not summary.get("complete") and not allow_draft:
        raise SystemExit(f"{final_dir} is a draft build - not painting "
                         f"{out_dir} from it (--draft to do it anyway)")

    datasource = ogr.Open(str(final_dir / build_module.GPKG))
    layer = datasource.GetLayerByName("routes")
    lines: dict[int, overlap.Line] = {}
    corridors: dict[int, Path] = {}
    for feature in layer:
        corridor_id = feature.GetField("corridor_id")
        geometry = feature.GetGeometryRef()
        if geometry.GetGeometryType() != ogr.wkbLineString:
            # overlap measures along one line; a branching merge has none.
            raise SystemExit(f"corridor {corridor_id}: route is "
                             f"{geometry.GetGeometryName()}, overlap needs one line")
        lines[corridor_id] = overlap.make_line(corridor_id, feature.GetField("colour"),
                                               geometry.GetPoints())
        corridors[corridor_id] = (final_dir / build_module.TIF_DIR
                                  / f"{corridor_id:04d}.tif")
    datasource = None

    missing = [c for c, p in corridors.items() if not p.is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} corridor tifs missing, e.g. {missing[:5]}")

    written = overlap.write_classes(lines, corridors, out_dir)
    # Statistics ArcGIS cached for the previous rasters would now be wrong.
    for path in written.values():
        stale = path.with_name(path.name + ".aux.xml")
        if stale.exists():
            stale.unlink()
    print(f"\n{len(lines)} final corridors -> {out_dir}")
    for colour, path in written.items():
        print(f"  {colour}: {path.name}")
    return written
