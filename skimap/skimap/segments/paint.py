"""Turning the drawing into one raster per class.

Two questions get answered separately for every cell, and keeping them apart
is the point of this module:

    how far into a corridor is it   -> the MAX membership over the tours
                                       covering it, which is what
                                       routing.merge_corridors means by a
                                       merge
    which class is it               -> a vote among those tours, most
                                       dangerous winning

Answering both with one comparison is a bug, not a shortcut. Take the more
dangerous tour's colour AND its membership and a cell at the faint outer
fringe of one corridor (1e-6) outranks the core of another (0.95), then
drags 1e-6 in as the value - which any sane opacity ramp draws as nothing.
The symptom is holes punched through strong corridors, and it is invisible
in the numbers because the cell is still "painted".

The vote is restricted to tours with a real claim on the cell for the same
reason: a corridor's outermost fringe should not repaint the core of one
that actually goes there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from scipy.ndimage import binary_fill_holes, distance_transform_edt, label

from skimap import config, exposure, paths
from skimap.segments import aoi, drawn
from skimap.segments.aoi import Window
from skimap.segments.drawn import CLASS_NAMES, SEVERITY, Drawn
from skimap.segments.routes import Route


def corridors_in(window: Window, corridor_dir: Optional[Path] = None,
                 clip: Optional[np.ndarray] = None) -> dict[int, Path]:
    """tour_fid -> corridor, for corridors with cells actually inside the window.

    Extent overlap is not enough. A corridor whose bounding box clips a
    corner of the window may have no cells in it at all - two did, on the
    first area this was run on - and including them puts routes in the
    report that contribute nothing.
    """
    corridor_dir = Path(corridor_dir) if corridor_dir else (paths.ROUTES / "corridors")
    if not corridor_dir.is_dir():
        raise FileNotFoundError(f"No corridors at {corridor_dir}")
    found: dict[int, Path] = {}
    for fid, path in exposure.corridors_by_fid(corridor_dir).items():
        if not aoi.overlaps(window, path):
            continue
        arr = aoi.read(window, path)
        if clip is not None:
            arr = arr * clip
        if (arr > 0).any():
            found[fid] = path
    return found


def fill_holes(corridor: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Close enclosed gaps in a corridor. Returns (filled, cells done, cells left).

    The router excludes patches mid-band that cost more than its slack
    allows - a cliff, a glacier, or merely a detour a little too expensive -
    and those read as damage on a map rather than as the judgement they are.

    Only ENCLOSED holes, so filling can never push a corridor outward, and
    only up to max_hole_cells, so a genuinely impassable massif still shows
    as excluded. Filled cells take the nearest real membership, which keeps
    the ramp coherent across the patch instead of stepping to a flat number.
    """
    if not config.SEGMENTS["fill_holes"]:
        return corridor, 0, 0
    inside = corridor > 0
    holes = binary_fill_holes(inside) & ~inside
    if not holes.any():
        return corridor, 0, 0

    cap = int(config.SEGMENTS["max_hole_cells"])
    tags, _ = label(holes)
    sizes = np.bincount(tags.ravel())
    small = np.isin(tags, np.flatnonzero((sizes > 0) & (sizes <= cap))) & holes
    left = int(holes.sum() - small.sum())
    if not small.any():
        return corridor, 0, left

    out = corridor.copy()
    _, (iy, ix) = distance_transform_edt(~inside, return_indices=True)
    out[small] = out[iy[small], ix[small]]
    return out, int(small.sum()), left


def paint(window: Window, routes: dict[int, Route], features: list[Drawn],
          corridors: dict[int, Path], *, clip: Optional[np.ndarray] = None,
          report: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """(severity per cell, membership per cell). Severity is -1 off the corridors."""
    plans = {}
    for fid in corridors:
        plans[fid], notes = drawn.timeline(fid, features, routes)
        if report:
            route = routes[fid]
            print(f"\n  tour {fid}  ({route.length_m:.0f} m)"
                  + (f"  {route.name}" if route.name else ""))
            for s0, s1, colour in plans[fid]:
                bar = "#" * max(1, int((s1 - s0) / max(route.length_m, 1e-9) * 42))
                print(f"    {s0:>6.0f} - {s1:>6.0f}  {colour:<6} {bar}")
            for note in notes:
                print(f"    {note}")

    cx, cy = window.centres()
    sevs, vals = [], []
    filled_total = left_total = 0
    if report:
        print()
    for fid, path in corridors.items():
        corridor = aoi.read(window, path)
        if clip is not None:
            corridor = corridor * clip
        corridor, filled, left = fill_holes(corridor)
        filled_total += filled
        left_total += left

        here = corridor > 0
        if not here.any():
            continue
        station = np.full(window.shape, np.nan)
        station[here] = routes[fid].station_of(
            np.column_stack([cx[here], cy[here]]))[0]

        sev = np.full(window.shape, -1, dtype=np.int8)
        for s0, s1, colour in plans[fid]:
            sev[here & (station >= s0) & (station <= s1)] = SEVERITY[colour]
        sevs.append(sev)
        vals.append(corridor)
        if report:
            note = f", {filled} hole cells filled" if filled else ""
            print(f"  tour {fid}: {int(here.sum()):>7d} cells{note}")

    if not sevs:
        empty = np.full(window.shape, -1, dtype=np.int8)
        return empty, np.zeros(window.shape, dtype=np.float32)
    if report and left_total:
        print(f"  {left_total} hole cells left unfilled (larger than "
              f"{config.SEGMENTS['max_hole_cells']} cells)")

    S, V = np.stack(sevs), np.stack(vals)
    membership = V.max(axis=0)
    # No floor under the denominator. Corridor values are (1 - gap/max_gap)^gamma,
    # so cells at the outer edge are legitimately tiny; clamping it made them
    # fail their own vote and vanish from every output. V <= membership always,
    # so the owning tour always votes.
    fraction = float(config.SEGMENTS["claim_fraction"])
    votes = (V > 0) & (V >= fraction * membership)
    severity = np.where(votes, S, -1).max(axis=0).astype(np.int8)

    if report:
        contested = (V > 0).sum(axis=0) >= 2
        muted = contested & ((V > 0).sum(axis=0) > votes.sum(axis=0))
        if contested.any():
            print(f"  {int(contested.sum())} cells lie under 2+ corridors; on "
                  f"{int(muted.sum())} a tour's claim was below {fraction:.0%} of the "
                  f"best and did not vote on colour")

    # Stencils last: a polygon wins over whatever the lines decided, on any
    # corridor beneath it, so the line under one need not be deleted.
    for d in features:
        if d.kind != "poly":
            continue
        mask = aoi.burn(window, d.geometry) & (severity >= 0)
        if d.tour_fid in corridors:
            mask &= aoi.read(window, corridors[d.tour_fid]) > 0
        severity[mask] = SEVERITY[d.colour]
        if report:
            print(f"  poly {d.fid}: {d.colour:<6} painted over {int(mask.sum()):>6d} "
                  f"corridor cells")

    return severity, membership


def write(window: Window, severity: np.ndarray, membership: np.ndarray,
          out_dir: Path, *, report: bool = True) -> dict[str, Path]:
    """One raster per class. Disjoint: every cell appears in exactly one."""
    out_dir = Path(out_dir)
    written: dict[str, Path] = {}
    blocked: list[str] = []
    for colour in CLASS_NAMES:
        arr = np.where(severity == SEVERITY[colour], membership, 0.0)
        path = out_dir / f"corridors_{colour}.tif"
        cells = int((arr > 0).sum())
        if cells == 0:
            if path.exists():
                path.unlink()          # else a stale file from a previous run lingers
            if report:
                print(f"  {colour:<6} no cells - not written")
            continue
        landed, ok = aoi.write(window, arr, path)
        written[colour] = landed
        if not ok:
            blocked.append(colour)
        if report:
            note = (f"  -> {landed.name}" if ok else
                    f"  -> LOCKED, left as {landed.name}; {path.name} is untouched")
            print(f"  {colour:<6} {cells:>7d} cells{note}")
    if blocked and report:
        print(f"\n  {len(blocked)} raster(s) could not be replaced - close them in "
              f"ArcGIS and run split again.")
    return written
