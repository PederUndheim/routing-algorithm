"""What do the GPS tracks actually contribute to a route?

The track layer is the one input to the cost surface that is not terrain. It
is where people have actually skied, and it takes a fixed number of cost units
off - up to `max_reduction` outside forest, up to `max_reduction_forest`
inside it (config.TRACKS). The claim it encodes is that a well-used line is
easier than the terrain alone suggests.

That claim is testable, and this measures it the only way that settles it:
build a second national surface with the track step skipped, route every tour
through both, and look at how far the lines moved. Everything else is held
identical - same tours, same region buffers, same corridor, same router
- so the difference between the two sets of lines IS the track layer.

Everything lands under data/test/track_reduction_test/:

    tiles/                  per-tile surfaces, built with tracks=False
    output/cost_surface.tif the national no-track surface, as a COG
    routes.gpkg             routes through it, with comparison fields
    corridors/              corridors through it
    corridors_all.tif       those corridors merged

Nothing here touches data/cost_surface or data/routing_output, so the production
surface and its routes stay exactly as they are and the comparison has
something to compare against.

Three stages, in order:

    python -m skimap.track_test surface --jobs 8    # ~1300 tiles
    python -m skimap.track_test mosaic              # VRT + COG
    python -m skimap.track_test route               # every tour
    python -m skimap.track_test compare             # stats, re-runnable

`route` fills in the comparison fields itself; `compare` recomputes them
without re-routing, which is what to run after editing anything by hand.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import ogr

from skimap import paths, routing

ogr.UseExceptions()

ROOT = paths.DATA / "test" / "track_reduction_test"
TILES = ROOT / "tiles"
OUTPUT = ROOT / "output"
VRT = OUTPUT / "cost_surface.vrt"
COG = OUTPUT / "cost_surface.tif"
ROUTES = ROOT / "routes.gpkg"
CORRIDORS = ROOT / "corridors"

# Its own name in the GRASS mapset, so it sits beside nat_cost instead of
# relinking every time a run switches between the two surfaces.
COST_RASTER = "nat_cost_notracks"

# The production routes this is measured against.
REFERENCE = paths.ROUTES / "routes.gpkg"

COMPARISON_FIELDS = (
    ("ref_len_m", ogr.OFTReal),     # the tracked route's length, same tour
    ("len_diff_m", ogr.OFTReal),    # this one minus that one
    ("cost_diff", ogr.OFTReal),     # cost_opt difference, no-tracks minus tracked
    ("sep_mean_m", ogr.OFTReal),    # mean distance between the two lines
    ("sep_max_m", ogr.OFTReal),     # worst distance - symbolise on this
)


def national_surface() -> Path:
    """The no-track surface: the COG if it has been built, else the VRT."""
    for candidate in (COG, VRT):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No no-track surface in {OUTPUT}. Build one with "
        "'python -m skimap.track_test surface' then '... mosaic'."
    )


# --- stages -------------------------------------------------------------


def build_surface(*, jobs: int = 1, force: bool = False,
                  only: Optional[list[str]] = None) -> list[str]:
    """Every tile again, with the track reduction skipped.

    Resumable in the same way the production build is: a tile that already has
    a variant output is skipped unless `force`. That matters here because this
    is the long stage.
    """
    from skimap.cost_surface.surface import build_all

    return build_all(only=only, force=force, jobs=jobs,
                     tracks=False, tiles_root=TILES)


def build_mosaic(*, cog: bool = True) -> Path:
    """VRT over the variant tiles, then the COG the router reads."""
    from skimap import mosaic

    vrt = mosaic.build_mosaic(out_path=VRT, tiles_root=TILES)
    if not cog:
        return vrt
    print(f"materializing {vrt.name} -> {COG.name}")
    return mosaic.to_cog(vrt, COG)


def route(*, buffer_m: Optional[float] = None,
          force: bool = False, merge: bool = True,
          limit: int = 0, fids: Optional[list[int]] = None):
    """Route the tours through the no-track surface."""
    from skimap import tours as tours_mod

    found = sorted(tours_mod.read_tours(), key=lambda t: t.fid)
    if fids:
        wanted = set(fids)
        found = [t for t in found if t.fid in wanted]
    elif limit:
        found = found[:limit]
    if not found:
        raise SystemExit("No tours to route.")

    surface = national_surface()
    print(f"routing {len(found)} tours through {surface}")
    results = routing.run_batch(
        found, out_dir=ROOT, buffer_m=buffer_m,
        force=force, merge=merge,
        # Prunes against this build's own routes.gpkg, so a tour deleted,
        # moved or renamed in tours.gpkg is dropped here as it is in
        # production - otherwise its corridor keeps being merged, and the
        # corridor review compares a stale route against a fresh one. Never
        # with --fid or --limit: to pruning, every tour left out of a subset
        # looks deleted.
        prune=not (fids or limit),
        surface=surface, cost_raster=COST_RASTER,
    )
    compare()
    return results


# --- comparison ---------------------------------------------------------


def compare(routes_path: Optional[Path] = None,
            reference_path: Optional[Path] = None) -> None:
    """Fill in the comparison fields and print how far the lines moved.

    Separate from `route` and safe to re-run: it only reads geometry and
    writes attributes, so re-running after the production routes are rebuilt
    re-measures against the new ones without touching a corridor.
    """
    routes_path = Path(routes_path) if routes_path else ROUTES
    reference_path = Path(reference_path) if reference_path else REFERENCE
    if not routes_path.exists():
        raise FileNotFoundError(f"No no-track routes at {routes_path}")
    if not reference_path.exists():
        print(f"No production routes at {reference_path} - nothing to compare against.")
        return

    ref_ds = ogr.Open(str(reference_path))
    ref_layer = ref_ds.GetLayerByName(routing.ROUTES_LAYER)
    reference = {f.GetField("tour_fid"): (f.GetGeometryRef().Clone(),
                                          float(f.GetField("length_m") or 0.0),
                                          float(f.GetField("cost_opt") or 0.0))
                 for f in ref_layer}
    ref_ds = None

    ds = ogr.Open(str(routes_path), 1)
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    have = {layer.GetLayerDefn().GetFieldDefn(i).GetName()
            for i in range(layer.GetLayerDefn().GetFieldCount())}
    for name, kind in COMPARISON_FIELDS:
        if name not in have:
            layer.CreateField(ogr.FieldDefn(name, kind))

    rows = []
    for feat in layer:
        fid = feat.GetField("tour_fid")
        if fid not in reference:
            continue
        ref_geom, ref_len, ref_cost = reference[fid]
        geom = feat.GetGeometryRef()
        mean_sep, max_sep = routing.separation(geom, ref_geom)
        length = float(feat.GetField("length_m") or 0.0)
        cost = float(feat.GetField("cost_opt") or 0.0)

        feat.SetField("ref_len_m", round(ref_len, 1))
        feat.SetField("len_diff_m", round(length - ref_len, 1))
        feat.SetField("cost_diff", round(cost - ref_cost, 1))
        feat.SetField("sep_mean_m", round(mean_sep, 1))
        feat.SetField("sep_max_m", round(max_sep, 1))
        layer.SetFeature(feat)
        rows.append((fid, feat.GetField("name") or f"tour_{fid}", length, ref_len,
                     cost, ref_cost, max_sep))
    ds = None

    if not rows:
        print("No tours in common with the production routes.")
        return
    _report(rows)


def _report(rows: list[tuple]) -> None:
    seps = np.array([r[6] for r in rows])
    len_diff = np.array([r[2] - r[3] for r in rows])
    cost_diff = np.array([r[4] - r[5] for r in rows])

    print(f"\nno-track routes vs tracked routes, {len(rows)} tours\n")
    print(f"  worst separation   median {np.median(seps):7.0f} m   "
          f"p90 {np.percentile(seps, 90):7.0f} m   max {seps.max():7.0f} m")
    print(f"  length difference  median {np.median(len_diff):+7.0f} m   "
          f"p90 {np.percentile(len_diff, 90):+7.0f} m")
    # Removing a reduction can only make ground dearer, so a no-track route
    # costs at least what the tracked one did. A negative here means something
    # other than the track layer differs between the two surfaces.
    print(f"  cost difference    median {np.median(cost_diff):+7.1f}    "
          f"p90 {np.percentile(cost_diff, 90):+7.1f}   "
          f"min {cost_diff.min():+7.1f}")
    if cost_diff.min() < -0.5:
        n = (cost_diff < -0.5).sum()
        print(f"    WARNING {n} route(s) came out CHEAPER without the track "
              f"reduction. Removing a discount cannot do that - the two "
              f"surfaces differ by something else as well.")

    print()
    for cut in (10.0, 50.0, 250.0, 1000.0):
        print(f"  within {cut:7.0f} m everywhere: {(seps < cut).sum():4d} / {len(rows)}")

    unmoved = (seps < 10.0).sum()
    print(f"\n  the tracks changed nothing on {unmoved / len(rows):.0%} of tours "
          f"and moved the line on {1 - unmoved / len(rows):.0%}")

    print(f"\n  most affected by the tracks")
    print(f"  {'fid':>5}  {'tour':26s} {'no-trk m':>9} {'tracked m':>9} {'sep max':>8}")
    for r in sorted(rows, key=lambda r: -r[6])[:15]:
        print(f"  {r[0]:>5}  {r[1][:26]:26s} {r[2]:9.0f} {r[3]:9.0f} {r[6]:8.0f}")
    print("\n  Symbolise routes.gpkg on sep_max_m to find them on the map.")


# --- cli ----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skimap.track_test",
        description="Measure what the GPS track layer contributes to a route.",
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("surface", help="build every tile with the track step skipped")
    p.add_argument("--jobs", type=int, default=1, help="parallel worker processes")
    p.add_argument("--force", action="store_true", help="rebuild tiles that already exist")
    p.add_argument("--tile", action="append", dest="tiles", help="only these tile ids")

    p = sub.add_parser("mosaic", help="VRT and COG over the variant tiles")
    p.add_argument("--no-cog", action="store_true", help="stop after the VRT")

    p = sub.add_parser("route", help="route the tours through the no-track surface")
    p.add_argument("--buffer", type=float)
    p.add_argument("--limit", type=int, default=0, help="first N tours by fid (0 = all)")
    p.add_argument("--fid", action="append", type=int)
    p.add_argument("--force", action="store_true", help="re-route everything")
    p.add_argument("--no-merge", action="store_true")

    p = sub.add_parser("compare", help="recompute the comparison without re-routing")

    args = parser.parse_args(argv)

    if args.stage == "surface":
        jobs = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)
        failed = build_surface(jobs=jobs, force=args.force, only=args.tiles)
        return 1 if failed else 0

    if args.stage == "mosaic":
        build_mosaic(cog=not args.no_cog)
        return 0

    if args.stage == "route":
        results = route(buffer_m=args.buffer, force=args.force,
                        merge=not args.no_merge, limit=args.limit, fids=args.fid)
        return 1 if any(not r.ok for r in results) else 0

    compare()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
