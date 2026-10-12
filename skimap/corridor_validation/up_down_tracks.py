"""Split recorded ski-touring tracks into their uphill and downhill legs.

The corridors are built from an uphill cost model, so validating them
against a whole recorded trip would also score the descents - which follow
the fall line, not the skin track, and say nothing about where people
choose to go up.

The tracks carry neither Z nor timestamps, but their vertex order is time
order (checked by eye in ArcGIS on the first four test tours). Each track
is draped on the national 10 m DEM every SPACING_M and its height profile
cut at its turning points: the tops and bottoms where the skier turned
around. A turning point only counts once the profile has reversed from it
by at least --min-drop metres, so the dips and short rises inside a long
climb stay in that climb, while a day over two tops still gives two
uphill legs with the run between them as a downhill leg.

The legs cover the whole track, start to end, and alternate up and down.
A track that never moves --min-drop either way has no leg and is counted
as flat.

All of Norway, or a few tracks to try a different --min-drop on:

    python -m corridor_validation.up_down_tracks
    python -m corridor_validation.up_down_tracks --track-ids 12 345 --out test.gpkg

Run from skimap/ (the directory holding the skimap package). Writes one
GeoPackage with two layers, `uphill` and `downhill`, one row per leg, each
drawn in the direction it was travelled. `track_fid` is the source
shapefile's FID + 1: the OBJECTID the track had in the old tracks_working
layer, so the legs of one recording can always be found together.

The working layer that ski tours are assigned in is a copy of `uphill`,
made once with make_working_layer.py - never rewritten from here, since it
holds hand edits.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from osgeo import gdal
from shapely import LineString
from shapely.ops import substring

from skimap import exposure, paths

gdal.UseExceptions()

VALIDATION = paths.DATA / "validation_data"
TRACKS = VALIDATION / "tracks_DP5m_without_attributes" / "tracks_DP5m_without_attributes.shp"
UP_DOWN = VALIDATION / "up_down_tracks.gpkg"

SPACING_M = 10.0      # the DEM's own cell size; finer only resamples one cell
SMOOTH_SAMPLES = 5    # running median over 50 m, against single-cell DEM spikes
# Default --min-drop. On the four test tours the single-top ones
# (Dronningkrona, Nonshøa, Storhornet) stop gaining uphill legs at 50 m and
# do not change again up to 200 m: everything below 50 is DEM noise and dips
# inside a climb. Above 50 only the multi-top days (Tydalsnebba) keep
# merging, and a drop of 50 m or more is where skins come off for a real run.
MIN_DROP_M = 50.0


class Dem:
    """The national DEM, opened once and sampled one track window at a time."""

    def __init__(self, path: Path):
        self.ds = gdal.Open(str(path))
        self.band = self.ds.GetRasterBand(1)
        self.nodata = self.band.GetNoDataValue()
        self.inverse = gdal.InvGeoTransform(self.ds.GetGeoTransform())

    def sample(self, xy: np.ndarray) -> np.ndarray:
        inv = self.inverse
        px = np.floor(inv[0] + inv[1] * xy[:, 0] + inv[2] * xy[:, 1]).astype(np.int64)
        py = np.floor(inv[3] + inv[4] * xy[:, 0] + inv[5] * xy[:, 1]).astype(np.int64)
        out = np.full(len(xy), np.nan)
        on = (px >= 0) & (py >= 0) & (px < self.ds.RasterXSize) & (py < self.ds.RasterYSize)
        if on.any():
            x0, x1 = int(px[on].min()), int(px[on].max())
            y0, y1 = int(py[on].min()), int(py[on].max())
            window = self.band.ReadAsArray(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
            out[on] = window[py[on] - y0, px[on] - x0]
        if self.nodata is not None:
            out[out == self.nodata] = np.nan
        return out


def profile(line: LineString, dem: Dem) -> tuple[np.ndarray, np.ndarray]:
    """Distance along the line and smoothed height there, gaps interpolated."""
    s, xy = exposure.sample_stations(np.asarray(line.coords)[:, :2], SPACING_M)
    z = dem.sample(xy)
    ok = ~np.isnan(z)
    if ok.sum() < 2:
        return s, np.full(len(s), np.nan)
    z = np.interp(s, s[ok], z[ok])
    if len(z) >= SMOOTH_SAMPLES:
        z = pd.Series(z).rolling(SMOOTH_SAMPLES, center=True, min_periods=1).median().to_numpy()
    return s, z


def turning_points(z: np.ndarray, min_drop: float) -> tuple[list[int], int]:
    """Where the profile turns around, and whether it sets off up (+1) or down (-1).

    The first index is 0 and the last is the profile's end, so the legs
    between them cover the whole track. A top is only confirmed once the
    profile has dropped `min_drop` below it, and a bottom once it has risen
    `min_drop` above it; a smaller reversal stays inside the leg it
    interrupts. ([], 0) for a track that never moves `min_drop` either way.
    """
    # Until the profile has moved min_drop from somewhere, it has not
    # declared a direction: track the running low and high from the start.
    lo = hi = 0
    for i in range(1, len(z)):
        lo = i if z[i] < z[lo] else lo
        hi = i if z[i] > z[hi] else hi
        if z[i] - z[lo] >= min_drop:
            first = trend = 1
            break
        if z[hi] - z[i] >= min_drop:
            first = trend = -1
            break
    else:
        return [], 0

    pivots, extreme = [0], i
    for i in range(i + 1, len(z)):
        if trend == 1:
            if z[i] > z[extreme]:
                extreme = i
            elif z[extreme] - z[i] >= min_drop:
                pivots.append(extreme)
                trend, extreme = -1, i
        else:
            if z[i] < z[extreme]:
                extreme = i
            elif z[i] - z[extreme] >= min_drop:
                pivots.append(extreme)
                trend, extreme = 1, i
    # The last leg runs to the end of the recording. Whatever follows its
    # final top or bottom is a reversal smaller than min_drop - the walk back
    # up to the car after the run down - and belongs to that leg.
    pivots.append(len(z) - 1)
    return pivots, first


def legs(line: LineString, dem: Dem, min_drop: float) -> list[dict] | None:
    """The line's legs in travel order. None if it lies off the DEM."""
    s, z = profile(line, dem)
    if np.isnan(z).all():
        return None
    pivots, direction = turning_points(z, min_drop)
    out = []
    for a, b in zip(pivots[:-1], pivots[1:]):
        seg = z[a:b + 1]
        out.append({
            "direction": "uphill" if direction > 0 else "downhill",
            "geometry": substring(line, s[a], s[b]),
            "z_start": round(float(z[a]), 1),
            "z_end": round(float(z[b]), 1),
            # Net height across the leg, and the climbing and descending
            # inside it - the gap between the two is the small dips and
            # rises the leg absorbed.
            "net_m": round(float(z[b] - z[a]), 1),
            "climb_m": round(float(np.clip(np.diff(seg), 0, None).sum()), 1),
            "descent_m": round(float(-np.clip(np.diff(seg), None, 0).sum()), 1),
            "length_m": round(float(s[b] - s[a]), 1),
        })
        direction = -direction
    return out


def run(track_ids: list[int] | None, min_drop: float, out: Path) -> None:
    tracks = gpd.read_file(TRACKS, columns=[], fid_as_index=True)
    tracks.index = tracks.index + 1
    tracks = tracks.rename_axis("track_fid").reset_index()
    if track_ids:
        tracks = tracks[tracks["track_fid"].isin(track_ids)]
    print(f"{len(tracks)} tracks, min drop {min_drop:g} m")

    dem = Dem(paths.source("dem"))
    rows, flat, off_dem = [], 0, 0
    for n, row in enumerate(tracks.itertuples(index=False), 1):
        ident = {"track_fid": row.track_fid}
        # Three tracks in the national set are multipart. The gap between
        # parts has no height profile to cut across, so each part is its own
        # run of legs; leg_no still counts through the whole track.
        track_legs = []
        for part in getattr(row.geometry, "geoms", [row.geometry]):
            part_legs = legs(part, dem, min_drop)
            if part_legs is None:
                off_dem += 1
                continue
            track_legs += part_legs
        flat += not track_legs
        for no, leg in enumerate(track_legs, 1):
            rows.append({**ident, "leg_no": no, "n_legs": len(track_legs), **leg})
        if n % 2000 == 0:
            print(f"  {n}/{len(tracks)}")

    result = gpd.GeoDataFrame(rows, geometry="geometry", crs=tracks.crs)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    for direction in ("uphill", "downhill"):
        result[result["direction"] == direction].drop(columns="direction").to_file(out, layer=direction)
    report(result, tracks, flat, off_dem)
    print(f"wrote {out}")


def report(result: gpd.GeoDataFrame, tracks: gpd.GeoDataFrame, flat: int, off_dem: int) -> None:
    if flat or off_dem:
        print(f"{flat} tracks without a leg ({off_dem} parts off the DEM)")
    up = result[result["direction"] == "uphill"]
    per_track = up.groupby("track_fid").size()
    print("uphill legs per track:", per_track.value_counts().sort_index().to_dict())
    print(f"uphill keeps {up['length_m'].sum() / 1000:.0f} km of "
          f"{tracks.geometry.length.sum() / 1000:.0f} km")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--track-ids", type=int, nargs="+",
                   help="only these tracks (track_fid); all of Norway if left out")
    p.add_argument("--min-drop", type=float, default=MIN_DROP_M,
                   help="metres the profile must reverse by for a top or bottom to count")
    p.add_argument("--out", type=Path, default=UP_DOWN)
    a = p.parse_args()
    run(a.track_ids, a.min_drop, a.out)


if __name__ == "__main__":
    main()
