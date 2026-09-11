"""Try a change to the cost surface and see, in about ten minutes, what moved.

The national loop is too slow to think in: 1334 tiles, a 1.65 GB COG and 842
routes is the better part of a day, and by the time it finishes you have
forgotten what you were asking. This runs the same pipeline over a handful of
tours you picked, on only the tiles those tours can reach, and puts the answer
on screen as one PNG per tour with the current route drawn beside the new one.

    python -m skimap.lab init steeper --fid 42 --fid 562 --fid 716
    # edit data/test/lab/profiles/steeper.json, put the change in "config"
    python -m skimap.lab run steeper --jobs 8

`run` is surface -> route -> compare -> figures. Each is also its own stage,
so re-rendering the figures after changing a colour does not re-route, and
re-routing does not rebuild the surface.

Everything lands under data/test/lab/<name>/:

    tiles/              only the tiles the tours can reach
    cost_surface.vrt    those tiles, mosaicked - no COG, see build_surface
    config_used.json    every parameter as the profile left it
    tiles.json          which tiles were built, and why that set
    routes.gpkg         the routes, with how far each moved from production
    corridors/
    figures/            one PNG per tour, plus index.html

Nothing here writes to data/cost_surface or data/routing_output. Those stay
as they are, and they are what every experiment is measured against.

## The baseline is free

The comparison is against data/routing_output/routes.gpkg - the routes you
have now. There is no baseline run: production already routed these tours
through the unmodified surface, and a lab surface built with an empty profile
reproduces it tile for tile. So a profile that changes one weight produces,
per tour, the metres its line moved.

That does mean production routes must be current. If routes.gpkg is older
than the surface or the tour file, you are measuring your change plus
whatever else drifted since - `compare` prints the dates so you can see it.

## What a profile is

A JSON file naming the tours and the parameters:

    {
      "name": "steeper",
      "note": "does a 32 deg slope threshold pull routes off the ridges?",
      "tours": [42, 562, 716],
      "config": {"SLOPE": {"threshold": 32.0}}
    }

`tours` are FIDs in data/tours/tours.gpkg. FIDs, not a copied tours_test.gpkg,
and that is deliberate: copy features to a new GeoPackage and OGR renumbers
them, so `tour_fid` in the copy no longer points at the tour production routed
under that id, and two experiments started from different copies cannot be
compared to each other either. One tour file, one set of ids, forever.

`config` is applied by config.py itself at import - see the bottom of that
file for why it has to happen there and not here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Stdlib and paths only. paths.py reads no parameter and imports no module
# that does, so it is safe before the profile is in the environment;
# everything else is imported inside the stages, after main() has set it.
from skimap import paths

LAB = paths.DATA / "test" / "lab"
PROFILES = LAB / "profiles"

# The production routes every experiment is measured against.
REFERENCE = paths.ROUTES / "routes.gpkg"

# Route colours, picked against the ArcGIS ramp rather than in the abstract.
# That ramp runs green -> yellow -> orange -> brown -> black, so an orange
# line disappears into steep ground exactly where you most want to see where
# it went. These two hues appear nowhere in it, and each is drawn over a dark
# casing so it also reads on the pale corridor bands and on a black barrier.
NEW_ROUTE = "#2e9bff"    # this profile
OLD_ROUTE = "#ffffff"    # the production route it is measured against

COMPARISON_FIELDS = (
    ("ref_len_m", "OFTReal"),     # the production route's length, same tour
    ("len_diff_m", "OFTReal"),    # this one minus that one
    ("cost_diff", "OFTReal"),     # cost_opt difference, lab minus production
    ("sep_mean_m", "OFTReal"),    # mean distance between the two lines
    ("sep_max_m", "OFTReal"),     # worst distance - this is the one to sort on
)


@dataclass(frozen=True)
class Profile:
    path: Path
    name: str
    note: str
    fids: tuple[int, ...]
    overrides: bool = False   # does "config" ask for anything?

    @property
    def root(self) -> Path:
        return LAB / self.name

    @property
    def tiles_dir(self) -> Path:
        return self.root / "tiles"

    @property
    def vrt(self) -> Path:
        return self.root / "cost_surface.vrt"

    @property
    def routes(self) -> Path:
        return self.root / "routes.gpkg"

    @property
    def corridors(self) -> Path:
        return self.root / "corridors"

    @property
    def figures(self) -> Path:
        return self.root / "figures"

    @property
    def cost_raster(self) -> str:
        """Its own name in the GRASS mapset.

        Per profile, so two experiments' surfaces can sit in the mapset at
        once instead of relinking on every switch - and so a stale link can
        never hand one profile another's surface.
        """
        from skimap import routing

        return f"lab_{routing.slug(self.name)}"


def resolve(name_or_path: str) -> Path:
    """A profile by name (data/test/lab/profiles/<name>.json) or by path."""
    direct = Path(name_or_path)
    if direct.suffix and direct.exists():
        return direct.resolve()
    candidate = PROFILES / f"{Path(name_or_path).stem}.json"
    if candidate.exists():
        return candidate.resolve()
    if direct.exists():
        return direct.resolve()
    raise SystemExit(
        f"No profile {name_or_path!r}. Looked in {candidate} and at that path. "
        f"Make one with 'python -m skimap.lab init {name_or_path} --fid <id> ...'."
    )


def _read_json(path: Path) -> dict:
    # utf-8-sig: a profile is hand-edited on Windows, where Notepad and
    # PowerShell's Out-File both leave a BOM.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _inherited_fids(data: dict, path: Path, seen: Optional[list] = None) -> tuple[int, ...]:
    """The tour list, following "extends" to another profile if there is one.

    Only the TOUR LIST is inherited, never "config", and that asymmetry is
    deliberate. The tours are a fixed test set shared by every experiment -
    duplicating twenty-odd FIDs per profile means adding one tour later is an
    edit to every file, and a set that has silently drifted apart makes two
    runs incomparable without anything looking wrong. The parameters are the
    opposite case: a profile is read months later to answer "what did this
    one change?", and it can only answer that if the whole change is written
    in it. Inheriting config would put half the answer in another file.
    """
    seen = seen or []
    fids = tuple(int(f) for f in data.get("tours", []))
    parent = data.get("extends")
    if not parent:
        return fids
    if fids:
        raise SystemExit(f"{path.name} has both \"tours\" and \"extends\"; use one.")
    if path in seen:
        raise SystemExit("extends cycle: "
                         + " -> ".join(q.stem for q in seen + [path]))
    parent_path = resolve(str(parent))
    return _inherited_fids(_read_json(parent_path), parent_path, seen + [path])


def load(path: Path) -> Profile:
    data = _read_json(Path(path))
    fids = _inherited_fids(data, Path(path).resolve())
    if not fids:
        raise SystemExit(
            f"{path} lists no tours. Add FIDs from data/tours/tours.gpkg, or "
            f'"extends": "<another profile>" to reuse its set.'
        )
    return Profile(
        path=Path(path).resolve(),
        name=str(data.get("name") or Path(path).stem),
        note=str(data.get("note") or ""),
        fids=fids,
        overrides=bool(data.get("config")),
    )


def _live(profile: Profile) -> None:
    """Refuse to run unless config really did load this profile.

    The overlay is applied at import from SKIMAP_PROFILE, so importing
    skimap.lab into a session that already imported config leaves the
    parameters at their production values while every path here still says
    the experiment's name. That produces a full set of figures showing no
    change, which is indistinguishable from a change that did nothing - the
    one wrong answer this tool must not be able to give.
    """
    from skimap import config

    if config.PROFILE != profile.path:
        raise SystemExit(
            f"config loaded profile {config.PROFILE} but this run is {profile.path}.\n"
            f"Parameters would be production's, not the experiment's. Run the stage "
            f"through 'python -m skimap.lab', which sets SKIMAP_PROFILE before "
            f"importing anything that reads a parameter."
        )


def _tours(profile: Profile) -> list:
    from skimap import tours as tours_mod

    found = {t.fid: t for t in tours_mod.read_tours()}
    missing = [f for f in profile.fids if f not in found]
    if missing:
        raise SystemExit(f"No tour with fid {missing} in {paths.TOURS}")
    return [found[f] for f in profile.fids]


# --- which tiles ---------------------------------------------------------


def tiles_for(tours, *, buffer_m: Optional[float] = None) -> tuple[list[str], list[str]]:
    """The tiles the router can reach from these tours: (in the grid, outside it).

    Routing sets g.region to each tour's start/end bounding box plus a buffer
    and spreads r.cost only inside it, so the surface has to cover exactly
    that window and nothing beyond it is ever read. The buffer is computed
    with routing's own _region_buffer, not a copy of the formula - it scales
    with tour length, and a lab surface built to a different rule than the
    router uses would clip a route at a nodata edge and look like terrain.

    Tiles outside the national grid are returned separately rather than
    dropped silently. They are normal - a coastal tour's window runs into the
    sea, which was never tiled - but a long list of them means the tours are
    somewhere the surface does not cover.
    """
    from skimap import config, grid, routing

    ceiling = float(buffer_m if buffer_m is not None else config.ROUTING["region_buffer_m"])
    ox, oy = config.GRID_ORIGIN
    size = config.TILE_SIZE

    wanted: set[str] = set()
    for tour in tours:
        pad = routing._region_buffer(tour, ceiling)
        minx = min(tour.start[0], tour.end[0]) - pad
        maxx = max(tour.start[0], tour.end[0]) + pad
        miny = min(tour.start[1], tour.end[1]) - pad
        maxy = max(tour.start[1], tour.end[1]) + pad

        x = grid._snap_down(minx, ox)
        while x < maxx:
            y = grid._snap_down(miny, oy)
            while y < maxy:
                wanted.add(grid.tile_id(x, y))
                y += size
            x += size

    in_grid = {t.tile_id for t in grid.iter_tiles()}
    return sorted(wanted & in_grid), sorted(wanted - in_grid)


def plan_tiles(profile: Profile, *, buffer_m: Optional[float] = None) -> list[str]:
    _live(profile)
    tours = _tours(profile)
    tile_ids, outside = tiles_for(tours, buffer_m=buffer_m)

    profile.root.mkdir(parents=True, exist_ok=True)
    (profile.root / "tiles.json").write_text(
        json.dumps({"tiles": tile_ids, "outside_grid": outside,
                    "tours": list(profile.fids)}, indent=2),
        encoding="utf-8",
    )
    print(f"{len(profile.fids)} tours reach {len(tile_ids)} tiles"
          + (f" ({len(outside)} of their window is outside the national grid)" if outside else ""))
    return tile_ids


# --- the surface ---------------------------------------------------------


def _dump_config(profile: Profile) -> None:
    """Every parameter as the profile left it, beside the output it produced.

    A figure is looked at days after the run that made it, and "which weights
    was this?" is otherwise answered by trusting that the profile has not been
    edited since. This is the copy that cannot drift.
    """
    from skimap import config

    out = {}
    for key in dir(config):
        if key.startswith("_") or not key.isupper():
            continue
        try:
            json.dumps(getattr(config, key))
        except TypeError:
            continue
        out[key] = getattr(config, key)
    (profile.root / "config_used.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


def build_surface(profile: Profile, *, jobs: int = 1, force: bool = False,
                  buffer_m: Optional[float] = None) -> list[str]:
    """Build the tour's tiles with the profile applied, and mosaic them.

    A VRT and no COG. `mosaic --cog` exists because ArcGIS cannot read a VRT
    and because the national surface wants overviews; the router reads either,
    run_batch takes the path explicitly, and materializing 1.65 GB is most of
    what makes the national build slow. If you want to open a lab surface in
    ArcGIS, run mosaic.to_cog on it by hand.
    """
    from skimap import mosaic
    from skimap.cost_surface.surface import build_all

    tile_ids = plan_tiles(profile, buffer_m=buffer_m)
    failed = build_all(only=tile_ids, force=force, jobs=jobs, tiles_root=profile.tiles_dir)
    if failed:
        print(f"{len(failed)} tiles failed; the surface has holes: {failed[:10]}")
    mosaic.build_mosaic(out_path=profile.vrt, tiles_root=profile.tiles_dir)
    _dump_config(profile)
    return failed


# --- routing -------------------------------------------------------------


def route(profile: Profile, *, force: bool = False, buffer_m: Optional[float] = None,
          merge: bool = False):
    from skimap import routing

    _live(profile)
    if not profile.vrt.exists():
        raise SystemExit(f"No surface at {profile.vrt}. Run 'lab surface {profile.name}' first.")

    tours = _tours(profile)
    print(f"routing {len(tours)} tours through {profile.vrt}")
    return routing.run_batch(
        tours, out_dir=profile.root, buffer_m=buffer_m, force=force, merge=merge,
        # The tour list is a subset of the file by construction, and to
        # pruning every tour left out of a subset is indistinguishable from a
        # deleted one. Nothing else writes here, so there is nothing to prune.
        prune=False,
        surface=profile.vrt, cost_raster=profile.cost_raster,
    )


# --- what moved ----------------------------------------------------------


def reference_routes(against: Optional[str] = None) -> tuple[Path, str]:
    """What a profile is measured against: production, or another profile.

    Production is the default because it is the map you actually have. But it
    is only a fair reference while it is current, and when it is not - a stale
    national mosaic, a config change since it was routed - every profile
    inherits that drift and reads as a bigger change than it made. Pointing
    `against` at a control profile that differs by exactly one parameter
    removes it: whatever both share cancels, and what is left is the parameter.
    """
    if not against:
        return REFERENCE, "the production routes"
    path = LAB / against / "routes.gpkg"
    if not path.exists():
        raise SystemExit(f"No routes at {path}. Run 'lab route {against}' first.")
    return path, f"profile {against}"


def measure(profile: Profile, *, against: Optional[str] = None) -> list[dict]:
    """Per tour: the two lines, and how far apart they are.

    Reads only. `compare` writes the numbers onto routes.gpkg and prints them;
    `figures` draws them. Both start here so they can never disagree.

    `against` names another profile to measure from instead of production.
    """
    from osgeo import ogr

    from skimap import routing

    if not profile.routes.exists():
        raise SystemExit(f"No routes at {profile.routes}. Run 'lab route {profile.name}' first.")

    ref_path, _ = reference_routes(against)

    reference = {}
    if ref_path.exists():
        ref_ds = ogr.Open(str(ref_path))
        for feat in ref_ds.GetLayerByName(routing.ROUTES_LAYER):
            reference[feat.GetField("tour_fid")] = (
                feat.GetGeometryRef().Clone(),
                float(feat.GetField("length_m") or 0.0),
                float(feat.GetField("cost_opt") or 0.0),
            )
        ref_ds = None

    rows = []
    ds = ogr.Open(str(profile.routes))
    for feat in ds.GetLayerByName(routing.ROUTES_LAYER):
        fid = feat.GetField("tour_fid")
        geom = feat.GetGeometryRef().Clone()
        row = {
            "fid": fid,
            "name": feat.GetField("name") or f"tour_{fid}",
            "length_m": float(feat.GetField("length_m") or 0.0),
            "cost_opt": float(feat.GetField("cost_opt") or 0.0),
            "geom": geom,
            "ref_geom": None,
            "ref_len_m": None,
            "len_diff_m": None,
            "cost_diff": None,
            "sep_mean_m": None,
            "sep_max_m": None,
        }
        if fid in reference:
            ref_geom, ref_len, ref_cost = reference[fid]
            # Both directions, and that is not fussiness. routing.separation
            # samples along the FIRST line only, so a production route that
            # carries a loop the new one drops has every lab point sitting on
            # it and scores near zero - measured here, fid 243 came out at
            # 205 m one way and 1210 m the other, on a route that had lost
            # 2.1 km. The figures are sorted on this number, so understating
            # it puts the most-changed tour in the middle of the page.
            mean_a, max_a = routing.separation(geom, ref_geom)
            mean_b, max_b = routing.separation(ref_geom, geom)
            mean_sep, max_sep = (mean_a + mean_b) / 2.0, max(max_a, max_b)
            row.update(ref_geom=ref_geom, ref_len_m=ref_len,
                       len_diff_m=row["length_m"] - ref_len,
                       cost_diff=row["cost_opt"] - ref_cost,
                       sep_mean_m=mean_sep, sep_max_m=max_sep)
        rows.append(row)
    ds = None

    # Worst separation first: the whole point is to look at what changed, and
    # on most runs most tours will not have moved at all.
    rows.sort(key=lambda r: (r["sep_max_m"] is None, -(r["sep_max_m"] or 0.0)))
    return rows


def compare(profile: Profile, *, against: Optional[str] = None) -> list[dict]:
    """Write the comparison onto routes.gpkg and print it."""
    from osgeo import ogr

    from skimap import routing

    _live(profile)
    rows = measure(profile, against=against)

    ds = ogr.Open(str(profile.routes), 1)
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    defn = layer.GetLayerDefn()
    have = {defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())}
    for name, kind in COMPARISON_FIELDS:
        if name not in have:
            layer.CreateField(ogr.FieldDefn(name, getattr(ogr, kind)))

    by_fid = {r["fid"]: r for r in rows}
    for feat in layer:
        row = by_fid.get(feat.GetField("tour_fid"))
        if not row or row["sep_max_m"] is None:
            continue
        for name, _ in COMPARISON_FIELDS:
            feat.SetField(name, round(row[name], 1))
        layer.SetFeature(feat)
    ds = None

    _report(profile, rows, against=against)
    return rows


def _report(profile: Profile, rows: list[dict], *, against: Optional[str] = None) -> None:
    import numpy as np

    ref_path, ref_label = reference_routes(against)

    print(f"\n{profile.name}: {len(rows)} tours vs {ref_label}")
    if profile.note:
        print(f"  {profile.note}")

    if not ref_path.exists():
        print(f"  No routes at {ref_path} - nothing to compare against.")
        return

    # The baseline is only a baseline if it is current. Say so rather than
    # letting a months-old routes.gpkg pass for the surface as it is now.
    # Only production is checked: a control profile is built from the same
    # tiles as the profile beside it, so there is no drift between them to
    # warn about - which is the reason to use one.
    if not against:
        ref_age = ref_path.stat().st_mtime
        for label, path in (("tours", paths.TOURS),
                            ("national surface", paths.COST_SURFACE / "cost_surface.tif")):
            if path.exists() and path.stat().st_mtime > ref_age:
                print(f"  WARNING production routes.gpkg is OLDER than the {label}. "
                      f"Some of what follows is drift, not your change - re-run the "
                      f"national route stage to get a clean baseline, or measure "
                      f"against a control profile with --against.")

    scored = [r for r in rows if r["sep_max_m"] is not None]
    if not scored:
        print(f"  No tours in common with {ref_label}.")
        return
    if len(scored) < len(rows):
        print(f"  {len(rows) - len(scored)} tour(s) have no route in {ref_label} to compare to.")

    seps = np.array([r["sep_max_m"] for r in scored])
    moved = int((seps >= 10.0).sum())
    print(f"\n  moved at all (>10 m):  {moved} / {len(scored)}")
    for cut in (50.0, 250.0, 1000.0):
        print(f"  moved more than {cut:5.0f} m: {int((seps >= cut).sum()):4d} / {len(scored)}")
    print(f"  worst separation   median {np.median(seps):6.0f} m   max {seps.max():6.0f} m")

    print(f"\n  {'fid':>5}  {'tour':24s} {'sep max':>8} {'len diff':>9} {'cost diff':>10}")
    for r in scored:
        print(f"  {r['fid']:>5}  {r['name'][:24]:24s} {r['sep_max_m']:8.0f} "
              f"{r['len_diff_m']:+9.0f} {r['cost_diff']:+10.1f}")
    if moved == 0 and not profile.overrides:
        # An empty config is the baseline run, and nothing moving is the
        # whole point of it: it says the lab reproduces production on this
        # tour set, so anything that moves under a real profile is that
        # profile's doing and not an artifact of the smaller surface.
        print()
        print("  Nothing moved, and this profile changes nothing - so the "
              "lab reproduces production exactly on these tours. Any "
              "movement under a profile that sets something is that change.")
    elif moved == 0:
        print()
        print("  Nothing moved, though the profile does set something. "
              "Either the change is invisible to the router, or config did "
              "not load it - check the 'profile ...' line above.")


def reduction(profile: Profile, *, cog: bool = True) -> Path:
    """The track cost reduction as a map, on the cost surface's own grid.

    One Float32 raster per tile of this profile's set, mosaicked, showing the
    cost units the track step takes off each cell under THIS profile's
    settings. Open it over the cost surface to see where the tracks are
    actually paying and where they are not.

    Float32 and computed directly, not differenced out of two built surfaces.
    The surfaces are uint16 and rounded, and the mean delivered reduction is
    a few tenths of a cost unit, so subtracting one from the other would
    quantize most of the signal to zero and show a map of rounding.

    The arithmetic is surface.py's track step verbatim, reading the same
    config the build read - so what you see is what the router was given.
    """
    import numpy as np

    from skimap import config, grid, mosaic, paths, raster
    from skimap.data_preprocessing import tracks as track_scale

    _live(profile)
    tile_ids = plan_tiles(profile)
    scale = track_scale.load_scale()
    t = config.TRACKS
    out_dir = profile.root / "reduction"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"track reduction: curve={t.get('curve', 'linear')} "
          f"floor={t.get('presence_floor', 0.0)} power={t['power']} "
          f"max={t['max_reduction']} in the open, "
          f"{t['max_reduction_forest']} in forest")

    written, stats = [], []
    for tile in grid.iter_tiles(only=tile_ids):
        # normalize() applies `power` itself; see its docstring.
        unit = track_scale.normalize(
            raster.read_tile("tracks", tile, fill=0.0), scale)
        # Per-pixel ceiling, exactly as the build does it - see surface.py.
        ceiling = np.where(
            raster.read_mask("forest", tile),
            float(t["max_reduction_forest"]),
            float(t["max_reduction"]),
        )
        red = (ceiling * unit).astype(np.float32)
        # write_tile georeferences on the RASTER lattice, which is where the
        # cost surface sits - so this overlays it cell for cell rather than
        # half a pixel off. See raster.tile_origin.
        written.append(raster.write_tile(
            red, tile, out_dir / f"{tile.tile_id}.tif",
            dtype="Float32", nodata=config.NODATA))
        hit = red[red > 0]
        if hit.size:
            stats.append((hit.size / red.size, float(hit.mean()), float(hit.max())))

    vrt = mosaic.rasters.build_vrt(written, profile.root / "track_reduction.vrt")
    print()
    print(f"{len(written)} tiles -> {vrt}")
    if cog:
        # ArcGIS does not read a GDAL VRT - see the mosaic stage.
        tif = mosaic.to_cog(vrt, profile.root / "track_reduction.tif")
        print(f"  and {tif}")

    if stats:
        a = np.array(stats)
        print()
        print(f"{a[:, 0].mean():.1%} of cells get any reduction at all")
        print(f"  where it applies: mean {a[:, 1].mean():.3f} cost units, "
              f"max {a[:, 2].max():.2f}")
        print(f"  Classify 0.01 / 0.1 / 0.25 / 0.5 / 1 / 2 / 4 - a linear stretch")
        print(f"  shows almost nothing, the same way it does for the surface.")
    return vrt


def track_schemes() -> dict:
    """Every candidate TRACKS block: the one in config.py, plus each profile's.

    Read off the profiles rather than listed here, so a scheme you invented
    by writing a profile is automatically in the comparison and cannot fall
    out of step with the run it produced.
    """
    from skimap import config

    out = {"config.py": dict(config.TRACKS)}
    for path in sorted(PROFILES.glob("*.json")):
        try:
            block = _read_json(path).get("config", {}).get("TRACKS")
        except (OSError, ValueError):
            continue
        if block:
            out[path.stem] = {**config.TRACKS, **block}
    return out


def track_curves(profile: Profile, *, count: int = 5, max_px: int = 700) -> Path:
    """What each scheme actually pays, on ground with real track densities.

    A curve on its own says nothing about whether a scheme helps a quiet
    area: what matters is where that area's density DISTRIBUTION sits under
    the curve. So each panel draws both - the mapping from density to cost
    reduction for every scheme, over a filled histogram of the densities
    actually present around that tour.

    Tours are chosen to span the range, from the least tracked window in the
    profile to the most, because the question is precisely whether a scheme
    that suits Jotunheimen also gives Setesdal something.
    """
    import matplotlib
    matplotlib.use("Agg")

    import matplotlib.pyplot as plt
    import numpy as np

    from skimap import config, paths, routing
    from skimap.data_preprocessing import tracks as track_scale

    _live(profile)
    tours = _tours(profile)
    lo, hi = track_scale.load_scale()
    layer = paths.layer("tracks")
    ceiling = float(config.ROUTING["region_buffer_m"])

    # Density in each tour's own routing window - the ground the router can
    # actually reach, not an arbitrary square.
    windows = []
    for tour in tours:
        pad = routing._region_buffer(tour, ceiling)
        xs, ys = (tour.start[0], tour.end[0]), (tour.start[1], tour.end[1])
        extent = (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)
        arr = _read(layer, extent, max_px, nodata=0.0)
        if arr is None:
            continue
        pos = np.ma.compressed(arr)
        pos = pos[pos > 0]
        if pos.size < 50:
            continue
        windows.append((tour, pos, pos.size / max(arr.size, 1)))

    if not windows:
        raise SystemExit("No tour window has track data to plot.")
    windows.sort(key=lambda w: w[2])
    picks = [windows[round(i * (len(windows) - 1) / max(count - 1, 1))]
             for i in range(min(count, len(windows)))]

    schemes = track_schemes()
    grid_x = np.logspace(0, np.log10(max(60.0, float(max(p[1].max() for p in picks)))), 400)
    colours = plt.get_cmap("tab10").colors

    fig, axes = plt.subplots(len(picks), 1, figsize=(10, 3.0 * len(picks)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, (tour, pos, share) in zip(axes, picks):
        hist = ax.twinx()
        bins = np.logspace(0, np.log10(max(grid_x)), 45)
        hist.hist(pos, bins=bins, color="#b9c6d4", alpha=0.55,
                  weights=np.full(pos.size, 1.0 / pos.size))
        hist.set_ylabel("share of tracked px", fontsize=8, color="#6b7785")
        hist.tick_params(labelsize=7, colors="#6b7785")

        for i, (label, block) in enumerate(schemes.items()):
            # Plot what the code does, not a second implementation of it.
            # `reference=pos` so a per-tile scheme takes its percentiles from
            # this window's real densities while being drawn on the synthetic
            # axis; the continuous curves ignore it.
            unit = track_scale.normalize(grid_x.astype("float32"), (lo, hi),
                                         params=block, reference=pos)
            # The open-ground ceiling. This axis is density, which says
            # nothing about forest, so a forest pixel reads higher than the
            # curve drawn here - by max_reduction_forest / max_reduction.
            ax.plot(grid_x, unit * float(block["max_reduction"]),
                    lw=2.0, color=colours[i % len(colours)], label=label, zorder=3)

        ax.set_zorder(hist.get_zorder() + 1)
        ax.patch.set_visible(False)
        ax.set_xscale("log")
        ax.set_ylabel("cost units off", fontsize=9)
        ax.set_title(f"{tour.label}   -   {share:.1%} of the window has tracks, "
                     f"median density {np.median(pos):.0f}, p90 {np.percentile(pos, 90):.0f}",
                     fontsize=10, loc="left")
        ax.grid(alpha=0.25, zorder=0)

    axes[-1].set_xlabel("GPS track density (log scale)", fontsize=9)
    axes[0].legend(fontsize=8, loc="upper left", framealpha=0.9)
    fig.suptitle("What each scheme pays, against the densities actually there"
                 "  |  least-tracked window at the top, most-tracked at the bottom",
                 fontsize=11, y=0.999)
    fig.tight_layout()

    profile.figures.mkdir(parents=True, exist_ok=True)
    out = profile.figures / "track_curves.png"
    fig.savefig(out, bbox_inches="tight", dpi=110)
    plt.close(fig)

    print(f" {len(schemes)} schemes over {len(picks)} windows -> {out}")
    _track_table(picks, schemes, (lo, hi))
    return out


def _track_table(picks, schemes, scale) -> None:
    """Mean reduction each scheme delivers on each window's tracked ground."""
    import numpy as np

    from skimap import config
    from skimap.data_preprocessing import tracks as track_scale

    names = list(schemes)
    print()
    print(f"mean cost units taken off a TRACKED pixel")
    print(f"  {'window':26s} " + " ".join(f"{n[:15]:>15s}" for n in names))
    print("  " + "-" * (26 + 16 * len(names)))
    rows = []
    for tour, pos, _ in picks:
        cells = []
        for name in names:
            block = schemes[name]
            u = track_scale.normalize(pos.astype("float32"), scale, params=block)
            cells.append(float(u.mean()) * float(block["max_reduction"]))
        rows.append(cells)
        print(f"  {tour.label[:26]:26s} " + " ".join(f"{c:15.3f}" for c in cells))
    a = np.array(rows)
    print("  " + "-" * (26 + 16 * len(names)))
    print(f"  {'quietest / busiest':26s} " +
          " ".join(f"{a[-1, i] / max(a[0, i], 1e-9):14.1f}x" for i in range(len(names))))
    print()
    print("The last row is the fairness number: 1.0x would mean a track in the")
    print("  quietest window is worth exactly what it is worth in the busiest.")


def score(profile: Profile) -> None:
    """Both sides of the track tradeoff, as numbers.

    Following tracks is not free, and "how far did the line move" does not
    say whether the move was good. Two measures, and they pull opposite ways:

    TRACK COVERAGE - the share of the route standing on tracked ground, and
    the mean normalized density under it. This is what a track reduction buys
    and it goes up with the coefficient by construction, so on its own it is
    circular: it rewards the thing you turned up.

    EXPOSURE - the ExpScore of the line. This is the counterweight, and it is
    NOT circular: it is computed from the PRA and runout rasters, which the
    track layer never touches. Tracks are where people went, which is not the
    same as where it is safe to go, so a setting that buys coverage while
    driving exp_score up is buying route-following with avalanche terrain.

    Pick the setting that gains coverage without gaining exposure. That is a
    defensible answer; "it looked better" is not.
    """
    import numpy as np
    from osgeo import ogr

    from skimap import config, exposure, paths, routing
    from skimap.data_preprocessing import tracks as track_scale

    _live(profile)
    if not profile.routes.exists():
        raise SystemExit(f"No routes at {profile.routes}. Run 'lab route {profile.name}' first.")

    print(f"scoring {profile.routes}")
    exposure.score_routes(profile.routes)

    def read(path: Path) -> dict:
        ds = ogr.Open(str(path))
        out = {}
        for f in ds.GetLayerByName(routing.ROUTES_LAYER):
            out[f.GetField("tour_fid")] = (f.GetGeometryRef().Clone(),
                                           float(f.GetField("exp_score") or 0.0),
                                           float(f.GetField("exp_per_km") or 0.0))
        return out

    lab_rows = read(profile.routes)
    ref_rows = read(REFERENCE) if REFERENCE.exists() else {}

    lo, hi = track_scale.load_scale()
    layer = paths.layer("tracks")
    spacing = float(config.EXPOSURE["sample_spacing_m"])

    def coverage(geom):
        xy = exposure.sample_points(geom, spacing)
        d = exposure.sample_raster(layer, xy)
        d = np.where(np.isnan(d), 0.0, d)
        return float((d > 0).mean()), float(track_scale.normalize(d, (lo, hi)).mean())

    nan = float("nan")
    rows = []
    for fid, (geom, exp, per_km) in lab_rows.items():
        share, unit = coverage(geom)
        ref = ref_rows.get(fid)
        r_share, r_unit = coverage(ref[0]) if ref else (nan, nan)
        rows.append((share, unit, exp, per_km,
                     r_share, r_unit, ref[1] if ref else nan, ref[2] if ref else nan))

    a = np.array(rows, dtype=float)
    print()
    print(f"{profile.name}: {len(rows)} routes")
    print(f"  {'':22s} {'this profile':>13} {'production':>12} {'change':>10}")
    for label, i, j, pct in (("on tracked ground", 0, 4, True),
                             ("mean track density", 1, 5, False),
                             ("exposure, total", 2, 6, False),
                             ("exposure per km", 3, 7, False)):
        mine, theirs = np.nanmean(a[:, i]), np.nanmean(a[:, j])
        fmt = (lambda v: f"{v:.1%}") if pct else (lambda v: f"{v:.3f}")
        print(f"  {label:22s} {fmt(mine):>13} {fmt(theirs):>12} "
              f"{(mine - theirs) / theirs if theirs else 0:+10.1%}")

    d_cov = np.nanmean(a[:, 0]) - np.nanmean(a[:, 4])
    # Per km, not total. ExpScore is a dose summed along the line, so a route
    # that got shorter scores lower for being shorter rather than for picking
    # safer ground - and every track setting changes length. The rate is the
    # only one of the two that says which terrain was chosen.
    d_exp = np.nanmean(a[:, 3]) - np.nanmean(a[:, 7])
    print()
    print("  Judge on exposure PER KM: the total is a dose and every track")
    print("  setting changes route length, so the total moves for that alone.")
    print()
    if abs(d_cov) < 1e-9 and abs(d_exp) < 1e-9:
        print("  Identical to production on both measures.")
    elif d_cov > 0 and d_exp <= 0:
        print("  More track-following AND no more exposure. That is the trade you want.")
    elif d_cov > 0:
        print(f"  More track-following, but exposure is up {d_exp:+.2f} too - the "
              f"coverage is being bought with avalanche terrain.")
    elif d_cov < 0 and d_exp < 0:
        print("  Less track-following and less exposure - a safer, less social line.")
    else:
        print("  Less track-following and no exposure gain: this setting costs "
              "without buying.")


# --- figures -------------------------------------------------------------


def figures(profile: Profile, *, pad: float = 0.18, max_px: int = 1100,
            style: Optional[Path] = None, show_tracks: bool = True,
            against: Optional[str] = None) -> Path:
    """One PNG per tour, worst-moved first, and an index.html over them.

    The background is the lab cost surface under the ArcGIS symbology in
    data/styles_arcgis/cost_surface.tif.lyrx, read at render time - so a
    figure looks like the map you already have open, and re-styling the layer
    in ArcGIS and re-running this stage is all it takes to change these.
    `style` points at a different .lyrx. If none can be read it falls back to
    config.DISPLAY_BREAKS and says so.

    It is the surface the new route actually walked, which is what makes the
    picture answer "why there": the line follows the cheap ground you can see
    underneath it.
    """
    import matplotlib
    matplotlib.use("Agg")   # no display, and this must precede pyplot

    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from matplotlib.lines import Line2D

    from skimap import config

    _live(profile)
    rows = measure(profile, against=against)
    ref_label = against or "production"
    profile.figures.mkdir(parents=True, exist_ok=True)

    cost_cmap, norm = _style(style)
    # Banded, not a continuous wash. Over flat ground a balanced corridor is
    # enormous - max_gap 300 buys kilometres of sideways room where a cell
    # costs 1 - so it routinely covers the whole frame, and a smooth veil over
    # all of it just desaturates the surface and shows nothing. Quantized into
    # a few steps you read the falloff instead: where the band is tight around
    # the line, and where it opens out.
    corridor_levels = [1e-6, 0.05, 0.2, 0.45, 0.75, 1.0]
    corridor_cmap = ListedColormap([(1, 1, 1, a) for a in (0.06, 0.13, 0.22, 0.31, 0.40)])

    written = []
    for row in rows:
        extent = _extent(row, pad)
        surface = _read(profile.vrt, extent, max_px, nodata=config.COST_NODATA)
        if surface is None:
            print(f"  {row['fid']}: nothing readable at that extent, skipped")
            continue

        fig, ax = plt.subplots(figsize=(9, 9), dpi=110)
        ax.imshow(surface, extent=extent, origin="upper", cmap=cost_cmap,
                  norm=norm, interpolation="nearest")
        ax.set_facecolor("none")

        drew_tracks = False
        if show_tracks:
            alpha = _tracks(extent, max_px)
            if alpha is not None:
                # Magenta appears nowhere in the .lyrx ramp and nowhere in
                # the route colours, so tracks cannot be mistaken for terrain
                # or for a line. Under the routes: the question these answer
                # is whether a route followed a track, and a route hidden
                # beneath the tracks cannot answer it.
                rgba = np.zeros(alpha.shape + (4,), dtype=float)
                rgba[..., 0], rgba[..., 1], rgba[..., 2] = 0.93, 0.16, 0.72
                rgba[..., 3] = np.ma.filled(alpha, 0.0)
                ax.imshow(rgba, extent=extent, origin="upper",
                          interpolation="nearest", zorder=2)
                drew_tracks = True

        corridor = _corridor_path(profile, row["fid"])
        if corridor is not None:
            band = _read(corridor, extent, max_px, nodata=config.NODATA)
            if band is not None:
                filled = np.ma.filled(band, 0.0)
                ax.contourf(filled, levels=corridor_levels, colors=corridor_cmap.colors,
                            extend="neither", extent=extent, origin="upper")
                # A dark hairline for the outer edge, and deliberately NOT
                # the cased-white treatment the routes get - two things drawn
                # the same way read as the same thing, and the corridor edge
                # is not a route.
                ax.contour(filled, levels=[1e-6], colors="#2b2b2b",
                           linewidths=0.9, alpha=0.55,
                           extent=extent, origin="upper")

        if row["ref_geom"] is not None:
            x, y = _xy(row["ref_geom"])
            ax.plot(x, y, color="#141414", lw=4.0, zorder=4)
            ax.plot(x, y, color=OLD_ROUTE, lw=1.8, zorder=5)
        x, y = _xy(row["geom"])
        ax.plot(x, y, color="#141414", lw=4.4, zorder=6)
        ax.plot(x, y, color=NEW_ROUTE, lw=2.2, zorder=7)
        ax.plot(x[0], y[0], "o", ms=9, mfc=NEW_ROUTE, mec="#141414", mew=1.5, zorder=8)
        ax.plot(x[-1], y[-1], "^", ms=11, mfc=NEW_ROUTE, mec="#141414", mew=1.5, zorder=8)

        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{row['fid']:03d}  {row['name']}", fontsize=14, loc="left", pad=10)
        ax.set_xlabel(_subtitle(row), fontsize=10, labelpad=8)

        handles = [Line2D([], [], color=NEW_ROUTE, lw=2.6, label=f"{profile.name} (new)")]
        if row["ref_geom"] is not None:
            handles.append(Line2D([], [], color=OLD_ROUTE, lw=2.6, label=f"{ref_label} (ref)"))
        if drew_tracks:
            handles.append(Line2D([], [], color="#ed29b8", lw=2.6, alpha=0.8,
                                  label="GPS tracks"))
        legend = ax.legend(handles=handles, loc="upper right", fontsize=9,
                           facecolor="#1c1f24", edgecolor="#3a3f47", framealpha=0.92)
        for text in legend.get_texts():
            text.set_color("#e6e6e6")

        out = profile.figures / f"{row['fid']:03d}_{_slug(row['name'])}.png"
        fig.tight_layout()
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        written.append((out, row))

    index = _write_index(profile, written)
    print(f"\n{len(written)} figures -> {profile.figures}")
    print(f"open {index}")
    return index


def _tracks(extent, max_px: int):
    """The GPS track layer over one window, as (alpha, present) or None.

    Alpha carries the NORMALIZED density - the same [0,1] the cost surface
    reduces on, from the one national scale - so what you see is what the
    router was paid to follow, not raw passage counts.

    But it floors at a visible value wherever there is any track at all,
    because the two cases you have to tell apart are "nobody has been here"
    and "somebody has, and it earned no discount". The national scale starts
    at the 60th percentile of positive pixels, so a single passage normalizes
    to zero; drawn on a plain density ramp it would be indistinguishable from
    empty ground, which is exactly the distinction the overlay is for.

    Returns None where the source does not reach - the national track
    rasters cover about 56% of the tiles, so an empty window is normal.
    """
    import numpy as np

    from skimap import paths
    from skimap.data_preprocessing import tracks as track_scale

    try:
        raw = _read(paths.layer("tracks"), extent, max_px, nodata=0.0)
    except (OSError, RuntimeError, FileNotFoundError):
        return None
    if raw is None or raw.count() == 0:
        return None

    lo, hi = track_scale.load_scale()
    unit = track_scale.normalize(np.ma.filled(raw, 0.0), (lo, hi))
    present = ~np.ma.getmaskarray(raw)
    alpha = np.where(present, 0.16 + 0.62 * unit, 0.0)
    return np.ma.masked_where(~present, alpha)


def _style(path: Optional[Path] = None):
    """The cost surface colours for a figure, from the ArcGIS .lyrx.

    Falls back to a stock colormap if the style cannot be read. A broken style
    file must not cost you the run: the figures are the output, the symbology
    is only how they are painted, and a printed reason beats a traceback after
    the routing is already paid for.
    """
    from matplotlib import colormaps
    from matplotlib.colors import Normalize

    try:
        # Imported inside the try, not above it: the fallback is only reachable
        # if the import itself is one of the things that can fail.
        from skimap import lyrx

        cmap, norm = lyrx.colormap(path)
        print(f"  symbology {lyrx.describe(path)}")
        return cmap, norm
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print(f"  symbology falling back to a stock ramp ({exc})")

    from skimap import config

    cmap = colormaps["magma_r"].copy()
    cmap.set_bad((1, 1, 1, 0))
    return cmap, Normalize(vmin=config.MIN_COST, vmax=config.BASE_MAX_COST)


def _slug(text: str) -> str:
    from skimap import routing

    return routing.slug(text)


def _corridor_path(profile: Profile, fid: int) -> Optional[Path]:
    if not profile.corridors.is_dir():
        return None
    hits = [p for p in profile.corridors.glob("*.tif")
            if p.name.split("_", 1)[0].isdigit() and int(p.name.split("_", 1)[0]) == fid]
    return hits[0] if hits else None


def _extent(row: dict, pad: float) -> tuple[float, float, float, float]:
    """Both lines in one window, padded, and never narrower than a square.

    Square because two lines of very different shape share a figure, and a
    long thin extent puts one of them in a sliver of it.
    """
    boxes = [row["geom"].GetEnvelope()]
    if row["ref_geom"] is not None:
        boxes.append(row["ref_geom"].GetEnvelope())
    minx = min(b[0] for b in boxes)
    maxx = max(b[1] for b in boxes)
    miny = min(b[2] for b in boxes)
    maxy = max(b[3] for b in boxes)

    side = max(maxx - minx, maxy - miny, 500.0) * (1.0 + 2 * pad)
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    return (cx - side / 2, cx + side / 2, cy - side / 2, cy + side / 2)


def _read(src: Path, extent, max_px: int, *, nodata: float):
    """A window of a raster as a masked array on exactly `extent`.

    gdal.Warp rather than a hand-rolled window read: the extent is arbitrary
    and routinely runs off the edge of a lab surface built from a dozen tiles,
    and Warp fills that with nodata instead of failing.
    """
    import numpy as np
    from osgeo import gdal

    from skimap import config

    gdal.UseExceptions()
    minx, maxx, miny, maxy = extent
    res = max(config.PIXEL_SIZE, (maxx - minx) / max_px)
    try:
        mem = gdal.Warp("", str(src), format="MEM", outputBounds=(minx, miny, maxx, maxy),
                        xRes=res, yRes=res, resampleAlg="near",
                        dstNodata=nodata, errorThreshold=0)
    except RuntimeError:
        return None
    if mem is None:
        return None
    arr = mem.GetRasterBand(1).ReadAsArray()
    mem = None
    if arr is None:
        return None
    return np.ma.masked_equal(arr.astype("float32"), float(nodata))


def _xy(geom):
    pts = [geom.GetPoint_2D(i) for i in range(geom.GetPointCount())]
    if not pts:   # multilinestring, if v.generalize ever hands one back
        merged = geom.GetGeometryRef(0)
        pts = [merged.GetPoint_2D(i) for i in range(merged.GetPointCount())]
    return [p[0] for p in pts], [p[1] for p in pts]


def _subtitle(row: dict) -> str:
    if row["sep_max_m"] is None:
        return f"{row['length_m'] / 1000:.2f} km   cost {row['cost_opt']:,.0f}   (no production route)"
    return (f"{row['length_m'] / 1000:.2f} km   "
            f"moved up to {row['sep_max_m']:,.0f} m (mean {row['sep_mean_m']:,.0f} m)   "
            f"length {row['len_diff_m']:+,.0f} m   cost {row['cost_diff']:+,.1f}")


def _write_index(profile: Profile, written: list) -> Path:
    """One scrollable page, worst-moved first."""
    cards = []
    for out, row in written:
        cards.append(
            f'<figure><img src="{out.name}" loading="lazy" alt="{row["name"]}">'
            f'<figcaption><b>{row["fid"]:03d} {row["name"]}</b><br>{_subtitle(row)}</figcaption>'
            f"</figure>"
        )
    html = f"""<!doctype html><meta charset="utf-8"> <title>{profile.name}</title>
<style>
 body {{ font: 14px/1.5 system-ui, sans-serif; margin: 2rem; background: #14161a; color: #e6e6e6; }}
 h1 {{ font-size: 1.4rem; margin: 0 0 .3rem; }}
 p.note {{ color: #9aa0a6; margin: 0 0 1.5rem; }}
 .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); gap: 1.5rem; }}
 figure {{ margin: 0; background: #1c1f24; border-radius: 8px; padding: .6rem; }}
 img {{ width: 100%; border-radius: 4px; display: block; }}
 figcaption {{ font-size: .82rem; color: #b8bcc2; padding: .55rem .2rem 0; }}
</style>
<h1>{profile.name}</h1>
<p class="note">{profile.note or "&nbsp;"}<br>
{len(written)} tours, worst-moved first. Orange is this profile, grey is production.</p>
<div class="grid">
{chr(10).join(cards)}
</div>
"""
    index = profile.figures / "index.html"
    index.write_text(html, encoding="utf-8")
    return index


# --- init ----------------------------------------------------------------


def init(name: str, fids: Optional[list[int]] = None, *, note: str = "",
         extends: Optional[str] = None, overwrite: bool = False) -> Path:
    out = PROFILES / f"{name}.json"
    if out.exists() and not overwrite:
        raise SystemExit(f"{out} exists. Edit it, or pass --overwrite.")
    if bool(fids) == bool(extends):
        raise SystemExit("Give either --fid (a new tour set) or --extends (reuse one).")
    PROFILES.mkdir(parents=True, exist_ok=True)

    body = {"name": name, "note": note or "what this experiment is asking"}
    if extends:
        body["extends"] = resolve(extends).stem
    else:
        body["tours"] = sorted(fids)
    body["config"] = {}
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")
    print(f"Wrote {out}\n"
          f"Put the change in its \"config\" object, then:\n"
          f"  python -m skimap.lab run {name} --jobs 8")
    return out


# --- cli -----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skimap.lab",
        description="Try a change to the cost surface on a few tours and look at it.",
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("init", help="write a starter profile")
    p.add_argument("name")
    p.add_argument("--fid", action="append", type=int, dest="fids",
                   help="a tour FID from data/tours/tours.gpkg; repeatable")
    p.add_argument("--extends", help="reuse another profile's tour set instead of "
                                     "listing FIDs again")
    p.add_argument("--note", default="")
    p.add_argument("--overwrite", action="store_true")

    for stage, help_text in (
        ("tiles", "just work out which tiles the tours reach"),
        ("surface", "build those tiles with the profile applied, and mosaic them"),
        ("route", "route the profile's tours through that surface"),
        ("compare", "how far each line moved from the production route"),
        ("figures", "one PNG per tour, plus index.html"),
        ("score", "track coverage and avalanche exposure, against production"),
        ("tracks", "what each scheme pays against the densities actually present"),
        ("reduction", "write the track reduction as a raster on the surface grid"),
        ("run", "surface, route, compare, figures"),
    ):
        p = sub.add_parser(stage, help=help_text)
        p.add_argument("profile")
        if stage in ("surface", "run"):
            p.add_argument("--jobs", type=int, default=1, help="parallel worker processes")
        if stage in ("surface", "route", "run", "tiles"):
            p.add_argument("--buffer", type=float,
                           help="region buffer ceiling in m (default config.ROUTING). "
                                "Set it here and the tile set follows it.")
        if stage in ("surface", "route", "run"):
            p.add_argument("--force", action="store_true",
                           help="rebuild tiles / re-route instead of resuming")
        if stage == "reduction":
            p.add_argument("--no-cog", action="store_true",
                           help="stop at the VRT; ArcGIS cannot read one")
        if stage in ("figures", "run"):
            p.add_argument("--hide-tracks", action="store_true",
                           help="leave the GPS track layer off the figures")
            p.add_argument("--style", type=Path,
                           help="an ArcGIS .lyrx to colour the cost surface with "
                                "(default data/styles_arcgis/cost_surface.tif.lyrx)")
        if stage in ("compare", "figures", "run"):
            p.add_argument("--against", metavar="PROFILE",
                           help="measure against another profile's routes instead of "
                                "production. Use a control that differs by one "
                                "parameter to see only that parameter.")

    args = parser.parse_args(argv)

    if args.stage == "init":
        init(args.name, args.fids, note=args.note, extends=args.extends,
             overwrite=args.overwrite)
        return 0

    # Before importing anything that reads a parameter. config applies the
    # overlay at import, and the ProcessPoolExecutor children inherit this.
    path = resolve(args.profile)
    os.environ["SKIMAP_PROFILE"] = str(path)
    profile = load(path)

    jobs = getattr(args, "jobs", 1)
    if jobs is not None and jobs <= 0:
        jobs = os.cpu_count() or 1
    buffer_m = getattr(args, "buffer", None)
    force = getattr(args, "force", False)

    if args.stage == "tiles":
        plan_tiles(profile, buffer_m=buffer_m)
        return 0

    if args.stage in ("surface", "run"):
        failed = build_surface(profile, jobs=jobs, force=force, buffer_m=buffer_m)
        if failed and args.stage == "run":
            return 1
        if args.stage == "surface":
            return 1 if failed else 0

    if args.stage in ("route", "run"):
        results = route(profile, force=force, buffer_m=buffer_m)
        if any(not r.ok for r in results):
            print("Some tours failed to route; compare and figures cover the rest.")

    if args.stage in ("compare", "run"):
        compare(profile, against=getattr(args, "against", None))

    if args.stage == "tracks":
        track_curves(profile)
        return 0

    if args.stage == "reduction":
        reduction(profile, cog=not args.no_cog)
        return 0

    if args.stage in ("score", "run"):
        score(profile)

    if args.stage in ("figures", "run"):
        figures(profile, style=getattr(args, "style", None),
                show_tracks=not getattr(args, "hide_tracks", False),
                against=getattr(args, "against", None))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
