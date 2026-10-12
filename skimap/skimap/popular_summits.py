"""Rank Norway's mountain tops by how much recorded ski touring reaches them.

Approximate on purpose - a list to check by eye, not a measurement.

A summit is a DEM cell that is the highest within PEAK_RADIUS_M and stands
at least MIN_DROP_M above the mean of a ring around it, so the top of a
slope or a bump on a plateau does not count.

Its score is the traffic into its summit area: the ground connected to the
top that lies within ZONE_DROP_M below it and ZONE_RADIUS_M of it. The track
density on the one-cell boundary of that area is summed and halved, since a
trip crosses it once going up and once coming down. Counting at the area's
edge rather than at the top itself matters on mountains like Gaustatoppen,
where most tracks stop at a hut or ski depot just below the true top: those
trips still crossed into the summit area, while a fixed ring RING_RADIUS_M
around the top only sees the few who carried on.

The summit area alone is fooled by a busy track that runs along a flank
inside it without heading for the top - a crossing of Sognefjellet scored
4667 that way with one passage near the top. From the raster that looks
like Gausta; what tells them apart is whether any of the traffic goes on
to the top. So `est_visits` is `area_visits` capped at REACH_FACTOR times
`ring_visits`: the area count, believed only as far as the top is reached.
Gausta gets most of its area count back, the flank crossing almost none.

A top whose summit area holds higher ground is a sub-top of that higher
one and is dropped, so a ridge of tops counts as one mountain and the
summit areas of the tops that remain never overlap.

Known ways it is off: laps, and tracks running along the boundary, count
more than once; a track that only skirts the summit area also counts.

    python -m skimap.popular_summits
    python -m skimap.popular_summits --top 1000

Writes data/popular_summits/popular_summits.gpkg (layer `top`, ranked, and
layer `all`, every scored summit) and popular_summits.csv beside it.
"""

from __future__ import annotations

import argparse
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from osgeo import gdal
from scipy import ndimage

from skimap import config, paths

gdal.UseExceptions()

OUT_DIR = paths.DATA / "popular_summits"
OUT_GPKG = OUT_DIR / "popular_summits.gpkg"
OUT_CSV = OUT_DIR / "popular_summits.csv"

PEAK_RADIUS_M = 300.0   # highest point within this (square) radius
DROP_RADIUS_M = 300.0   # ring the summit has to stand above ...
MIN_DROP_M = 40.0       # ... by at least this much on average
ZONE_DROP_M = 100.0     # summit area: ground within this much below the top ...
ZONE_RADIUS_M = 800.0   # ... and this far from it
RING_RADIUS_M = 150.0   # ring around the top proving the traffic reaches it
REACH_FACTOR = 10.0     # area visits believed up to this many times the ring's
MIN_SCORE = 5.0         # fewer estimated visits than this is not written
BLOCK = 4096            # cells per side of one processing block

EIGHT = np.ones((3, 3), dtype=bool)


def _ring(radius_cells: float) -> tuple[np.ndarray, np.ndarray]:
    """Offsets of a closed, one-cell-wide ring: no track can step across it
    diagonally without touching one of its cells."""
    r = int(np.ceil(radius_cells)) + 1
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    d = np.hypot(dy, dx)
    inside = d < radius_cells
    # The cells just outside the disk that border it 4-connected.
    edge = ~inside & (np.roll(inside, 1, 0) | np.roll(inside, -1, 0)
                      | np.roll(inside, 1, 1) | np.roll(inside, -1, 1))
    return dy[edge], dx[edge]


def _windows(n: int, pad: int):
    """(read_start, read_size, core_start_in_read, core_size) along one axis."""
    for core0 in range(0, n, BLOCK):
        core = min(BLOCK, n - core0)
        r0 = max(0, core0 - pad)
        r1 = min(n, core0 + core + pad)
        yield r0, r1 - r0, core0 - r0, core


def _summit_area_visits(dem, tracks, r, c, z, zone_r, disk) -> float | None:
    """Half the track density on the boundary of the summit area at (r, c);
    None when that area holds higher ground, i.e. this is a sub-top."""
    h, w = dem.shape
    # One cell beyond the disk, so the boundary just outside it is in reach.
    r0, r1 = max(0, r - zone_r - 1), min(h, r + zone_r + 2)
    c0, c1 = max(0, c - zone_r - 1), min(w, c + zone_r + 2)
    if not tracks[r0:r1, c0:c1].any():
        return 0.0
    sub = dem[r0:r1, c0:c1]
    d = disk[r0 - r + zone_r + 1:r1 - r + zone_r + 1, c0 - c + zone_r + 1:c1 - c + zone_r + 1]
    high = (sub >= z - ZONE_DROP_M) & d
    labels, _ = ndimage.label(high)
    zone = labels == labels[r - r0, c - c0]
    if (sub[zone] > z).any():
        return None
    # 8-connected, so a track leaving the area diagonally still lands on it.
    edge = ndimage.binary_dilation(zone, structure=EIGHT) & ~zone
    return float(tracks[r0:r1, c0:c1][edge].sum()) / 2.0


def find(min_score: float = MIN_SCORE) -> pd.DataFrame:
    px = config.PIXEL_SIZE
    peak_r = int(round(PEAK_RADIUS_M / px))
    zone_r = int(round(ZONE_RADIUS_M / px))
    ring_dy, ring_dx = _ring(RING_RADIUS_M / px)
    drop_dy, drop_dx = _ring(DROP_RADIUS_M / px)
    pad = max(peak_r, int(DROP_RADIUS_M / px), zone_r) + 3
    yy, xx = np.mgrid[-zone_r - 1:zone_r + 2, -zone_r - 1:zone_r + 2]
    disk = np.hypot(yy, xx) <= zone_r

    tracks_ds = gdal.Open(str(paths.layer("tracks")))
    dem_ds = gdal.Open(str(paths.layer("dem")))
    tracks_band, dem_band = tracks_ds.GetRasterBand(1), dem_ds.GetRasterBand(1)
    dem_nodata = dem_band.GetNoDataValue()
    tgt, dgt = tracks_ds.GetGeoTransform(), dem_ds.GetGeoTransform()
    # Same 10 m lattice, so the DEM is the tracks grid shifted by whole cells.
    dem_dx = int(round((tgt[0] - dgt[0]) / px))
    dem_dy = int(round((dgt[3] - tgt[3]) / px))
    w, h = tracks_ds.RasterXSize, tracks_ds.RasterYSize

    rows = []
    started = time.time()
    y_windows = list(_windows(h, pad))
    for bi, (ry, rh, cy, ch) in enumerate(y_windows):
        for rx, rw, cx, cw in _windows(w, pad):
            tracks = tracks_band.ReadAsArray(rx, ry, rw, rh)
            if not tracks[cy:cy + ch, cx:cx + cw].any():
                continue
            dem = dem_band.ReadAsArray(rx + dem_dx, ry + dem_dy, rw, rh).astype(np.float32)
            valid = np.isfinite(dem)
            if dem_nodata is not None:
                valid &= dem != dem_nodata
            dem[~valid] = -1e9

            top = ndimage.maximum_filter(dem, size=2 * peak_r + 1, mode="nearest")
            peak = (dem == top) & valid
            core = np.zeros_like(peak)
            core[cy:cy + ch, cx:cx + cw] = True
            peak &= core
            if not peak.any():
                continue
            # A flat top ties over several cells: one summit per tied patch.
            labels, n = ndimage.label(peak, structure=EIGHT)
            _, first = np.unique(labels.ravel(), return_index=True)
            pr, pc = np.unravel_index(first[1:], labels.shape)   # [0] is background

            def at(arr, dy, dx):
                rr = np.clip(pr[:, None] + dy[None, :], 0, rh - 1)
                cc = np.clip(pc[:, None] + dx[None, :], 0, rw - 1)
                return arr[rr, cc]

            z = dem[pr, pc]
            around = at(dem, drop_dy, drop_dx)
            around = np.where(around > -1e8, around, np.nan)
            drop = z - np.nanmean(around, axis=1)
            ring = at(tracks, ring_dy, ring_dx).astype(np.int64).sum(axis=1) / 2.0
            for i in np.flatnonzero(drop >= MIN_DROP_M):
                area = _summit_area_visits(dem, tracks, pr[i], pc[i], z[i], zone_r, disk)
                if area is None:
                    continue
                visits = min(area, REACH_FACTOR * ring[i])
                if visits < min_score:
                    continue
                rows.append({
                    "x": tgt[0] + (rx + pc[i] + 0.5) * px,
                    "y": tgt[3] - (ry + pr[i] + 0.5) * px,
                    "est_visits": float(visits),
                    "area_visits": area,
                    "ring_visits": float(ring[i]),
                    "elev_m": round(float(z[i]), 1),
                    "drop_m": round(float(drop[i]), 1),
                })
        print(f"  row {bi + 1}/{len(y_windows)}: {len(rows)} summits so far, "
              f"{time.time() - started:.0f} s", flush=True)

    return pd.DataFrame(rows, columns=["x", "y", "est_visits", "area_visits", "ring_visits",
                                       "elev_m", "drop_m"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--top", type=int, default=500, help="how many go in the `top` layer")
    ap.add_argument("--min-score", type=float, default=MIN_SCORE)
    args = ap.parse_args()

    df = find(args.min_score)
    df = df.sort_values("est_visits", ascending=False, ignore_index=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.x, df.y),
                           crs=f"EPSG:{config.CRS_EPSG}")
    ll = gdf.geometry.to_crs(4326)
    gdf["lat"], gdf["lon"] = ll.y.round(6), ll.x.round(6)
    # norgeskart takes UTM 33 easting/northing in its lon/lat parameters.
    gdf["norgeskart"] = [
        f"https://norgeskart.no/#!?project=norgeskart&layers=1002&zoom=14&lat={y:.0f}&lon={x:.0f}"
        for x, y in zip(gdf.x, gdf.y)
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    top = gdf.head(args.top)
    top.to_file(OUT_GPKG, layer="top", driver="GPKG")
    gdf.to_file(OUT_GPKG, layer="all", driver="GPKG")
    top.drop(columns="geometry").to_csv(OUT_CSV, index=False)
    print(f"{len(gdf)} summits scored; top {len(top)} written to {OUT_GPKG} and {OUT_CSV}")


if __name__ == "__main__":
    main()
