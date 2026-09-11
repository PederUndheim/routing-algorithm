"""python -m skimap.segments.cli <command> --aoi <outline>

    template   the corridors reaching an outline, merged into one raster to
               draw on, plus the route centrelines and two empty layers to
               digitize into
    split      those drawings applied: one raster per class, ready for the
               green/blue/red/black .lyrx

Between the two you draw, in ArcGIS or QGIS:

    a LINE along a stretch of route sets that stretch's colour. The cut is
    perpendicular to the route and spans the corridor's full width, so the
    line only has to run roughly along the right part - and overshoot past
    the ends of a route rather than stopping short of them.

    a POLYGON sets the colour of whatever corridor is under it, exactly as
    drawn. Use one where a perpendicular cut takes ground it should not:
    side lobes, alternative lines, a short stretch in a wide corridor.

Set `colour` on everything you draw - 1 green, 2 blue, 3 red, 4 black, or
the names. Leave `tour_fid` at 0 unless two routes run close enough that
split reports the choice as ambiguous.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from osgeo import ogr


def _out_dir(args, aoi_path: Path) -> Path:
    from skimap import paths

    return Path(args.out) if args.out else paths.segments(aoi_path.stem)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="skimap.segments", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("template", "merge the corridors here and make the drawing layers"),
                            ("split", "apply the drawings, one raster per class")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--aoi", type=Path, required=True,
                       help="polygon bounding the area to work on")
        p.add_argument("--layer", help="layer name, for multi-layer sources")
        p.add_argument("--pad", type=float, default=0.0,
                       help="metres of margin around the outline")
        p.add_argument("--out", type=Path,
                       help="working directory (default data/segments/<aoi name>)")
        p.add_argument("--routes", type=Path,
                       help="routes.gpkg (default data/routing_output/routes.gpkg)")
        p.add_argument("--corridors", type=Path,
                       help="per-tour corridors (default data/routing_output/corridors)")
        p.add_argument("--no-clip", action="store_true",
                       help="use the outline's bounding box, not the polygon itself")
        if name == "template":
            p.add_argument("--force", action="store_true",
                           help="overwrite drawing layers that already exist")

    args = parser.parse_args()

    from skimap.segments import aoi as aoi_mod, drawn, paint, routes as routes_mod

    aoi_path = Path(args.aoi)
    window = aoi_mod.from_vector(aoi_path, layer=args.layer, pad_m=args.pad)
    clip = None if args.no_clip else aoi_mod.mask(window, aoi_path, layer=args.layer)
    out_dir = _out_dir(args, aoi_path)
    print(f"{aoi_path.name}: {window}")
    if clip is not None:
        print(f"  {int(clip.sum())} of {clip.size} cells inside the outline")

    corridors = paint.corridors_in(window, args.corridors, clip)
    if not corridors:
        raise SystemExit("No corridor reaches this outline. Has `route` been run here?")
    routes = routes_mod.load(args.routes, only=set(corridors))
    print(f"\n{len(corridors)} corridors reach it:")
    for fid in sorted(corridors):
        route = routes[fid]
        doubles = route.self_proximity()
        warn = ("   <-- doubles back on itself; a cut here may land in two places"
                if doubles > 0.2 else "")
        print(f"  {fid:>4}  {route.length_m:>7.0f} m  {route.name or '(unnamed)'}{warn}")

    lines_path = out_dir / "segments_lines.shp"
    polys_path = out_dir / "segments_polygons.shp"

    if args.command == "template":
        merged = out_dir / "corridors_merged.tif"
        arr = aoi_mod.merge_max(window, corridors.values())
        if clip is not None:
            arr = arr * clip
        landed, ok = aoi_mod.write(window, arr, merged)
        print(f"\n  {int((arr > 0).sum())} corridor cells -> {landed.name}"
              + ("" if ok else "  (LOCKED; close it and rerun)"))

        # The centrelines, clipped. Needed on screen while drawing: the cuts
        # are perpendicular to these, and a line is assigned to whichever
        # route it runs along.
        centre = out_dir / "routes_aoi.shp"
        drawn.template(centre, ogr.wkbLineString)
        outline = None if args.no_clip else aoi_mod.union(aoi_path, layer=args.layer)
        ds = ogr.Open(str(centre), 1)
        layer = ds.GetLayer(0)
        for fid in sorted(corridors):
            geom = routes[fid].geometry
            if outline is not None:
                geom = geom.Intersection(outline)
            if geom is None or geom.IsEmpty():
                continue
            parts = ([geom] if geom.GetGeometryCount() == 0
                     else [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())])
            for part in parts:
                feat = ogr.Feature(layer.GetLayerDefn())
                feat.SetField("note", f"tour {fid} {routes[fid].name}"[:64])
                feat.SetField("tour_fid", fid)
                feat.SetGeometry(part)
                layer.CreateFeature(feat)
                feat = None
        ds = None
        print(f"  route centrelines -> {centre.name}")

        for path, kind in ((lines_path, ogr.wkbLineString), (polys_path, ogr.wkbPolygon)):
            if path.exists() and not args.force:
                print(f"  {path.name} exists - kept (--force to replace)")
                continue
            drawn.template(path, kind)
            print(f"  empty -> {path.name}")
        print(f"\nDraw into {lines_path.name} and {polys_path.name}, then run "
              f"'split' with the same --aoi.")
        return

    features = drawn.read(lines_path, "line") + drawn.read(polys_path, "poly")
    n_lines = sum(1 for d in features if d.kind == "line")
    print(f"\n{n_lines} lines and {len(features) - n_lines} polygons drawn")
    if not features:
        from skimap import config

        print(f"  nothing drawn yet - every corridor will come out "
              f"{config.SEGMENTS['default']}")
    else:
        drawn.assign(features, routes)
        print(f"\n{'fid':>4} {'kind':>5} {'colour':>7} {'tour':>5} {'dist':>7}   station range")
        print("-" * 62)
        for d in sorted(features, key=lambda d: (d.route, d.s0)):
            flag = "  <-- ambiguous, set tour_fid" if d.ambiguous else ""
            print(f"{d.fid:>4} {d.kind:>5} {d.colour:>7} {d.route:>5} {d.distance:>6.0f}m"
                  f"   {d.s0:>6.0f} -> {d.s1:>6.0f}{flag}")

    severity, membership = paint.paint(window, routes, features, corridors, clip=clip)
    print()
    paint.write(window, severity, membership, out_dir)
    print(f"\n{int((severity >= 0).sum())} corridor cells painted, disjoint by "
          f"construction. Style each with its matching .lyrx.")


if __name__ == "__main__":
    main()
