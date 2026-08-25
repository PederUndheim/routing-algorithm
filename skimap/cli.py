"""python -m skimap.cli <stage>"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="skimap", description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("grid", help="build the national tile grid")
    p.add_argument("--boundary", type=Path, required=True, help="polygon to clip the fishnet to")
    p.add_argument("--boundary-layer")
    p.add_argument("--align-to", type=Path, help="derive the lattice from this grid instead of config.GRID_ORIGIN")
    p.add_argument("--align-to-layer")

    p = sub.add_parser("tracks", help="compute the national track normalization scale")

    p = sub.add_parser("cost", help="build per-tile cost surfaces")
    p.add_argument("--tile", action="append", dest="tiles")
    p.add_argument("--area", action="append", dest="areas",
                   help="a name from config.STUDY_AREAS; names the debug folder too")
    p.add_argument("--all-areas", action="store_true",
                   help="every study area in config.STUDY_AREAS")
    p.add_argument("--force", action="store_true")
    p.add_argument("--jobs", type=int, default=1, help="parallel worker processes")
    p.add_argument("--debug", action="store_true",
                   help="also write each cost component to the tile's debug/ dir")

    p = sub.add_parser("tours", help="the digitized start/end pairs to route")
    p.add_argument("action", choices=["init", "check", "import-json"],
                   help="init: write an empty layer to digitize into; "
                        "check: validate what you drew; "
                        "import-json: bring in the older {area: [{name,start,end}]} format")
    p.add_argument("--path", type=Path, help="tour file (default data/tours/tours.gpkg)")
    p.add_argument("--layer", help="layer name, for multi-layer sources")
    p.add_argument("--json", type=Path, help="source file for import-json")
    p.add_argument("--overwrite", action="store_true",
                   help="init/import-json only, and it discards digitized work")

    p = sub.add_parser("route", help="route the digitized tours through the cost surface")
    p.add_argument("--path", type=Path, help="tour file (default data/tours/tours.gpkg)")
    p.add_argument("--layer", help="layer name, for multi-layer sources")
    p.add_argument("--out", type=Path, help="output root (default data/routes)")
    p.add_argument("--fid", action="append", type=int, help="route only these tour ids")
    p.add_argument("--buffer", type=float,
                   help="region buffer ceiling in m, scaled down for shorter tours "
                        "(default config.ROUTING)")
    p.add_argument("--mode", action="append", dest="modes",
                   choices=["conservative", "balanced", "explorative"],
                   help="corridor modes to write; repeatable, config.DEFAULT_CORRIDOR_MODE alone by default")
    p.add_argument("--force", action="store_true", help="re-route everything, discarding routes.gpkg")
    p.add_argument("--no-prune", action="store_true",
                   help="keep routes whose tour was deleted, moved or renamed "
                        "(pruning is off automatically with --fid)")
    p.add_argument("--no-merge", action="store_true", help="skip rebuilding corridors_all.tif")
    p.add_argument("--merge-only", action="store_true",
                   help="just rebuild corridors_all.tif from the corridors already on disk")

    p = sub.add_parser("exposure", help="score the routed lines for avalanche exposure "
                                        "and split their corridors by the class")
    p.add_argument("--routes", type=Path, help="routes.gpkg (default data/routes/routes.gpkg)")
    p.add_argument("--corridors", type=Path,
                   help="per-route corridors (default data/routes/corridors)")
    p.add_argument("--out", type=Path, help="output root (default data/corridors)")
    p.add_argument("--no-copy-all", action="store_true",
                   help="write only the per-class rasters, skipping the copy of "
                        "every corridor and of corridors_all.tif")

    p = sub.add_parser("alignment", help="check the surface is georeferenced where its data is")
    p.add_argument("--tile", action="append", dest="tiles", help="limit to these tiles")
    p.add_argument("--source", help="probe this file in data/output instead of the default")

    p = sub.add_parser("mosaic", help="merge tiles into the national surface")
    p.add_argument("--cog", action="store_true", help="also write a COG")

    args = parser.parse_args()

    if args.stage == "grid":
        from skimap import config, grid

        origin = config.GRID_ORIGIN
        if args.align_to is not None:
            origin = grid.lattice_origin(args.align_to, layer=args.align_to_layer)
            print(f"Lattice offset from {args.align_to.name}: {origin}")
        grid.build_grid(args.boundary, boundary_layer=args.boundary_layer, origin=origin)
        return

    if args.stage == "tracks":
        from skimap.data_preprocessing import tracks

        tracks.compute_scale()
        return

    if args.stage == "cost":
        from skimap import config
        from skimap.cost.surface import build_all

        # Areas resolve to tiles, and carry their name through so debug
        # output lands somewhere findable.
        names = list(config.STUDY_AREAS) if args.all_areas else (args.areas or [])
        unknown = [n for n in names if n not in config.STUDY_AREAS]
        if unknown:
            raise SystemExit(
                f"Unknown study area(s): {', '.join(unknown)}. "
                f"Known: {', '.join(sorted(config.STUDY_AREAS))}"
            )
        labels = {config.STUDY_AREAS[n]: n for n in names}

        only = None
        if names or args.tiles:
            only = sorted({*(args.tiles or []), *labels})

        jobs = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)
        if names:
            print(f"{len(names)} study area(s): {', '.join(names)}")
        failed = build_all(only=only, force=args.force, jobs=jobs,
                           debug=args.debug, labels=labels)
        raise SystemExit(1 if failed else 0)

    if args.stage == "tours":
        from skimap import tours

        if args.action == "init":
            tours.create_template(args.path, overwrite=args.overwrite)
        elif args.action == "import-json":
            if not args.json:
                raise SystemExit("--json is required for import-json")
            tours.import_json(args.json, args.path, overwrite=args.overwrite)
        else:
            raise SystemExit(1 if tours.check(
                tours.read_tours(args.path, layer=args.layer)) else 0)
        return

    if args.stage == "route":
        from skimap import routing, tours as tours_mod

        if args.merge_only:
            routing.merge_corridors()
            return

        found = tours_mod.read_tours(args.path, layer=args.layer)
        if args.fid:
            wanted = set(args.fid)
            found = [t for t in found if t.fid in wanted]
            missing = wanted - {t.fid for t in found}
            if missing:
                raise SystemExit(f"No tour with fid {sorted(missing)}")
        if not found:
            raise SystemExit("No tours to route.")

        results = routing.run_batch(
            found, out_dir=args.out, buffer_m=args.buffer,
            modes=args.modes, force=args.force, merge=not args.no_merge,
            # --fid hands run_batch a subset, and to pruning every tour left
            # out of that subset is indistinguishable from a deleted one - it
            # would take routes.gpkg down to the one route being redone.
            prune=not (args.no_prune or args.fid),
        )
        raise SystemExit(1 if any(not r.ok for r in results) else 0)

    if args.stage == "exposure":
        from skimap import exposure

        exposure.run(args.routes, args.corridors, args.out,
                     copy_all=not args.no_copy_all)
        return

    if args.stage == "alignment":
        from skimap import alignment

        raise SystemExit(0 if alignment.run(args.tiles, args.source) else 1)

    if args.stage == "mosaic":
        from skimap import mosaic, paths

        vrt = mosaic.build_mosaic()
        mosaic.write_colormap()
        if args.cog:
            mosaic.to_cog(vrt, paths.OUTPUT / "cost_surface.tif")
        return

    raise NotImplementedError(args.stage)


if __name__ == "__main__":
    main()
