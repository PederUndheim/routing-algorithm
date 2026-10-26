"""How much of Norway's recorded uphill skiing one model's corridors reach.

skimap.corridor_track_coverage answers this for whole trips, from the
tracks.tif density raster - descents included. The corridors come from an
uphill cost model, so the fairer test is the uphill legs alone: the
`uphill` layer of up_down_tracks.gpkg, every recorded track cut at its
turning points.

Weighted by length, not by leg: each leg is cut into pieces of at most
STEP_M, and a piece counts as covered when the corridor raster is above
MEMBERSHIP_FLOOR at its midpoint. Overlapping legs each count, so a skin
track a hundred people used weighs a hundred times one only a single
person did - the same weighting tracks.tif gives by counting passages.

Against a track variant's standard-width merge of every tour's corridor,
data/test/track_variants/<model>/corridors_all.tif:

    python -m corridor_validation.uphill_coverage                  # forest_1_2
    python -m corridor_validation.uphill_coverage --model max2

Run from skimap/. Writes data/review/stats/uphill_coverage_<model>.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from osgeo import gdal

from corridor_validation.up_down_tracks import UP_DOWN
from skimap import paths
from skimap.corridor_track_coverage import MEMBERSHIP_FLOOR, model_raster

gdal.UseExceptions()

STEP_M = 10.0          # the corridor raster's own cell size
CHUNK = 5000           # legs per batch, to keep the sampled pieces in memory
BLOCK_PX = 4096        # raster read window, in pixels per side
# Per-leg share of length inside the corridor, binned for the summary.
LEG_BINS = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0 + 1e-9)


class Corridor:
    """A corridor raster, read one window at a time around the points in it."""

    def __init__(self, path: Path):
        self.ds = gdal.Open(str(path))
        self.band = self.ds.GetRasterBand(1)
        self.nodata = self.band.GetNoDataValue()
        gt = self.ds.GetGeoTransform()
        self.x0, self.dx, self.y0, self.dy = gt[0], gt[1], gt[3], gt[5]

    def inside(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        px = np.floor((x - self.x0) / self.dx).astype(np.int64)
        py = np.floor((y - self.y0) / self.dy).astype(np.int64)
        out = np.zeros(len(x), dtype=bool)
        on = (px >= 0) & (py >= 0) & (px < self.ds.RasterXSize) & (py < self.ds.RasterYSize)
        if not on.any():
            return out

        idx = np.flatnonzero(on)
        block = (py[idx] // BLOCK_PX) * (self.ds.RasterXSize // BLOCK_PX + 1) + px[idx] // BLOCK_PX
        order = np.argsort(block, kind="stable")
        idx, block = idx[order], block[order]
        starts = np.flatnonzero(np.r_[True, block[1:] != block[:-1]])
        for start, stop in zip(starts, np.r_[starts[1:], len(idx)]):
            sel = idx[start:stop]
            wx0, wy0 = int(px[sel].min()), int(py[sel].min())
            wx1, wy1 = int(px[sel].max()) + 1, int(py[sel].max()) + 1
            arr = self.band.ReadAsArray(wx0, wy0, wx1 - wx0, wy1 - wy0)
            vals = arr[py[sel] - wy0, px[sel] - wx0]
            hit = vals > MEMBERSHIP_FLOOR
            if self.nodata is not None:
                hit &= vals != self.nodata
            out[sel] = hit
        return out


def pieces(geoms: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Every leg cut into segments of at most STEP_M: midpoint x, y, length,
    and which leg (position in `geoms`) each came from."""
    dense = shapely.segmentize(geoms, STEP_M)
    xy, leg = shapely.get_coordinates(dense, return_index=True)
    same = leg[1:] == leg[:-1]
    a, b = xy[:-1][same], xy[1:][same]
    mid = (a + b) / 2.0
    length = np.hypot(*(b - a).T)
    return mid[:, 0], mid[:, 1], length, leg[:-1][same]


def analyze(corridor_path: Path) -> dict:
    print(f"reading uphill legs from {UP_DOWN}")
    legs = gpd.read_file(UP_DOWN, layer="uphill", columns=["track_fid"])
    geoms = legs.geometry.values
    n = len(geoms)
    print(f"  {n:,} legs, {legs.track_fid.nunique():,} recordings")

    corridor = Corridor(corridor_path)
    leg_total = np.zeros(n)
    leg_covered = np.zeros(n)
    for start in range(0, n, CHUNK):
        chunk = np.asarray(geoms[start:start + CHUNK])
        x, y, length, leg = pieces(chunk)
        hit = corridor.inside(x, y)
        leg_total[start:start + len(chunk)] = np.bincount(leg, weights=length, minlength=len(chunk))
        leg_covered[start:start + len(chunk)] = np.bincount(leg, weights=length * hit, minlength=len(chunk))
        done = min(start + CHUNK, n)
        if done % 20000 < CHUNK or done == n:
            print(f"  {done:,}/{n:,} legs")

    total, covered = float(leg_total.sum()), float(leg_covered.sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(leg_total > 0, leg_covered / leg_total, 0.0)
    counts, _ = np.histogram(share, bins=LEG_BINS)
    labels = [f"{lo:.0%}-{min(hi, 1.0):.0%}" for lo, hi in zip(LEG_BINS[:-1], LEG_BINS[1:])]

    return {
        "corridor_raster": str(corridor_path),
        "uphill_legs": n,
        "recordings": int(legs.track_fid.nunique()),
        "uphill_km": total / 1000.0,
        "covered_km": covered / 1000.0,
        "covered_pct": covered / total * 100.0 if total else 0.0,
        "legs_touching_corridor": int((leg_covered > 0).sum()),
        "legs_fully_inside": int((share >= 0.999).sum()),
        "legs_by_share_inside": dict(zip(labels, map(int, counts))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m corridor_validation.uphill_coverage",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="forest_1_2",
                        help="track variant whose corridors_all.tif to measure (default forest_1_2)")
    parser.add_argument("--out", type=Path, help="where to write the summary JSON")
    args = parser.parse_args()

    result = analyze(model_raster(args.model))
    result["model"] = args.model

    print(f"\n{result['covered_pct']:.2f}% of all recorded UPHILL skiing in Norway "
          f"falls inside the {args.model} corridors (every tour, standard width)")
    print(f"  uphill total  {result['uphill_km']:12,.0f} km over {result['uphill_legs']:,} legs")
    print(f"  covered       {result['covered_km']:12,.0f} km")
    print(f"  legs touching a corridor at all: {result['legs_touching_corridor']:,}, "
          f"wholly inside one: {result['legs_fully_inside']:,}")
    print("\nlegs by share of their length inside:")
    for label, count in result["legs_by_share_inside"].items():
        print(f"  {label:>9s}  {count:7,d}  {count / result['uphill_legs'] * 100:5.1f}%")

    out = args.out or paths.DATA / "review" / "stats" / f"uphill_coverage_{args.model}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
