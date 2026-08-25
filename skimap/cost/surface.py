"""Build one tile's cost surface by reading windows from the national layers.

Order matters:
  1. weighted sum of the terrain layers (slope, windshelter, pra_runout)
  2. MAX in the barriers (ocean, steep slope, plus anything enabled in
     config.BARRIERS)
  3. MIN in the reductions (road, tractor trail in forest, bridge), gated
     so they only apply where the terrain is safe enough to walk anyway
  4. MAX the barriers back in, so no reduction can undo a cliff or the sea
  5. subtract track influence, floored at MIN_COST

Step 4 covers every barrier, not just the steep slope. The reduction gate
opens on gentle, low avalanche ground, and open water is exactly that -
slope 0, no release area - so without it every coastal road pixel that
all_touched bleeds into a Havflate polygon becomes a cost-2 hole in the
middle of a fjord.

Tracks come last and are deliberately left able to dent a barrier: the
reduction is capped at a few cost units, so a barrier of 5000 or a cliff of
1500 stays a barrier either way.

Nothing is materialized per tile except the result.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from skimap import config, paths
from skimap.cost import combine, transforms
from skimap.data_preprocessing import tracks as track_scale
from skimap.grid import Tile, iter_tiles
from skimap.raster import read_mask, read_tile, write_tile

# What 'cost --debug' writes alongside the surface, in build order. Each is
# Float32 in the same cost units as the output, so they can be compared to
# it and to each other directly.
DEBUG_LAYERS = (
    "01_slope_cost",            # slope degrees -> cost, via the threshold jump
    "02_windshelter_cost",      # shelter index -> cost, via the logistic
    "03_pra_runout_cost",       # avalanche exposure, already in cost units
    "04_terrain_weighted_sum",  # the three above, weighted and normalized
    "05_barriers",              # steep slope and whatever config.BARRIERS enables
    "06_reduction_gate",        # 0..1: how much of a road reduction may apply
    "07_after_reductions",      # cost once roads, forest trails and bridges are in
    "08_track_reduction",       # cost units the GPS tracks took off
    "09_cost_surface",          # the result, copied in so one folder holds it all
)


def build_cost_surface(
    tile: Tile,
    *,
    force: bool = False,
    scale: Optional[tuple[float, float]] = None,
    debug: bool = False,
    label: Optional[str] = None,
) -> Path:
    """Write cost_surface.tif for one tile. uint16, COST_NODATA outside.

    With `debug`, also writes the DEBUG_LAYERS into data/debug/<label>/ -
    the components that went into the result, so a surprising cost can be
    traced back to the layer that caused it. `label` names that folder and
    defaults to the tile id; pass a study area name to get something you can
    find again. Debug always recomputes, since the point is the
    intermediates and an existing surface says nothing about them.
    """
    label = label or tile.tile_id
    out_path = paths.cost_surface(tile.tile_id)
    if out_path.exists() and not force and not debug:
        return out_path
    if scale is None:
        scale = track_scale.load_scale()

    # Slope decides where the tile has ground at all: it comes from the DEM,
    # so its nodata is the country's outline plus whatever the DEM misses.
    # Every other layer is read with a neutral fill.
    slope = read_tile("slope", tile)
    valid = np.isfinite(slope)
    slope = np.nan_to_num(slope, nan=0.0)

    def dbg(name: str, array: np.ndarray) -> None:
        """Write one component, masked to the same ground as the output."""
        if not debug:
            return
        write_tile(
            np.where(valid, array, config.NODATA).astype(np.float32),
            tile, paths.debug_layer(label, name),
            dtype="Float32", nodata=config.NODATA,
        )

    # Windshelter has nodata holes all over the country, not just at the
    # edge of its extent - 637 land tiles carry at least one, some are two
    # thirds hole. Fill them at x0, the logistic midpoint, which is also
    # very close to the national median of the index: a gap then reads as
    # "average shelter", which is the honest answer where there is no data.
    #
    # The tempting alternative - drop windshelter there and renormalize the
    # other two weights - is NOT neutral. Windshelter's cost band is 5..30,
    # so it contributes a real positive offset even on easy ground, while
    # slope and pra_runout both bottom out near MIN_COST. Removing it and
    # scaling the rest by 1/0.88 leaves easy ground at 1.6 against 3.5 for
    # its neighbours: measured on land, every hole came out at cost 2 where
    # comparable ground outside read 4. That is a router that prefers to
    # travel through missing data.
    windshelter = read_tile("windshelter", tile, fill=config.WINDSHELTER["x0"])
    pra_runout = read_tile("pra_runout", tile, fill=config.MIN_COST)

    # --- 1. terrain -----------------------------------------------------
    # pra_runout arrives already in cost units - data_preprocessing.derived
    # built it that way. Slope and windshelter still go through a curve.
    terrain = {
        "slope": transforms.slope_cost(slope),
        "windshelter": transforms.windshelter_cost(windshelter),
        "pra_runout": pra_runout,
    }
    dbg("01_slope_cost", terrain["slope"])
    dbg("02_windshelter_cost", terrain["windshelter"])
    dbg("03_pra_runout_cost", terrain["pra_runout"])

    cost = combine.weighted_sum(terrain, config.WEIGHTS)
    cost = np.clip(cost, config.MIN_COST, config.BASE_MAX_COST)
    dbg("04_terrain_weighted_sum", cost)

    # --- 2. barriers ----------------------------------------------------
    barriers = [combine.steep_slope_barrier(slope, **config.STEEP_SLOPE_BARRIER)]
    for name, enabled in config.BARRIERS.items():
        if enabled:
            barriers.append(
                combine.barrier_from_mask(
                    read_mask(name, tile),
                    barrier_value=config.BARRIER_COST,
                    min_cost=config.MIN_COST,
                )
            )
    barrier = combine.max_combine(*barriers)
    cost = combine.max_combine(cost, barrier)
    dbg("05_barriers", barrier)

    # --- 3. reductions --------------------------------------------------
    # A road is only worth following where you could walk anyway. Both gates
    # have to open, so a road cut into a 35 degree slope or run through a
    # runout zone keeps the terrain's cost.
    g = config.REDUCTION_GATE
    gate = combine.gate_below(slope, threshold=g["slope_threshold"], width=g["slope_width"]) * \
           combine.gate_below(pra_runout, threshold=g["pra_runout_threshold"], width=g["pra_runout_width"])
    dbg("06_reduction_gate", gate)

    for name in ("road", "tractorroad_trail_forest", "bridge"):
        mask = read_mask(name, tile)
        if not mask.any():
            continue
        cost = combine.min_combine(
            cost,
            combine.reduction_from_mask(
                mask, gate, low_value=config.ROAD_TRAIL_COST, elsewhere=cost
            ),
        )

    dbg("07_after_reductions", cost)

    # --- 4. barriers win ------------------------------------------------
    cost = combine.max_combine(cost, barrier)

    # --- 5. tracks ------------------------------------------------------
    # A fixed number of cost units off, not a factor: a well-used route
    # should make flat ground marginally cheaper, not make a 40 degree
    # slope look like a road.
    t = config.TRACKS
    unit = track_scale.normalize(read_tile("tracks", tile, fill=0.0), scale) ** t["power"]
    max_reduction = np.where(
        read_mask("forest", tile), t["max_reduction_forest"], t["max_reduction_outside"]
    ).astype(np.float32)
    reduction = max_reduction * unit
    dbg("08_track_reduction", reduction)
    cost = np.maximum(cost - reduction, config.MIN_COST)

    out = combine.clip_round(cost, min_cost=config.MIN_COST, max_cost=config.MAX_COST)
    out[~valid] = config.COST_NODATA
    if debug:
        # The result itself, beside its components - uint16 like the real
        # output, not the Float32 the others use, so it is the same numbers
        # the router will read rather than a lookalike.
        write_tile(out, tile, paths.debug_layer(label, "09_cost_surface"),
                   dtype="UInt16", nodata=config.COST_NODATA)
    return write_tile(out, tile, out_path, dtype="UInt16", nodata=config.COST_NODATA)


# --- driver ------------------------------------------------------------


def _build_one(args) -> tuple[str, Optional[str]]:
    """Worker body. Returns (tile_id, error) rather than raising - one bad
    tile must not take the whole run down 1300 tiles in."""
    tile, force, scale, debug, label = args
    try:
        build_cost_surface(tile, force=force, scale=scale, debug=debug, label=label)
        return label or tile.tile_id, None
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        return tile.tile_id, f"{type(exc).__name__}: {exc}"


def build_all(
    *,
    only: Optional[Sequence[str]] = None,
    force: bool = False,
    jobs: int = 1,
    debug: bool = False,
    labels: Optional[dict[str, str]] = None,
) -> list[str]:
    """Build every tile's cost surface. Resumable: tiles that already have an
    output are skipped unless `force`. Returns the ids that failed.

    `debug` also writes DEBUG_LAYERS per tile and rebuilds regardless, since
    an existing surface says nothing about whether its components are on
    disk. It multiplies the output size by roughly eight, so it is meant for
    the handful of tiles named with --tile or --area, not for the country.

    `labels` maps tile id -> folder name for the debug output, so a study
    area lands in data/debug/<area>/ instead of under its coordinates.
    """
    scale = track_scale.load_scale()
    tiles = list(iter_tiles(only=only))

    todo = tiles if (force or debug) else [
        t for t in tiles if not paths.cost_surface(t.tile_id).exists()
    ]
    print(f"{len(tiles)} tiles, {len(tiles) - len(todo)} already built, "
          f"{len(todo)} to do  (jobs={jobs})")
    if debug:
        print(f"debug: also writing {len(DEBUG_LAYERS)} component layers per tile")
        if only is None:
            print("  WARNING: debug over the whole grid. That is ~8x the output "
                  "size; --tile <id> is usually what you want.")
    if not todo:
        return []

    labels = labels or {}
    work = [(t, force, scale, debug, labels.get(t.tile_id)) for t in todo]
    failed: list[str] = []
    started = time.time()

    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            _report(pool.map(_build_one, work, chunksize=1), len(todo), started, failed)
    else:
        _report((_build_one(w) for w in work), len(todo), started, failed)

    if failed:
        print(f"\n{len(failed)} tiles failed: {', '.join(failed[:10])}"
              + (" ..." if len(failed) > 10 else ""))
    return failed


def _report(results, total: int, started: float, failed: list[str]) -> None:
    for i, (tile_id, error) in enumerate(results, 1):
        if error:
            failed.append(tile_id)
            print(f"[{i}/{total}] {tile_id}  FAILED  {error}", flush=True)
            continue
        elapsed = time.time() - started
        print(f"[{i}/{total}] {tile_id}  {elapsed / i:.1f}s/tile  "
              f"eta {elapsed / i * (total - i) / 60:.0f}m", flush=True)
