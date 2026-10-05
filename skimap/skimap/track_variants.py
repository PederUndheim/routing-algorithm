"""National surfaces at different track-reduction settings, side by side.

skimap.track_test asks whether the GPS tracks are worth anything at all, by
building the country with the track step switched off. This asks the question
that comes after that one: given that they are worth something, HOW MUCH
should a track take off, and is a track under trees worth more than the same
track above the treeline?

A variant is a name, a pair of numbers, and a full national build - its own
tiles, its own mosaic, its own routes and corridors, under its own directory.
Nothing here writes to data/cost_surface or data/routing_output, so production
stays exactly as it is and remains the baseline every variant is measured
against.

    python -m skimap.track_variants list
    python -m skimap.track_variants run max2       --jobs 8
    python -m skimap.track_variants run forest_1_2 --jobs 8

`run` is surface -> mosaic -> route -> compare. Each is a stage of its own as
well, so re-routing does not rebuild 1334 tiles:

    python -m skimap.track_variants surface max2 --jobs 8
    python -m skimap.track_variants mosaic  max2
    python -m skimap.track_variants route   max2
    python -m skimap.track_variants compare max2

Everything lands under data/test/track_variants/<name>/:

    <name>.json             the settings, in the form config.py's overlay reads
    built.json              the numbers the tiles on disk were actually built at
    tiles/                  per-tile surfaces at this variant's numbers
    output/cost_surface.tif the national surface, as a COG
    routes.gpkg             routes through it, with comparison fields
    corridors/              corridors through it
    corridors_all.tif       those corridors merged

Budget about 2.9 GB per variant - 1.1 GB of tiles and a 1.65 GB COG - and the
better part of a day, of which 841 tours is the long pole.

## The two that ship

Production takes up to 3.0 cost units off a tracked pixel, the same in forest
as above the treeline (config.TRACKS, both numbers equal).

    max2         2.0 everywhere. Is 3.0 simply too generous?
    forest_1_2   1.0 in the open, 2.0 in forest. In the open you can walk
                 anywhere, so somebody else's line is weak evidence; under
                 trees that line is also the gap between them.

Both are strictly smaller than production everywhere, so removing that much
discount can only make ground dearer: every variant route must cost at least
what the production route for the same tour cost. A negative cost_diff means
the two surfaces differ by something other than these numbers, and `compare`
says so rather than leaving you to notice.

Add your own:

    python -m skimap.track_variants init softer --max 0.5 --forest 1.5

## Why the numbers reach the tile workers through a file

config.py applies the overlay at import, from SKIMAP_PROFILE in the
environment. It has to happen there and not at runtime: build_all's workers
are spawned fresh on Windows and inherit the environment, not a runtime patch
to the config module. So main() sets that variable before anything that reads
a parameter is imported, and every stage checks it really took - see _live().
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

# Stdlib and paths only at module level. paths.py reads no parameter and
# imports nothing that does, so it is safe before SKIMAP_PROFILE is in the
# environment; everything else is imported inside a stage, after main() has
# set it.
from skimap import paths

ROOT = paths.DATA / "test" / "track_variants"

# The production routes every variant is measured against. There is no
# baseline run to do: production already routed these tours through the
# unmodified surface.
REFERENCE = paths.ROUTES / "routes.gpkg"

# The built-in variants. A name here needs no `init` - `run <name>` writes
# its profile on the way past.
VARIANTS: dict[str, dict] = {
    "max2": {
        "note": "2.0 everywhere - no forest split, just less than production",
        "max_reduction": 2.0,
        "max_reduction_forest": 2.0,
    },
    "forest_1_2": {
        "note": "1.0 in the open, 2.0 in forest",
        "max_reduction": 1.0,
        "max_reduction_forest": 2.0,
    },
}

COMPARISON_FIELDS = (
    ("ref_len_m", "OFTReal"),     # the production route's length, same tour
    ("len_diff_m", "OFTReal"),    # this one minus that one
    ("cost_diff", "OFTReal"),     # cost_opt difference, variant minus production
    ("sep_mean_m", "OFTReal"),    # mean distance between the two lines
    ("sep_max_m", "OFTReal"),     # worst distance - symbolise on this
)


@dataclass(frozen=True)
class Variant:
    """Where one variant keeps its things."""

    name: str

    @property
    def root(self) -> Path:
        return ROOT / self.name

    @property
    def profile(self) -> Path:
        """Named after the variant, not "profile.json": config.py announces the
        overlay it applied by the file's stem, and `profile profile: ...` in a
        log two variants deep tells you nothing about which one ran."""
        return self.root / f"{self.name}.json"

    @property
    def built(self) -> Path:
        return self.root / "built.json"

    @property
    def tiles(self) -> Path:
        return self.root / "tiles"

    @property
    def vrt(self) -> Path:
        return self.root / "output" / "cost_surface.vrt"

    @property
    def cog(self) -> Path:
        return self.root / "output" / "cost_surface.tif"

    @property
    def routes(self) -> Path:
        return self.root / "routes.gpkg"

    @property
    def corridors(self) -> Path:
        return self.root / "corridors"

    @property
    def cost_raster(self) -> str:
        """Its own name in the GRASS mapset, so it sits beside nat_cost and the
        other variants instead of relinking on every switch between them. A
        stale link would hand this run somebody else's surface."""
        return "nat_cost_" + re.sub(r"[^0-9a-zA-Z_]", "_", self.name)


# --- the profile --------------------------------------------------------


def write_profile(name: str, *, max_reduction: float, max_reduction_forest: float,
                  note: str = "", force: bool = False) -> Path:
    """Write <name>/<name>.json, the file config.py's overlay reads."""
    v = Variant(name)
    if v.profile.exists() and not force:
        raise SystemExit(
            f"{v.profile} already exists. --force overwrites it - but note that "
            "any tiles already built under the old numbers become stale, and "
            "'surface' will refuse to mix the two without --force of its own."
        )
    v.root.mkdir(parents=True, exist_ok=True)
    body = {
        "name": name,
        "note": note or f"max_reduction {max_reduction:g} outside forest, "
                        f"{max_reduction_forest:g} inside",
        "config": {
            "TRACKS": {
                "max_reduction": float(max_reduction),
                "max_reduction_forest": float(max_reduction_forest),
            }
        },
    }
    v.profile.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {v.profile}")
    return v.profile


def _discovered() -> set[str]:
    """Variant names with a profile on disk. A directory counts only if it
    holds <name>.json, so a stray file dropped in one is not read as a
    variant and a half-deleted directory stops being offered."""
    if not ROOT.is_dir():
        return set()
    return {d.name for d in ROOT.iterdir() if (d / f"{d.name}.json").exists()}


def ensure_profile(name: str) -> Variant:
    """The variant, with its profile on disk. Built-ins write their own."""
    v = Variant(name)
    if v.profile.exists():
        return v
    if name not in VARIANTS:
        known = ", ".join(sorted(set(VARIANTS) | _discovered()))
        raise SystemExit(
            f"No variant {name!r} and no {v.profile}.\n"
            f"  known: {known or '(none)'}\n"
            f"  make one: python -m skimap.track_variants init {name} "
            f"--max 1.0 --forest 2.0"
        )
    spec = VARIANTS[name]
    write_profile(name,
                  max_reduction=spec["max_reduction"],
                  max_reduction_forest=spec["max_reduction_forest"],
                  note=spec["note"])
    return v


def numbers(v: Variant) -> tuple[float, float]:
    """(outside forest, inside forest), read off the variant's profile."""
    # utf-8-sig: profiles get hand-edited on Windows, where Notepad and
    # PowerShell's Out-File both write a BOM.
    tracks = json.loads(v.profile.read_text(encoding="utf-8-sig"))["config"]["TRACKS"]
    return float(tracks["max_reduction"]), float(tracks["max_reduction_forest"])


def _activate(name: str) -> Variant:
    """Put this variant's profile in the environment. Before importing config."""
    v = ensure_profile(name)
    os.environ["SKIMAP_PROFILE"] = str(v.profile.resolve())
    return v


def _live(v: Variant) -> None:
    """Refuse to run unless config really did load this variant's profile.

    Import config before SKIMAP_PROFILE is set - directly, or through any
    module that reads a parameter - and every parameter stays at its
    production value while the output still lands here under this variant's
    name. That produces a full national build showing no change, which is
    exactly what a change that did nothing produces. The two must not be
    possible to confuse.
    """
    from skimap import config

    if config.PROFILE != v.profile.resolve():
        raise SystemExit(
            f"config loaded {config.PROFILE} but this is variant {v.name!r} "
            f"({v.profile}). Its parameters are NOT applied - run this through "
            "'python -m skimap.track_variants', which sets SKIMAP_PROFILE "
            "before importing anything that reads config."
        )
    want = numbers(v)
    have = (float(config.TRACKS["max_reduction"]),
            float(config.TRACKS["max_reduction_forest"]))
    if want != have:
        raise SystemExit(
            f"profile says max_reduction {want[0]:g}/{want[1]:g} but config has "
            f"{have[0]:g}/{have[1]:g}. Check the 'profile ...' line above."
        )


# --- stages -------------------------------------------------------------


def build_surface(v: Variant, *, jobs: int = 1, force: bool = False,
                  only: Optional[Sequence[str]] = None) -> list[str]:
    """Every tile again, at this variant's numbers.

    Resumable the way the production build is: a tile that already has a
    variant output is skipped unless `force`. That matters here because this
    is the long stage.

    Refuses to add tiles to a set built at different numbers. Resume keys on
    the file existing, not on what is in it, so without this check editing
    the profile and re-running would leave one directory holding tiles from
    two settings, mosaicked into a surface that is neither.
    """
    from skimap.cost_surface.surface import build_all

    _live(v)
    want = numbers(v)
    if v.built.exists() and not force:
        was = json.loads(v.built.read_text(encoding="utf-8"))
        had = (float(was["max_reduction"]), float(was["max_reduction_forest"]))
        if had != want:
            raise SystemExit(
                f"{v.tiles} holds tiles built at {had[0]:g}/{had[1]:g}, but "
                f"the profile now says {want[0]:g}/{want[1]:g}. Re-run with "
                "--force to rebuild them all, or use a new variant name to "
                "keep both."
            )

    failed = build_all(only=only, force=force, jobs=jobs,
                       tracks=True, tiles_root=v.tiles)
    if not failed:
        # Recorded after a partial --tile build too, not just a full one. The
        # numbers are what the check above compares, and a directory holding
        # one tile at the old settings is exactly as mixed as one holding
        # 1334 of them.
        v.built.write_text(json.dumps(
            {"max_reduction": want[0], "max_reduction_forest": want[1],
             "tiles": len(list(v.tiles.glob("*/cost_surface.tif")))},
            indent=2) + "\n", encoding="utf-8")
    return failed


def build_mosaic(v: Variant, *, cog: bool = True) -> Path:
    """VRT over this variant's tiles, then the COG the router reads."""
    from skimap import mosaic

    _live(v)
    vrt = mosaic.build_mosaic(out_path=v.vrt, tiles_root=v.tiles)
    if not cog:
        return vrt
    print(f"materializing {vrt.name} -> {v.cog.name}")
    return mosaic.to_cog(vrt, v.cog)


def national_surface(v: Variant) -> Path:
    """This variant's surface: the COG if it has been built, else the VRT."""
    for candidate in (v.cog, v.vrt):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No surface in {v.root / 'output'}. Build one with "
        f"'python -m skimap.track_variants surface {v.name}' then "
        f"'... mosaic {v.name}'."
    )


def route(v: Variant, *, buffer_m: Optional[float] = None, force: bool = False,
          merge: bool = True, limit: int = 0, fids: Optional[list[int]] = None):
    """Route the tours through this variant's surface."""
    from skimap import routing, tours as tours_mod

    _live(v)
    found = sorted(tours_mod.read_tours(), key=lambda t: t.fid)
    if fids:
        wanted = set(fids)
        found = [t for t in found if t.fid in wanted]
        missing = wanted - {t.fid for t in found}
        if missing:
            raise SystemExit(f"No tour with fid {sorted(missing)}")
    elif limit:
        found = found[:limit]
    if not found:
        raise SystemExit("No tours to route.")

    surface = national_surface(v)
    print(f"routing {len(found)} tours through {surface}")
    results = routing.run_batch(
        found, out_dir=v.root, buffer_m=buffer_m,
        force=force, merge=merge,
        # Prunes against this variant's own routes.gpkg, so a tour deleted,
        # moved or renamed in tours.gpkg is dropped here as it is in
        # production - otherwise its corridor keeps being merged, and the
        # corridor review compares a stale route against a fresh one. Never
        # with --fid or --limit: to pruning, every tour left out of a subset
        # looks deleted.
        prune=not (fids or limit),
        surface=surface, cost_raster=v.cost_raster,
    )
    compare(v)
    return results


# --- comparison ---------------------------------------------------------


def compare(v: Variant, reference_path: Optional[Path] = None) -> None:
    """Fill in the comparison fields and print how far the lines moved.

    Separate from `route` and safe to re-run: it only reads geometry and
    writes attributes, so re-running after the production routes are rebuilt
    re-measures against the new ones without touching a corridor.
    """
    from osgeo import ogr

    from skimap import routing

    ogr.UseExceptions()
    reference_path = Path(reference_path) if reference_path else REFERENCE
    if not v.routes.exists():
        raise SystemExit(
            f"No routes for {v.name!r} at {v.routes}. Route them with "
            f"'python -m skimap.track_variants route {v.name}'."
        )
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

    ds = ogr.Open(str(v.routes), 1)
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    have = {layer.GetLayerDefn().GetFieldDefn(i).GetName()
            for i in range(layer.GetLayerDefn().GetFieldCount())}
    for name, kind in COMPARISON_FIELDS:
        if name not in have:
            layer.CreateField(ogr.FieldDefn(name, getattr(ogr, kind)))

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
    _report(v, rows)


def _report(v: Variant, rows: list[tuple]) -> None:
    import numpy as np

    lo, hi = numbers(v)
    seps = np.array([r[6] for r in rows])
    len_diff = np.array([r[2] - r[3] for r in rows])
    cost_diff = np.array([r[4] - r[5] for r in rows])

    print(f"\n{v.name} ({lo:g} outside forest, {hi:g} inside) vs production, "
          f"{len(rows)} tours\n")
    print(f"  worst separation   median {np.median(seps):7.0f} m   "
          f"p90 {np.percentile(seps, 90):7.0f} m   max {seps.max():7.0f} m")
    print(f"  length difference  median {np.median(len_diff):+7.0f} m   "
          f"p90 {np.percentile(len_diff, 90):+7.0f} m")
    # Both shipped variants take LESS off than production does, so their
    # ground is dearer and a route through them costs at least what the
    # production route cost. A variant that raised a number would invert
    # this, which is why the check reads the profile rather than assuming.
    print(f"  cost difference    median {np.median(cost_diff):+7.1f}    "
          f"p90 {np.percentile(cost_diff, 90):+7.1f}   "
          f"min {cost_diff.min():+7.1f}")
    if max(lo, hi) <= 3.0 and cost_diff.min() < -0.5:
        n = (cost_diff < -0.5).sum()
        print(f"    WARNING {n} route(s) came out CHEAPER than production. This "
              f"variant only ever takes LESS off than production's 3.0, so "
              f"removing that discount cannot do that - the two surfaces "
              f"differ by something else as well.")

    print()
    for cut in (10.0, 50.0, 250.0, 1000.0):
        print(f"  within {cut:7.0f} m everywhere: {(seps < cut).sum():4d} / {len(rows)}")

    unmoved = (seps < 10.0).sum()
    print(f"\n  this setting changed nothing on {unmoved / len(rows):.0%} of tours "
          f"and moved the line on {1 - unmoved / len(rows):.0%}")

    print(f"\n  most affected")
    print(f"  {'fid':>5}  {'tour':26s} {'variant m':>9} {'prod m':>9} {'sep max':>8}")
    for r in sorted(rows, key=lambda r: -r[6])[:15]:
        print(f"  {r[0]:>5}  {r[1][:26]:26s} {r[2]:9.0f} {r[3]:9.0f} {r[6]:8.0f}")
    print("\n  Symbolise routes.gpkg on sep_max_m to find them on the map.")


# --- listing ------------------------------------------------------------


def show_list() -> None:
    """Every variant, its numbers, and how far it has been built."""
    from osgeo import ogr

    ogr.UseExceptions()
    names = sorted(set(VARIANTS) | _discovered())
    if not names:
        print("No variants.")
        return

    print(f"production: 3.0 outside forest, 3.0 inside  (config.TRACKS)\n")
    print(f"  {'name':14s} {'open':>5s} {'forest':>6s}  {'tiles':>5s}  "
          f"{'surface':7s} {'routes':>6s}  note")
    for name in names:
        v = Variant(name)
        if v.profile.exists():
            lo, hi = numbers(v)
            note = json.loads(v.profile.read_text(encoding="utf-8-sig")).get("note", "")
        else:
            spec = VARIANTS[name]
            lo, hi = spec["max_reduction"], spec["max_reduction_forest"]
            note = spec["note"] + "   (not started)"
        tiles = len(list(v.tiles.glob("*/cost_surface.tif")))
        surface = "cog" if v.cog.exists() else ("vrt" if v.vrt.exists() else "-")
        routed = 0
        if v.routes.exists():
            ds = ogr.Open(str(v.routes))
            layer = ds.GetLayerByName("routes")
            routed = layer.GetFeatureCount() if layer else 0
            ds = None
        print(f"  {name:14s} {lo:5g} {hi:6g}  {tiles:5d}  {surface:7s} "
              f"{routed:6d}  {note}")


# --- cli ----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skimap.track_variants",
        description="National surfaces at different track-reduction settings.",
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    sub.add_parser("list", help="every variant and how far it has been built")

    p = sub.add_parser("init", help="define a new variant")
    p.add_argument("name")
    p.add_argument("--max", type=float, required=True,
                   help="cost units off a fully tracked pixel OUTSIDE forest")
    p.add_argument("--forest", type=float, required=True,
                   help="the same, INSIDE forest (equal to --max for no split)")
    p.add_argument("--note", default="")
    p.add_argument("--force", action="store_true", help="overwrite an existing profile")

    p = sub.add_parser("surface", help="build every tile at this variant's numbers")
    p.add_argument("name")
    p.add_argument("--jobs", type=int, default=1, help="parallel worker processes")
    p.add_argument("--force", action="store_true", help="rebuild tiles that already exist")
    p.add_argument("--tile", action="append", dest="tiles", help="only these tile ids")

    p = sub.add_parser("mosaic", help="VRT and COG over this variant's tiles")
    p.add_argument("name")
    p.add_argument("--no-cog", action="store_true", help="stop after the VRT")

    p = sub.add_parser("route", help="route the tours through this variant's surface")
    p.add_argument("name")
    p.add_argument("--buffer", type=float)
    p.add_argument("--limit", type=int, default=0, help="first N tours by fid (0 = all)")
    p.add_argument("--fid", action="append", type=int)
    p.add_argument("--force", action="store_true", help="re-route everything")
    p.add_argument("--no-merge", action="store_true")

    p = sub.add_parser("compare", help="recompute the comparison without re-routing")
    p.add_argument("name")

    p = sub.add_parser("run", help="surface, mosaic, route, compare - the lot")
    p.add_argument("name")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--force", action="store_true")
    p.add_argument("--limit", type=int, default=0)

    args = parser.parse_args(argv)

    if args.stage == "list":
        show_list()
        return 0

    if args.stage == "init":
        write_profile(args.name, max_reduction=args.max,
                      max_reduction_forest=args.forest,
                      note=args.note, force=args.force)
        return 0

    # Everything below reads config, so the profile goes into the environment
    # first - see the note at the top of this file.
    v = _activate(args.name)

    if args.stage == "surface":
        jobs = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)
        return 1 if build_surface(v, jobs=jobs, force=args.force,
                                  only=args.tiles) else 0

    if args.stage == "mosaic":
        build_mosaic(v, cog=not args.no_cog)
        return 0

    if args.stage == "route":
        results = route(v, buffer_m=args.buffer, force=args.force,
                        merge=not args.no_merge, limit=args.limit, fids=args.fid)
        return 1 if any(not r.ok for r in results) else 0

    if args.stage == "compare":
        compare(v)
        return 0

    # run
    jobs = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)
    if build_surface(v, jobs=jobs, force=args.force):
        print("tiles failed - stopping before the mosaic, which would bake the "
              "gaps into the surface.")
        return 1
    build_mosaic(v, cog=True)
    results = route(v, force=args.force, limit=args.limit)
    return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
