"""Is the cost surface georeferenced where its data actually is?

This exists because it was not, and nothing caught it. The tiles were written
at their polygon corner while `window()` reads cells from the raster lattice
half a pixel away, so every value in the national surface sat 5 m east and
5 m south of the terrain it described.

That class of bug is invisible in all the obvious checks. The arrays are
right, so statistics, histograms, invariants and tile-to-tile seams all pass.
It only shows when the surface is laid against something else - a barrier
beside its own coastline, r.walk pairing elevation with a neighbour's
friction - by which time it has been published.

So the checks here all work through COORDINATES rather than array indices.
Comparing arrays index for index agrees perfectly even when the
georeferencing is wrong, which is exactly why the bug survived.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
from osgeo import gdal

from skimap import config, paths
from skimap.grid import Tile, iter_tiles
from skimap.raster import tile_origin, window

gdal.UseExceptions()

# Offsets to test, in metres. Half a pixel either way is the failure mode
# that matters; a whole pixel catches an off-by-one in the window maths.
PROBE_OFFSETS = (-10.0, -5.0, 0.0, 5.0, 10.0)


def check_tile_origins(tiles: Optional[Sequence[str]] = None) -> bool:
    """Does tile_origin() match the cells window() reads, for every layer?

    Every national layer has a different extent, so they only agree if the
    lattice maths is right rather than accidentally right for one of them.
    """
    names = [n for n in config.COST_LAYERS if _has(n)]
    sample = list(iter_tiles(only=tiles)) if tiles else _spread()

    ok = True
    for tile in sample:
        want = tile_origin(tile)
        for name in names:
            ds = gdal.Open(str(paths.layer(name)))
            gt = ds.GetGeoTransform()
            px, py = window(ds, tile)
            ds = None
            got = (gt[0] + px * config.PIXEL_SIZE, gt[3] + py * gt[5])
            if abs(got[0] - want[0]) > 1e-6 or abs(got[1] - want[1]) > 1e-6:
                print(f"  {tile.tile_id} {name}: reads ({got[0]:.1f}, {got[1]:.1f}) "
                      f"but tile_origin says ({want[0]:.1f}, {want[1]:.1f})")
                ok = False
    print(f"  tile_origin agrees with {len(names)} layers over {len(sample)} tiles: "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


def check_surface_lattice() -> bool:
    """Is the written surface on the same lattice as the layers it came from?"""
    ok = True
    ref = (config.RASTER_ORIGIN[0] % config.PIXEL_SIZE,
           config.RASTER_ORIGIN[1] % config.PIXEL_SIZE)

    targets = [("cost surface", paths.COST_SURFACE / "cost_surface.tif"),
               ("cost mosaic", paths.COST_SURFACE / "cost_surface.vrt")]
    targets += [(f"layer {n}", paths.layer(n)) for n in config.COST_LAYERS if _has(n)]
    targets += [("DEM", paths.source("dem"))]

    for label, path in targets:
        if not path.exists():
            continue
        ds = gdal.Open(str(path))
        gt = ds.GetGeoTransform()
        ds = None
        got = (gt[0] % config.PIXEL_SIZE, gt[3] % config.PIXEL_SIZE)
        good = abs(got[0] - ref[0]) < 1e-6 and abs(got[1] - ref[1]) < 1e-6
        ok &= good
        if not good:
            print(f"  {label:22s} lattice offset {got}, expected {ref}")
    print(f"  every layer and the surface share config.RASTER_ORIGIN's lattice: "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


def check_surface_current() -> bool:
    """Is the published COG newer than every tile it was built from?

    A stale COG beside fresh tiles is worse than a missing one: it opens, it
    looks right, and it is the raster everything downstream prefers. This
    catches the case where the tiles were rebuilt but the mosaic step failed
    - easy to miss, because that failure comes at the end of a long run.
    """
    import datetime as dt

    cog = paths.COST_SURFACE / "cost_surface.tif"
    if not cog.exists():
        print("  no COG built - nothing to be stale")
        return True

    tiles = list(paths.TILES.glob("*/cost_surface.tif"))
    if not tiles:
        print("  no tiles to compare against")
        return True

    newest = max(t.stat().st_mtime for t in tiles)
    if cog.stat().st_mtime < newest:
        fmt = "%Y-%m-%d %H:%M"
        print(f"  COG   {dt.datetime.fromtimestamp(cog.stat().st_mtime):{fmt}}")
        print(f"  tiles {dt.datetime.fromtimestamp(newest):{fmt}}  <- newer")
        print("  the COG predates its own tiles; rerun 'skimap.cli mosaic --cog'")
        return False
    print("  COG is newer than every tile it came from: PASS")
    return True


def measure_shift(tiles: Optional[Sequence[str]] = None,
                  source: Optional[str] = None) -> bool:
    """Find the offset at which the surface best matches the ocean mask.

    Ocean is the probe because it is the only thing reaching BARRIER_COST
    exactly - the steep-slope barrier stops at 1500 - so `cost == 5000` reads
    back the ocean mask as the surface recorded it. Sampling both by
    coordinate, the best offset is the error the surface carries. It should
    be (0, 0).
    """
    if source:
        surface = paths.COST_SURFACE / source
    else:
        surface = paths.COST_SURFACE / "cost_surface.tif"
        if not surface.exists():
            surface = paths.COST_SURFACE / "cost_surface.vrt"
    if not surface.exists():
        print("  no national surface built yet - skipped")
        return True
    print(f"  probing {surface.name}")

    cost_ds = gdal.Open(str(surface))
    cgt = cost_ds.GetGeoTransform()
    cband = cost_ds.GetRasterBand(1)
    ocean_ds = gdal.Open(str(paths.derived("ocean")))
    ogt = ocean_ds.GetGeoTransform()
    oband = ocean_ds.GetRasterBand(1)

    ok = True
    checked = 0
    for tile in (list(iter_tiles(only=tiles)) if tiles else _coastal()):
        n = 1200
        cx = int((tile.x0 + 4000 - cgt[0]) / cgt[1])
        cy = int((cgt[3] - (tile.y0 + config.TILE_SIZE - 4000)) / -cgt[5])
        if cx < 0 or cy < 0 or cx + n > cost_ds.RasterXSize or cy + n > cost_ds.RasterYSize:
            continue
        barrier = cband.ReadAsArray(cx, cy, n, n) == config.BARRIER_COST
        if barrier.sum() < 5000:
            continue
        checked += 1

        xs = cgt[0] + (cx + np.arange(n) + 0.5) * cgt[1]
        ys = cgt[3] + (cy + np.arange(n) + 0.5) * cgt[5]

        scores = {}
        for dx in PROBE_OFFSETS:
            for dy in PROBE_OFFSETS:
                px = np.clip((((xs + dx) - ogt[0]) / ogt[1]).astype(int),
                             0, ocean_ds.RasterXSize - 1)
                py = np.clip((((ys + dy) - ogt[3]) / ogt[5]).astype(int),
                             0, ocean_ds.RasterYSize - 1)
                sub = oband.ReadAsArray(int(px.min()), int(py.min()),
                                        int(px.max() - px.min()) + 1,
                                        int(py.max() - py.min()) + 1)
                src = sub[np.ix_(py - py.min(), px - px.min())] > 0
                scores[(dx, dy)] = int((src != barrier).sum())

        at_zero = scores[(0.0, 0.0)]
        best_off, best = min(scores.items(), key=lambda kv: kv[1])
        # A correctly placed surface is best at (0, 0), or within noise of it.
        good = at_zero <= best * 1.5 + 200
        ok &= good
        print(f"  {tile.tile_id:24s} at (0,0): {at_zero:>7,} px  "
              f"best {best:>7,} at ({best_off[0]:+.0f}, {best_off[1]:+.0f}) m  "
              f"{'ok' if good else 'SHIFTED'}")

    cost_ds = ocean_ds = None
    if checked == 0:
        print("  no coastal tiles with enough barrier to probe - skipped")
        return True
    print(f"  surface sits where its data does, over {checked} coastal tiles: "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


def check_tiles_tessellate() -> bool:
    """Adjacent tiles must abut exactly - no gap, no overlap."""
    a = next(iter_tiles(only=["tile_64500_6919500"]))
    right = next(iter_tiles(only=["tile_84500_6919500"]))
    below = next(iter_tiles(only=["tile_64500_6899500"]))

    ax, ay = tile_origin(a)
    span = config.TILE_SIZE
    gap_x = tile_origin(right)[0] - (ax + span)
    gap_y = ay - span - tile_origin(below)[1]
    ok = abs(gap_x) < 1e-6 and abs(gap_y) < 1e-6
    print(f"  neighbour gap: {gap_x:+.3f} m across, {gap_y:+.3f} m down  "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


def _has(name: str) -> bool:
    try:
        return paths.layer(name).exists()
    except FileNotFoundError:
        return False


def _spread() -> list[Tile]:
    """A handful of tiles from the corners and middle of the country."""
    tiles = list(iter_tiles())
    idx = [0, len(tiles) // 4, len(tiles) // 2, 3 * len(tiles) // 4, len(tiles) - 1]
    return [tiles[i] for i in idx]


def _coastal() -> list[Tile]:
    """Tiles known to hold a useful amount of sea."""
    wanted = ["tile_624500_7719500", "tile_464500_7559500", "tile_684500_7719500",
              "tile_64500_6919500"]
    have = {t.tile_id for t in iter_tiles()}
    return list(iter_tiles(only=[w for w in wanted if w in have]))


def run(tiles: Optional[Sequence[str]] = None, source: Optional[str] = None) -> bool:
    print("1. tile_origin() vs the cells window() reads")
    a = check_tile_origins(tiles)
    print("\n2. everything on one lattice")
    b = check_surface_lattice()
    print("\n3. tiles tessellate")
    c = check_tiles_tessellate()
    print("\n4. the published COG is not stale")
    e = check_surface_current()
    print("\n5. measured shift against the ocean mask")
    d = measure_shift(tiles, source)

    ok = a and b and c and d and e
    print(f"\n{'=' * 60}")
    print("ALIGNMENT OK" if ok else "ALIGNMENT FAILED - the surface is not where it says it is")
    return ok
