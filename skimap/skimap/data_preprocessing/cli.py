"""python -m skimap.data_preprocessing.cli <command>

Turns the raw dumps into the national datasets skimap expects.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skimap import paths
from skimap.data_preprocessing import rasters, vectors


def main() -> None:
    parser = argparse.ArgumentParser(prog="skimap-prep", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("vrt", help="mosaic a directory of rasters into one .vrt")
    p.add_argument("--src", type=Path, required=True, help="directory of .tif tiles")
    p.add_argument("--out", type=Path, required=True, help="output .vrt (keep it next to the tiles)")

    p = sub.add_parser("cog", help="materialize a source as one compressed COG")
    p.add_argument("--src", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dtype", help="e.g. Int16, to shrink an over-wide Float32")
    p.add_argument("--scale", type=float, help="store as int, value = stored * scale (needs --dtype)")
    p.add_argument("--compress", default="DEFLATE")

    p = sub.add_parser("merge", help="warp several rasters onto one grid and write a COG")
    p.add_argument("--src", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dtype")
    p.add_argument("--src-nodata", help='source nodata; "None" ignores a broken declaration')
    p.add_argument("--dst-nodata", help="nodata to write; omit for none")
    p.add_argument("--resampling", default="near")

    p = sub.add_parser("gpkg", help="convert a vector source into a GeoPackage")
    p.add_argument("--src", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--layer", help="source layer name, for multi-layer sources")
    p.add_argument("--out-layer")
    p.add_argument("--where")
    p.add_argument("--assign-srs", action="store_true", help="source declares no SRS; stamp CRS_EPSG on it")
    p.add_argument("--encoding", help="override a lying .cpg, e.g. ISO-8859-1")

    p = sub.add_parser("derived", help="build the national derived layers")
    p.add_argument("--only", nargs="+", help="limit to these layer names")
    p.add_argument("--force", action="store_true", help="rebuild layers that already exist")

    p = sub.add_parser("ridges", help="exposed ridges from a windshelter threshold")
    p.add_argument("--area", nargs="+", help="named areas; see ridges.AREAS and data/ridges/areas.json")
    p.add_argument("--tile", nargs="+", help="tile ids from the national grid")
    p.add_argument("--bbox", nargs=4, type=float, metavar=("MINX", "MINY", "MAXX", "MAXY"))
    p.add_argument("--label", help="folder name for --bbox output")
    p.add_argument("--national", action="store_true", help="one streamed pass over the national windshelter")
    p.add_argument("--threshold", nargs="+", type=float, metavar="W",
                   help="override config.RIDGE_CANDIDATES; areas write one mask "
                        "per value into candidates/, for comparing cuts")
    p.add_argument("--force", action="store_true", help="rebuild what already exists")
    p.add_argument("--list", action="store_true", help="list the named areas and stop")

    p = sub.add_parser("runout-alarm", help="merge the ALARM regions into one raster per scenario")
    p.add_argument("--only", nargs="+", choices=["A", "D"], help="limit to these scenarios")
    p.add_argument("--native", action="store_true",
                   help="keep the delivered 5 m grid instead of the national 10 m lattice")
    p.add_argument("--vrt", action="store_true",
                   help="stop at the virtual mosaic instead of writing a COG")

    p = sub.add_parser("layers", help="list layers in a vector source")
    p.add_argument("src", type=Path)

    p = sub.add_parser("describe", help="size, dtype, resolution and value range")
    p.add_argument("src", type=Path)

    args = parser.parse_args()

    if args.command == "vrt":
        tiles = sorted(args.src.glob("*.tif"))
        print(f"{len(tiles)} tiles in {args.src}")
        rasters.build_vrt(tiles, args.out)
    elif args.command == "cog":
        rasters.to_cog(args.src, args.out, dtype=args.dtype, scale=args.scale, compress=args.compress)
    elif args.command == "merge":
        rasters.warp_mosaic(
            args.src, args.out, dtype=args.dtype, resampling=args.resampling,
            src_nodata=args.src_nodata, dst_nodata=args.dst_nodata,
        )
    elif args.command == "gpkg":
        vectors.to_gpkg(
            args.src, args.out, layer=args.layer, out_layer=args.out_layer,
            where=args.where, assign_srs=args.assign_srs, encoding=args.encoding,
        )
    elif args.command == "derived":
        from skimap.data_preprocessing import derived

        derived.build_all(only=args.only, force=args.force)
    elif args.command == "ridges":
        from skimap.data_preprocessing import ridges

        if args.list:
            for name, spec in ridges.areas().items():
                where = spec.get("tile") or spec.get("bbox")
                print("%-16s %-28s %s" % (name, where, spec.get("place", "")))
        elif args.national:
            # A national run reproduces from config, so a threshold passed on
            # the command line would make an unrepeatable layer. Say so
            # rather than quietly building the wrong thing.
            ignored = [f for f, v in (("--area", args.area), ("--tile", args.tile),
                                      ("--bbox", args.bbox),
                                      ("--threshold", args.threshold)) if v]
            if ignored:
                raise SystemExit(f"--national does not take {', '.join(ignored)}. "
                                 "It builds one layer at config.RIDGE_COST['threshold']; "
                                 "try candidates on an area first.")
            for out in ridges.build_national(force=args.force):
                print(out)
        else:
            ridges.build_areas(
                ridges.resolve(area=args.area, tile=args.tile, bbox=args.bbox,
                               label=args.label),
                candidates=args.threshold, force=args.force,
            )
    elif args.command == "runout-alarm":
        from skimap.data_preprocessing import runout_alarm

        for out in runout_alarm.build_all(only=args.only, native=args.native,
                                          vrt_only=args.vrt):
            print(out)
    elif args.command == "layers":
        for name, n, geom in vectors.list_layers(args.src):
            print("%-40s %10d  %s" % (name, n, geom))
    elif args.command == "describe":
        for k, v in rasters.describe(args.src).items():
            print(f"{k:>10}: {v}")


if __name__ == "__main__":
    main()
