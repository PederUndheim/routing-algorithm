"""Five tiles, ten fixed files, one settings file - what the GPS tracks do.

skimap.track_test answers "are the tracks worth anything at all?" nationally,
by building the whole country twice and routing every tour through both. This
answers the question you ask next, which is a different one: *these* settings,
on ground where the track data is sparse, dense, forested, alpine - what do
they actually take off, and where?

So this is not the lab. The lab varies a parameter and shows you the routes it
moved; this varies the track parameters and shows you the RASTER, on five
tiles picked to span what the national track layer looks like. You keep the
files open in ArcGIS, change a number, re-run, and refresh. The filenames
never change, so the symbology, the layer order and the map you built around
them all survive every run.

    python -m skimap.track_scenarios init      # write settings.json
    python -m skimap.track_scenarios rasters   # the ten tifs
    python -m skimap.track_scenarios run       # rasters, then routes

Everything lands in data/test/track_scenarios/:

    01_etne_cost.tif        the cost surface, uint16, as the router reads it
    01_etne_reduction.tif   cost units the tracks took off, Float32
    02_bykle_cost.tif       ... and so on, for all five areas
    ...
    settings.json           the one file you edit
    settings_used.json      every parameter as the last run actually applied it
    stats.csv               one row per area per run, appended - the audit trail
    routes.gpkg             routes through these tiles, if you ran `route`

Ten raster files, and never an eleventh. A run builds into _work/ and then
replaces the published files, so a half-written raster is never what ArcGIS is
drawing and an interrupted run leaves the previous set whole.

Nothing here touches data/cost_surface or data/routing_output. That matters
more than it sounds: `cost --area X --debug` writes its tile straight into
data/cost_surface/tiles/, so running the production CLI under experimental
track settings quietly replaces production tiles with them. This never does.

## The settings file

    {
      "note":   "does presence_floor rescue the sparse coast?",
      "config": {"TRACKS": {"presence_floor": 0.25}},
      "scale":  {"lower": 2.0, "upper": 11.0}
    }

`config` is a config.py overlay, applied by config.py itself at import from
SKIMAP_PROFILE - the same mechanism skimap.lab uses, and for the same reason
(see the bottom of config.py). A misspelled parameter is an error rather than
a silent no-op, which is the one failure this must not have: a raster showing
no change is indistinguishable from a change that did nothing.

`scale` is the one knob that is NOT in config.py. It only matters for
curve="linear"/"log" - "tile_bands" ignores it. The pair is computed once
nationally into data/grid/track_scale.json, and re-deriving it is a full pass
over the national track raster, so this takes the two numbers directly.
Omit `scale`, or set it to null, for the national pair.

Those two numbers do half the work. At the national lower = 2.0 with the linear
curve, every pixel carrying one or two passages maps to exactly zero reduction -
and on the sparse coastal tiles that is over 80% of all the track evidence
there is. `presence_floor` and `lower` are the two ways to change that, and
this is the tool for seeing which one you want.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

# Stdlib and paths only at module level. paths.py reads no parameter and
# imports nothing that does, so it is safe before SKIMAP_PROFILE is in the
# environment; everything else is imported inside a stage, after main() has
# set it. Import config up here and a run silently uses production values
# while every path still carries this experiment's name.
from skimap import paths

ROOT = paths.DATA / "test" / "track_scenarios"
SETTINGS = ROOT / "settings.json"
USED = ROOT / "settings_used.json"
STATS = ROOT / "stats.csv"

# Scratch. Tiles are built here and the two published rasters are moved out of
# it, so nothing ArcGIS has open is ever written to directly.
WORK = ROOT / "_work"
TILES = WORK / "tiles"
LAYERS = WORK / "layers"
VRT = WORK / "surface.vrt"

ROUTES = ROOT / "routes.gpkg"

# `route`/`run` overwrite ROUTES every time, on purpose - that is what keeps
# it a fixed name ArcGIS can hold open. So a route comparison across several
# settings needs its own copies: `--save NAME` snapshots the just-written
# routes.gpkg here, untouched by the next run, so two or five settings can
# sit side by side instead of each erasing the last.
RUNS = ROOT / "runs"

# Its own name in the GRASS mapset, beside nat_cost and the lab surfaces, so
# switching between them never relinks and a stale link cannot hand this run
# somebody else's surface.
COST_RASTER = "trackscen_cost"

# The production routes a scenario route is measured against.
REFERENCE = paths.ROUTES / "routes.gpkg"

# build_cost_surface writes nine debug layers; asking for three keeps a run
# at a few tens of MB of intermediates instead of 310.
REDUCTION_LAYER = "08_track_reduction"

# The two layers stats() needs to find out whether a reduction actually
# survives rounding. clip_round runs on the cost AFTER tracks are subtracted,
# not on the reduction itself - see the note on `bite_pct` in stats() - so
# knowing the reduction alone is not enough. cost right before that
# subtraction is max(07_after_reductions, 05_barriers): 07 is what `cost`
# holds when the barriers-win-back MAX runs, and that MAX is not itself
# logged as its own debug layer.
PRE_TRACK_LAYERS = ("05_barriers", "07_after_reductions")


# --- the five areas ------------------------------------------------------
# Picked by measuring rather than by reputation: every tile in the national
# grid was scanned for GPS-track coverage, and these five span what that scan
# found. The numbers in `why` are at config.py as committed - lower 2.0,
# upper 11.0, linear, power 2.0, presence_floor 0.0 - and are what a run
# reproduces in stats.csv when settings.json is left at its defaults.
#
# Ordered by track coverage, sparse first, so the files sort in the ArcGIS
# table of contents the way you want to read them.
#
# To swap one, change the tile id here, or override the whole set with an
# "areas" object in settings.json. Nothing else in this file knows which
# tiles these are.
AREAS: dict[str, dict] = {
    "01_etne": {
        "tile": "tile_4500_6659500",
        "place": "Etne / Sunnhordland - the south west coast",
        "why": "0.12% of the tile carries any track, and 82% of that earns "
               "nothing at all. The sparse end: evidence exists, and the "
               "scale discards it.",
    },
    "02_bykle": {
        "tile": "tile_64500_6599500",
        "place": "Bykle / Setesdal",
        "why": "54% of its tracked pixels are in forest, by far the highest "
               "of the five - `forest_pct` in the stats table is still read "
               "off this tile for that reason, even though the reduction "
               "itself no longer treats forest any differently.",
    },
    "03_voss": {
        "tile": "tile_44500_6739500",
        "place": "Voss",
        "why": "7.3% coverage over mixed forest and alpine ground - the "
               "ordinary case, and the one most of the country resembles.",
    },
    "04_isfjorden": {
        "tile": "tile_124500_6959500",
        "place": "Isfjorden / Molde - study area isfjorden_01",
        "why": "carries the national maximum density, 2258 passages on one "
               "pixel, and 14% of its tracked pixels sit at or above the top "
               "of the scale. Where `upper` and `power` bite.",
    },
    "05_sjodalen": {
        "tile": "tile_164500_6819500",
        "place": "Sjodalen / Vaaga - eastern Jotunheimen",
        "why": "the densest ground in the country after Lom: 11% coverage "
               "and 2% forest - dense, treeless traffic with nothing else "
               "confounding it.",
    },
}

DEFAULT_SETTINGS = {
    "note": "baseline - config.py as committed",
    "config": {
        "TRACKS": {
            "max_reduction": 3.0,
            "power": 2.0,
            "curve": "tile_bands",
            "presence_floor": 0.0,
            "bands": [[50.0, 0.5], [80.0, 1.0]],
            "min_positive_px": 200,
            "min_density": 3.0,
        }
    },
    "scale": None,
}


# --- settings ------------------------------------------------------------


def read_settings() -> dict:
    # utf-8-sig, not utf-8: this is a file you edit by hand on Windows, where
    # Notepad and PowerShell's Out-File both leave a BOM.
    return json.loads(SETTINGS.read_text(encoding="utf-8-sig"))


def init(*, force: bool = False) -> Path:
    """Write settings.json, unless one is already there with your edits in it."""
    ROOT.mkdir(parents=True, exist_ok=True)
    if SETTINGS.exists() and not force:
        print(f"{SETTINGS} already exists - left alone. --force overwrites it.")
        return SETTINGS
    SETTINGS.write_text(json.dumps(DEFAULT_SETTINGS, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SETTINGS}")
    return SETTINGS


def areas() -> dict[str, dict]:
    """The five, with any override from settings.json applied."""
    if not SETTINGS.exists():
        return AREAS
    override = read_settings().get("areas")
    if not override:
        return AREAS
    return {name: (spec if isinstance(spec, dict)
                   else {"tile": spec, "place": "", "why": ""})
            for name, spec in override.items()}


def scale_override() -> Optional[tuple[float, float]]:
    """The (lower, upper) density pair from settings.json, if it names one."""
    if not SETTINGS.exists():
        return None
    spec = read_settings().get("scale")
    if not spec:
        return None
    lower, upper = float(spec["lower"]), float(spec["upper"])
    if upper <= lower:
        raise SystemExit(
            f'settings.json "scale" has lower={lower:g} >= upper={upper:g}. '
            "The normalization divides by their difference, so it has to be "
            "positive."
        )
    return lower, upper


def _live() -> None:
    """Refuse to run unless config really did load settings.json.

    The overlay is applied at import from SKIMAP_PROFILE. Import config before
    that variable is set - directly, or through any module that reads a
    parameter - and every parameter stays at its production value while the
    output still lands here with this run's name on it. That produces a full
    set of rasters showing no change, which is exactly what a change that did
    nothing produces.
    """
    from skimap import config

    if not SETTINGS.exists():
        return
    if config.PROFILE != SETTINGS.resolve():
        raise SystemExit(
            f"config loaded {config.PROFILE}, not {SETTINGS}.\n"
            "Parameters would be production's, not this run's. Go through "
            "'python -m skimap.track_scenarios', which sets SKIMAP_PROFILE "
            "before importing anything that reads a parameter."
        )


def _dump_used(scale: tuple[float, float]) -> None:
    """Every parameter as this run left it, beside the rasters it produced.

    A raster is looked at days after the run that made it, and "which settings
    was this?" is otherwise answered by trusting that settings.json has not
    been edited since. This is the copy that cannot drift.
    """
    from skimap import config

    out = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "note": read_settings().get("note", "") if SETTINGS.exists() else "",
        "scale_used": {"lower": scale[0], "upper": scale[1]},
        "areas": {name: spec["tile"] for name, spec in areas().items()},
    }
    for key in dir(config):
        if key.startswith("_") or not key.isupper():
            continue
        try:
            json.dumps(getattr(config, key))
        except TypeError:
            continue
        out[key] = getattr(config, key)
    USED.write_text(json.dumps(out, indent=2), encoding="utf-8")


# --- publishing ----------------------------------------------------------


def _publish(src: Path, dst: Path) -> bool:
    """Move a freshly built raster onto its published name, atomically.

    ArcGIS Pro holds an open handle on every raster in an open map, and
    Windows will not replace a file another process has open. So the build
    goes to _work/ and only this final move can fail - which means a failure
    leaves the previously published raster whole and drawable rather than
    half-overwritten. What is new is still on disk; `publish` moves it once
    the layer is closed.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
        return True
    except OSError as exc:
        print(f"  LOCKED  {dst.name}: {exc.strerror or exc}")
        return False


def _pending() -> list[tuple[Path, Path]]:
    """Built rasters still sitting in _work/ because the move could not land."""
    waiting = []
    for name in areas():
        for kind in ("cost", "reduction"):
            staged = WORK / f"{name}_{kind}.tif"
            if staged.exists():
                waiting.append((staged, ROOT / f"{name}_{kind}.tif"))
    return waiting


def publish() -> int:
    """Move whatever is waiting in _work/ onto the published names.

    Run this after closing the layers, when a run reported files as locked.
    """
    waiting = _pending()
    if not waiting:
        print("Nothing waiting in _work/ - the published rasters are current.")
        return 0
    print(f"{len(waiting)} file(s) waiting")
    stuck = [dst for src, dst in waiting if not _publish(src, dst)]
    if stuck:
        print(f"\n{len(stuck)} still locked. Close them in ArcGIS - remove the "
              f"layer, not just the map - and run this again.")
        return 1
    print("published.")
    return 0


# --- the rasters ---------------------------------------------------------


def build_rasters(*, jobs: int = 1) -> list[str]:
    """Build the five tiles and publish their cost and reduction rasters."""
    from skimap.cost_surface.surface import build_all
    from skimap.data_preprocessing import tracks as track_scale

    _live()
    chosen = areas()
    override = scale_override()
    scale = override or track_scale.load_scale()
    print(f"track scale: lower={scale[0]:g} upper={scale[1]:g}"
          + ("  (settings.json)" if override else "  (national)"))

    for directory in (WORK, TILES, LAYERS):
        directory.mkdir(parents=True, exist_ok=True)

    tile_ids = [spec["tile"] for spec in chosen.values()]
    labels = {spec["tile"]: name for name, spec in chosen.items()}
    # force=True always. The whole point is that the settings changed, and a
    # tile left over from the last run says nothing about the current ones.
    failed = build_all(only=tile_ids, force=True, jobs=jobs, debug=True,
                       labels=labels, tiles_root=TILES, scale=scale,
                       debug_root=LAYERS,
                       debug_only=(REDUCTION_LAYER, *PRE_TRACK_LAYERS))
    if failed:
        print(f"{len(failed)} tile(s) failed: {failed}")

    print()
    locked = []
    published = 0
    for name, spec in chosen.items():
        if spec["tile"] in failed:
            continue
        sources = (
            (TILES / spec["tile"] / "cost_surface.tif", "cost"),
            (LAYERS / name / f"{REDUCTION_LAYER}.tif", "reduction"),
        )
        for src, kind in sources:
            if not src.exists():
                print(f"  MISSING {src}")
                continue
            staged = WORK / f"{name}_{kind}.tif"
            shutil.copyfile(src, staged)
            if _publish(staged, ROOT / f"{name}_{kind}.tif"):
                published += 1
            else:
                locked.append(f"{name}_{kind}.tif")

    if locked:
        print(f"\n{len(locked)} published file(s) are open elsewhere and were not "
              f"replaced.\nThe new rasters are built and waiting in {WORK}.\n"
              f"Close the layers in ArcGIS, then:\n"
              f"    python -m skimap.track_scenarios publish")
    else:
        print(f"\n{published} rasters -> {ROOT}")

    _dump_used(scale)
    return failed


# --- what the settings delivered ----------------------------------------


def _read_float_layer(path: Path):
    """A Float32 debug layer, with its NODATA sentinel mapped to 0."""
    import numpy as np
    from osgeo import gdal

    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue()
    ds = None
    if nodata is not None:
        arr = np.where(arr == np.float32(nodata), 0.0, arr)
    return arr


def stats(*, append: bool = True) -> list[dict]:
    """Per area: how much track evidence there is, and how much of it counted.

    Read back off the rasters in `_work/layers/`, which is what the last
    `rasters` or `run` actually built - not recomputed from settings.json, so
    a `stats` run between edits still reports the run that is really on disk.

    `bite_pct` needs more than the reduction alone. clip_round in surface.py
    rounds the cost AFTER tracks are subtracted, not the reduction itself, so
    whether a reduction survives depends on where the pre-track cost's
    fractional part sits - a reduction of 0.9 can round away to nothing at one
    pixel, and, rarely, one of 0.2 can flip the integer at another. This
    reconstructs the actual before/after integer cost with `combine.clip_round`,
    the same function surface.py calls, and compares them directly rather than
    guessing from the reduction's size.
    """
    import numpy as np
    from osgeo import gdal

    from skimap import config, grid
    from skimap.cost_surface import combine
    from skimap.raster import read_mask, read_tile

    gdal.UseExceptions()
    _live()

    tiles = {tile.tile_id: tile for tile in grid.iter_tiles()}
    tour_counts = _tours_by_tile()
    scale = scale_override()
    if scale is None:
        from skimap.data_preprocessing import tracks as track_scale
        scale = track_scale.load_scale()

    rows = []
    for name, spec in areas().items():
        # From _work/layers/, the last BUILD's own intermediates - not the
        # published *_reduction.tif, which can be a stale file left in place
        # because ArcGIS had it locked (see `publish`). Reading reduction and
        # the pre-track layers from two different runs would silently produce
        # a bite%/delta that belongs to neither.
        reduction_path = LAYERS / name / f"{REDUCTION_LAYER}.tif"
        pre_paths = [LAYERS / name / f"{layer}.tif" for layer in PRE_TRACK_LAYERS]
        if not reduction_path.exists() or not all(p.exists() for p in pre_paths):
            print(f"  {name}: no build yet - run `rasters` first.")
            continue
        tile = tiles[spec["tile"]]

        reduction = _read_float_layer(reduction_path)
        # cost right before tracks are subtracted: max(07_after_reductions,
        # 05_barriers), the same MAX surface.py runs just before the track
        # step - see PRE_TRACK_LAYERS.
        cost_pre = np.maximum(*(_read_float_layer(p) for p in pre_paths))
        cost_post = np.maximum(cost_pre - reduction, config.MIN_COST)
        int_pre = combine.clip_round(cost_pre, min_cost=config.MIN_COST, max_cost=config.MAX_COST)
        int_post = combine.clip_round(cost_post, min_cost=config.MIN_COST, max_cost=config.MAX_COST)

        density = read_tile("tracks", tile, fill=0.0)
        # Below min_density a cell counts as untracked ground, same as
        # normalize() - so "tracked" here means the same population the
        # reduction was actually computed over, not every pixel with any GPS
        # trace at all.
        min_density = float(config.TRACKS.get("min_density", 1.0))
        tracked = density >= min_density
        n = int(tracked.sum())
        if not n:
            print(f"  {name}: no cell reaches min_density={min_density:g} here.")
            continue
        forest = read_mask("forest", tile)
        delivered = reduction[tracked]
        changed = int_pre[tracked].astype(np.int32) - int_post[tracked].astype(np.int32)
        bit = changed > 0

        rows.append({
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "area": name,
            "tile": tile.tile_id,
            "tours": tour_counts.get(tile.tile_id, 0),
            "trk_pct": round(100 * n / density.size, 3),
            # The share of all track evidence that earns exactly nothing from
            # the curve itself, before rounding even enters it. At the
            # national scale this is the headline number: `lower` is a
            # percentile of positive pixels whose mode is 1, so a single
            # passage maps to zero and is discarded before anything else runs.
            "zero_pct": round(100 * float((delivered <= 0).sum()) / n, 1),
            "sat_pct": round(100 * float((density[tracked] >= scale[1]).sum()) / n, 1),
            "forest_pct": round(100 * float(forest[tracked].sum()) / n, 1),
            "mean_red": round(float(delivered.mean()), 4),
            "p95_red": round(float(np.percentile(delivered, 95)), 3),
            "max_red": round(float(delivered.max()), 3),
            # The real answer, not a threshold guess: share of tracked pixels
            # where the FINAL uint16 cost the router reads actually differs
            # with tracks on vs off - int_pre vs int_post, both run through
            # the same clip_round the build uses.
            "bite_pct": round(100 * float(bit.sum()) / n, 1),
            "bite_delta": round(float(changed[bit].mean()), 2) if bit.any() else 0.0,
            "settings": json.dumps({"TRACKS": config.TRACKS,
                                    "scale": [scale[0], scale[1]]},
                                   separators=(",", ":")),
        })

    if not rows:
        return rows

    header = (f"{'area':14s} {'tours':>5} {'trk%':>6} {'zero%':>6} {'sat%':>5} "
              f"{'forest%':>7} {'mean_red':>8} {'p95_red':>7} {'max_red':>7} "
              f"{'bite%':>6} {'delta':>5}")
    print(f"\n{header}\n{'-' * len(header)}")
    for row in rows:
        print(f"{row['area']:14s} {row['tours']:5d} {row['trk_pct']:6.2f} "
              f"{row['zero_pct']:6.1f} {row['sat_pct']:5.1f} "
              f"{row['forest_pct']:7.1f} {row['mean_red']:8.3f} "
              f"{row['p95_red']:7.3f} {row['max_red']:7.3f} {row['bite_pct']:6.1f} "
              f"{row['bite_delta']:5.2f}")
    print(f"\n  trk%     share of the tile at or above min_density "
          f"({config.TRACKS.get('min_density', 1.0):g})")
    print("  zero%    share of THAT which earns no reduction at all, before rounding")
    print("  sat%     share at or above the top of the scale")
    print("  bite%    share where the FINAL integer cost actually changed")
    print("  delta    mean size of that change, in cost units, where it happened")

    if config.TRACKS.get("curve") == "tile_bands":
        _report_bands()

    if append:
        _append_stats(rows)
        print(f"\n  appended to {STATS}")
    return rows


def _report_bands() -> None:
    """What each band's percentile resolves to, per tile, and what it covers.

    The tuning readout for curve="tile_bands". Density is a small integer with
    heavy ties, so a percentile lands on a tied value more often than not and
    the share a band actually covers is not the share its percentile suggests:
    ask for the top 50% of a tile where 70% of cells read exactly 1, and the
    threshold comes out at 1, so the band takes everything. Read `covers`, not
    the percentile, when deciding whether a band is doing what you meant.
    """
    from skimap import config, grid
    from skimap.data_preprocessing import tracks as track_scale
    from skimap.raster import read_tile

    tiles = {tile.tile_id: tile for tile in grid.iter_tiles()}
    print(f"\n  bands, per tile ({config.TRACKS['max_reduction']:g} cost units, "
          f"scaled by weight)")
    print(f"  {'area':14s} {'pct':>5} {'weight':>7} {'density>=':>10} {'covers':>8} "
          f"{'units off':>9}")
    for name, spec in areas().items():
        tile = tiles.get(spec["tile"])
        if tile is None:
            continue
        density = read_tile("tracks", tile, fill=0.0)
        rows = track_scale.band_thresholds(density)
        if not rows:
            print(f"  {name:14s}  no tracked cells")
            continue
        for pct, weight, threshold, share in rows:
            units_off = weight * float(config.TRACKS["max_reduction"])
            print(f"  {name:14s} {pct:5.0f} {weight:7.2f} {threshold:10.0f} "
                  f"{100 * share:7.1f}% {units_off:9.2f}")


def _append_stats(rows: list[dict]) -> None:
    """One row per area per run, forever.

    The rasters are overwritten in place, so without this there is no record
    that a setting was ever tried. The `settings` column carries the whole
    parameter set, which makes the file self-contained: every row says what
    produced it.
    """
    STATS.parent.mkdir(parents=True, exist_ok=True)
    fresh = not STATS.exists()
    with STATS.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        if fresh:
            writer.writeheader()
        writer.writerows(rows)


# --- routing -------------------------------------------------------------


def _tile_of(tour) -> Optional[str]:
    """The tile holding BOTH of a tour's endpoints, or None if they differ."""
    from skimap import config, grid

    origin_x, origin_y = config.GRID_ORIGIN
    ids = {grid.tile_id(grid._snap_down(x, origin_x), grid._snap_down(y, origin_y))
           for (x, y) in (tour.start, tour.end)}
    return ids.pop() if len(ids) == 1 else None


def _tours_by_tile() -> dict[str, int]:
    """How many tours each tile holds outright."""
    from skimap import tours as tours_mod

    counts: dict[str, int] = {}
    for tour in tours_mod.read_tours():
        tile_id = _tile_of(tour)
        if tile_id:
            counts[tile_id] = counts.get(tile_id, 0) + 1
    return counts


def scenario_tours() -> list:
    """Tours with BOTH endpoints inside one of the five tiles.

    Both, not either. A tour that starts in a scenario tile and finishes two
    tiles away is not a test of that tile's track data: most of its line is
    somewhere else, over whatever the neighbouring tiles happen to hold.
    """
    from skimap import tours as tours_mod

    wanted = {spec["tile"] for spec in areas().values()}
    found = [tour for tour in tours_mod.read_tours() if _tile_of(tour) in wanted]
    return sorted(found, key=lambda tour: tour.fid)


def save_run(name: str) -> Path:
    """Snapshot the routes just written, under a name that survives the next run.

    Copies ROUTES as-is into `runs/<name>/routes.gpkg`, beside a `note.json`
    naming the settings that produced it - the same TRACKS block
    settings_used.json carries, so a snapshot from last week still says what
    it was. Corridors are not copied; they are per-tour rasters and heavy,
    and the geometry in routes.gpkg is what `compare-runs` and a GIS both
    need for a route-shape comparison.

    Overwrites a snapshot of the same name without asking - a name is meant
    to be reused as you retune one setting, not accumulate a version per typo.
    """
    if not ROUTES.exists():
        raise SystemExit(f"No {ROUTES} to save - run `route` or `run` first.")
    out_dir = RUNS / name
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROUTES, out_dir / "routes.gpkg")
    note = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "note": read_settings().get("note", "") if SETTINGS.exists() else "",
        "TRACKS": _live_or_default_tracks(),
    }
    (out_dir / "note.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
    print(f"saved -> {out_dir}")
    return out_dir


def _live_or_default_tracks() -> dict:
    from skimap import config
    return dict(config.TRACKS)


def list_runs() -> list[str]:
    if not RUNS.exists():
        return []
    return sorted(p.name for p in RUNS.iterdir() if (p / "routes.gpkg").exists())


def compare_runs(names: list[str]) -> None:
    """Tour by tour, side by side: length, cost, and separation from production.

    Reads only `runs/<name>/routes.gpkg` snapshots - `route --save NAME`
    writes them, this never builds anything. With exactly two names, also
    computes the separation BETWEEN those two runs directly, which is the
    number "how different are these two settings" actually asks for; each
    run's `sep_max_m` on its own only ever answers "how different from
    production", which is a different question once you are comparing your
    own settings against each other rather than against the committed one.
    """
    import numpy as np
    from osgeo import ogr

    from skimap import routing

    ogr.UseExceptions()
    missing = [n for n in names if not (RUNS / n / "routes.gpkg").exists()]
    if missing:
        known = list_runs()
        raise SystemExit(
            f"No saved run {missing!r} in {RUNS}.\n"
            f"Known: {known or '(none yet - use route/run --save NAME)'}"
        )

    per_run: dict[str, dict[int, tuple]] = {}
    for name in names:
        ds = ogr.Open(str(RUNS / name / "routes.gpkg"))
        layer = ds.GetLayerByName(routing.ROUTES_LAYER)
        rows = {}
        for feat in layer:
            fid = feat.GetField("tour_fid")
            rows[fid] = (
                feat.GetGeometryRef().Clone(),
                feat.GetField("name") or f"tour_{fid}",
                float(feat.GetField("length_m") or 0.0),
                float(feat.GetField("cost_opt") or 0.0),
                feat.GetField("sep_max_m"),
            )
        ds = None
        per_run[name] = rows

    fids = sorted(set.union(*(set(r) for r in per_run.values())))
    if not fids:
        print("No tours in any of these runs.")
        return

    header = f"  {'fid':>5}  {'tour':22s}" + "".join(
        f" {n[:14]:>14}  km   cost  vs.prod" for n in names)
    print(f"\n{header}")
    for fid in fids:
        label = next((rows[fid][1] for rows in per_run.values() if fid in rows), f"tour_{fid}")
        line = f"  {fid:>5}  {label[:22]:22s}"
        for name in names:
            row = per_run[name].get(fid)
            if row is None:
                line += f" {'—':>14}  {'':>4}   {'':>5}  {'':>7}"
                continue
            _, _, length, cost, sep = row
            sep_txt = f"{sep:7.0f}" if sep is not None else f"{'n/a':>7}"
            line += f" {'':14} {length/1000:4.1f}  {cost:6.0f}  {sep_txt}"
        print(line)

    if len(names) == 2:
        a, b = names
        common = sorted(set(per_run[a]) & set(per_run[b]))
        if not common:
            print(f"\n{a!r} and {b!r} share no tours - nothing to compare directly.")
            return
        seps = []
        for fid in common:
            geom_a = per_run[a][fid][0]
            geom_b = per_run[b][fid][0]
            _, max_sep = routing.separation(geom_a, geom_b)
            seps.append((fid, per_run[a][fid][1], max_sep))
        arr = np.array([s[2] for s in seps])
        print(f"\n  {a!r} vs {b!r} directly, {len(common)} tours in common")
        print(f"  median {np.median(arr):.0f} m   p90 {np.percentile(arr, 90):.0f} m   "
              f"max {arr.max():.0f} m")
        print(f"\n  most different")
        print(f"  {'fid':>5}  {'tour':26s} {'sep':>7}")
        for fid, label, sep in sorted(seps, key=lambda s: -s[2])[:10]:
            print(f"  {fid:>5}  {label[:26]:26s} {sep:7.0f}")
    else:
        print(f"\n  Add multiple runs' routes.gpkg to the same map to compare shapes "
              f"visually - each is a complete, independent file under {RUNS}\\<name>\\. "
              f"Pairwise separation above is only computed for exactly two names.")


def route(*, jobs: int = 1, buffer_m: Optional[float] = None,
          save: Optional[str] = None):
    """Route the tours inside the five tiles, through the surface just built.

    The router does not read a tile, it reads a window: g.region is the
    start/end bounding box plus a buffer scaled to the tour's own length, and
    that window spills over a tile edge on most tours. So this builds the
    scenario tiles PLUS every tile those windows reach, and mosaics the lot.
    Build only the five and a route that leaves one is clipped at a nodata
    edge - which on the map looks exactly like terrain turning it back.

    Only the five are published as rasters. The neighbours exist to keep the
    router honest, and stay in _work/.

    `save` snapshots the result to `runs/<save>/` afterward - see save_run.
    """
    from skimap import lab, mosaic, routing
    from skimap.cost_surface.surface import build_all
    from skimap.data_preprocessing import tracks as track_scale

    _live()
    tours = scenario_tours()
    if not tours:
        raise SystemExit(
            "No tour has both endpoints inside any of the five tiles. Either "
            "the areas moved or tours.gpkg did - check "
            "'python -m skimap.track_scenarios areas'."
        )

    scenario_tiles = {spec["tile"] for spec in areas().values()}
    reachable, outside = lab.tiles_for(tours, buffer_m=buffer_m)
    extra = sorted(set(reachable) - scenario_tiles)
    print(f"{len(tours)} tours in {len(scenario_tiles)} scenario tiles; their "
          f"routing windows reach {len(extra)} more"
          + (f" ({len(outside)} of that window is outside the national grid)"
             if outside else ""))

    scale = scale_override() or track_scale.load_scale()
    if extra:
        # No debug on these - they are ground for the router to walk, not
        # something anyone opens. force=False, so a neighbour already built
        # under these settings is not rebuilt for the second tour reaching it.
        build_all(only=extra, force=False, jobs=jobs, tiles_root=TILES, scale=scale)

    mosaic.build_mosaic(out_path=VRT, tiles_root=TILES)
    print(f"routing {len(tours)} tours through {VRT}")
    results = routing.run_batch(
        tours, out_dir=ROOT, buffer_m=buffer_m,
        # force: the surface underneath changed, so every line already in
        # routes.gpkg is stale by construction. Resuming would mix routes
        # drawn through two different surfaces into one file.
        force=True, merge=True,
        # `tours` is a subset of tours.gpkg by construction, and to pruning
        # every tour left out of a subset looks exactly like a deleted one.
        # Nothing else writes here, so there is nothing to prune anyway.
        prune=False,
        surface=VRT, cost_raster=COST_RASTER,
    )
    compare()
    if save:
        save_run(save)
    return results


def compare() -> None:
    """How far each line sits from the production route for the same tour.

    Production already routed these tours through the committed surface, so it
    is the baseline and there is no baseline run to do. What the numbers mean
    is narrower than it looks: the difference is this run's track settings only
    while production's routes are current. If routes.gpkg is older than the
    national surface, some of the gap is drift rather than your change.
    """
    import numpy as np
    from osgeo import ogr

    from skimap import routing

    ogr.UseExceptions()
    if not ROUTES.exists():
        raise SystemExit(f"No routes at {ROUTES}. Run `route` first.")
    if not REFERENCE.exists():
        print(f"No production routes at {REFERENCE} - nothing to compare against.")
        return

    ref_ds = ogr.Open(str(REFERENCE))
    reference = {feat.GetField("tour_fid"): (feat.GetGeometryRef().Clone(),
                                             float(feat.GetField("length_m") or 0.0),
                                             float(feat.GetField("cost_opt") or 0.0))
                 for feat in ref_ds.GetLayerByName(routing.ROUTES_LAYER)}
    ref_ds = None

    fields = (("ref_len_m", ogr.OFTReal), ("len_diff_m", ogr.OFTReal),
              ("cost_diff", ogr.OFTReal), ("sep_mean_m", ogr.OFTReal),
              ("sep_max_m", ogr.OFTReal))
    ds = ogr.Open(str(ROUTES), 1)
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    have = {layer.GetLayerDefn().GetFieldDefn(i).GetName()
            for i in range(layer.GetLayerDefn().GetFieldCount())}
    for name, kind in fields:
        if name not in have:
            layer.CreateField(ogr.FieldDefn(name, kind))

    rows = []
    for feat in layer:
        fid = feat.GetField("tour_fid")
        if fid not in reference:
            continue
        ref_geom, ref_len, ref_cost = reference[fid]
        mean_sep, max_sep = routing.separation(feat.GetGeometryRef(), ref_geom)
        length = float(feat.GetField("length_m") or 0.0)
        cost = float(feat.GetField("cost_opt") or 0.0)
        feat.SetField("ref_len_m", round(ref_len, 1))
        feat.SetField("len_diff_m", round(length - ref_len, 1))
        feat.SetField("cost_diff", round(cost - ref_cost, 1))
        feat.SetField("sep_mean_m", round(mean_sep, 1))
        feat.SetField("sep_max_m", round(max_sep, 1))
        layer.SetFeature(feat)
        rows.append((fid, feat.GetField("name") or f"tour_{fid}",
                     length, ref_len, max_sep))
    ds = None

    if not rows:
        print("No tours in common with the production routes.")
        return

    seps = np.array([row[4] for row in rows])
    print(f"\nthese settings vs production, {len(rows)} tours\n")
    print(f"  worst separation   median {np.median(seps):7.0f} m   "
          f"p90 {np.percentile(seps, 90):7.0f} m   max {seps.max():7.0f} m")
    unmoved = int((seps < 10.0).sum())
    print(f"  unchanged on {unmoved}/{len(rows)} tours, moved on {len(rows) - unmoved}")
    print(f"\n  {'fid':>5}  {'tour':26s} {'this m':>9} {'prod m':>9} {'sep max':>8}")
    for row in sorted(rows, key=lambda row: -row[4])[:15]:
        print(f"  {row[0]:>5}  {row[1][:26]:26s} {row[2]:9.0f} {row[3]:9.0f} "
              f"{row[4]:8.0f}")
    print("\n  Symbolise routes.gpkg on sep_max_m to find them on the map.")


# --- cli -----------------------------------------------------------------


def _wrap(text: str, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def show_areas() -> None:
    print(f"\n{'area':14s} {'tile':22s} place")
    print("-" * 78)
    for name, spec in areas().items():
        print(f"{name:14s} {spec['tile']:22s} {spec.get('place', '')}")
        for line in _wrap(spec.get("why", ""), 58):
            print(f"{'':37s}{line}")
    print(f"\nPublished into {ROOT}")
    print("  as <area>_cost.tif and <area>_reduction.tif")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skimap.track_scenarios",
        description="Five tiles, ten fixed rasters, one settings file.",
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("init", help="write settings.json")
    p.add_argument("--force", action="store_true", help="overwrite an edited one")

    sub.add_parser("areas", help="the five tiles, and why each is in the set")

    p = sub.add_parser("rasters", help="build and publish the ten rasters")
    p.add_argument("--jobs", type=int, default=1, help="parallel worker processes")

    p = sub.add_parser("route", help="route the tours inside those tiles")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--buffer", type=float, help="region buffer ceiling in m")
    p.add_argument("--save", metavar="NAME",
                   help="also snapshot routes.gpkg to runs/NAME/, so it "
                        "survives the next run - see compare-runs")

    p = sub.add_parser("run", help="rasters, then route")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--buffer", type=float)
    p.add_argument("--save", metavar="NAME")

    sub.add_parser("stats", help="re-read the published rasters and report")
    sub.add_parser("publish", help="move what _work/ still holds onto its names")
    sub.add_parser("runs", help="list saved route snapshots")

    p = sub.add_parser("compare-runs",
                       help="tour by tour, saved runs side by side")
    p.add_argument("names", nargs="+", help="names given to route/run --save")

    args = parser.parse_args(argv)

    if args.stage == "init":
        init(force=args.force)
        return 0

    # Everything past here reads a parameter, so the overlay has to be in the
    # environment before the first import of config - which is what any of
    # these stage functions does on its first line.
    if not SETTINGS.exists():
        print(f"No {SETTINGS} yet - writing the defaults.")
        init()
    os.environ["SKIMAP_PROFILE"] = str(SETTINGS.resolve())

    if args.stage == "areas":
        show_areas()
        return 0

    if args.stage == "publish":
        return publish()

    if args.stage == "stats":
        stats()
        return 0

    if args.stage == "runs":
        found = list_runs()
        print("\n".join(found) if found else
              f"No saved runs in {RUNS} yet - use route/run --save NAME.")
        return 0

    if args.stage == "compare-runs":
        compare_runs(args.names)
        return 0

    jobs = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)

    if args.stage in ("rasters", "run"):
        failed = build_rasters(jobs=jobs)
        stats()
        if args.stage == "rasters":
            return 1 if failed else 0
        if failed:
            print(f"\n{len(failed)} tile(s) failed; not routing through a "
                  f"surface with holes in it.")
            return 1

    results = route(jobs=jobs, buffer_m=args.buffer, save=args.save)
    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
