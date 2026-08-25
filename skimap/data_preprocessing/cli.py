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
    elif args.command == "layers":
        for name, n, geom in vectors.list_layers(args.src):
            print("%-40s %10d  %s" % (name, n, geom))
    elif args.command == "describe":
        for k, v in rasters.describe(args.src).items():
            print(f"{k:>10}: {v}")


if __name__ == "__main__":
    main()
