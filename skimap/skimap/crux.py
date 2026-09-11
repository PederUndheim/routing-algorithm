"""The Crux Identifier: where along a Route the terrain asks for attention.

Walk the line from start to end, one sample per 10 m cell, and give each
sample the highest-ranked Danger class that applies there (see CONTEXT.md):

    Probable release area   PRA above 50 %
    Fall hazard             slope 30 degrees or steeper, no upper cap
    Runout area             0 <= runout < 10000 m. 0 is release ground
                            itself, and deliberately counts

Consecutive samples of one class form a run. A run of a Danger class is a
Danger zone, and a Crux is its first sample - in the line's own direction,
so "where a zone begins" is where a ski tourer following it gets there.

A short dip does not split a zone. Where a Danger zone is interrupted by
less than max_dip_m of lower-ranked ground - a lower Danger class, none or
No data - and then carries on in the same class, it stays one zone with one
Crux: at 10 m a sample, a line along a zone's edge flickers in and out of
it, and every flicker would otherwise be a marker. A stretch of a HIGHER
class is never a dip, however short. A 10 m crossing of a release area is
exactly the kind of brief hazard that must not be smoothed away.

What counts as missing. Only the slope raster's nodata is a hole. PRA's
nodata (-128) is where the model found no release area at all, and the
runout raster's (10000) is ground beyond its reach: on a mountain window
around two thirds of cells are the first and a quarter the second, so
reading either as "unknown" would grey out most of every route. Those two
are missing only off their raster's extent. A sample where any raster is
missing is No data - unless one that is present already establishes a
Danger class, which then stands.

The thresholds live in config.CRUX.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import osr

from skimap import config, exposure, paths

WGS84_EPSG = 4326

PROBABLE_RELEASE_AREA = "probable_release_area"
FALL_HAZARD = "fall_hazard"
RUNOUT_AREA = "runout_area"
NONE = "none"
NO_DATA = "no_data"

# Index = the code a sample carries. RANK is what ranking compares: the
# Danger classes in order, None and No data both below every one of them.
CLASSES = (NO_DATA, NONE, RUNOUT_AREA, FALL_HAZARD, PROBABLE_RELEASE_AREA)
RANK = (0, 0, 1, 2, 3)
_NO_DATA, _NONE, _RUNOUT, _FALL, _RELEASE = range(5)

# Samples per raster read. A read covers its piece of line's bounding box,
# so however long the route, no read is more than 500 x 500 cells - where one
# window over a 50 km diagonal would be 5000 x 5000 per raster.
PIECE_SAMPLES = 500

# Output coordinates, in decimal degrees: about a centimetre.
_DECIMALS = 7


@dataclass(frozen=True)
class Sources:
    """The three rasters a Route is read against."""

    pra: Path
    slope: Path
    runout: Path

    @classmethod
    def national(cls) -> "Sources":
        """The national PRA, the derived slope layer and the Flow-Py runout."""
        return cls(pra=paths.source("pra"), slope=paths.layer("slope"),
                   runout=paths.source("runout"))


def _transform(from_epsg: int, to_epsg: int) -> osr.CoordinateTransformation:
    """(x, y) in, (x, y) out - lng/lat for WGS84, never GDAL 3's lat/lng."""
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(from_epsg)
    target.ImportFromEPSG(to_epsg)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


_TO_GRID = _transform(WGS84_EPSG, config.CRS_EPSG)
_FROM_GRID = _transform(config.CRS_EPSG, WGS84_EPSG)


def identify(route: dict, sources: Optional[Sources] = None) -> dict:
    """The Danger zones and Cruxes along one Route.

    `route` is a GeoJSON LineString in WGS84, followed in its point order.
    Returns:

        segments    consecutive runs: class, start_m, end_m and a WGS84 line
        cruxes      in route order: number, class, position {lat, lng},
                    distance_m from the start, length_m of its Danger zone,
                    and over that zone max_pra_percent (Probable release
                    area) or max_slope_deg (Fall hazard)
        length_m    the whole line, on the metric grid
        no_data_m   how much of it is No data

    Raises ValueError for anything that is not a usable WGS84 line.
    """
    sources = sources or Sources.national()
    settings = config.CRUX

    vertices = _grid_vertices(route)
    vertex_along = np.concatenate(
        [[0.0], np.cumsum(np.hypot(*np.diff(vertices, axis=0).T))])
    total = float(vertex_along[-1])

    along, xy = exposure.sample_stations(vertices, float(settings["sample_spacing_m"]))
    pra = _read(sources.pra, xy, nodata_as=0.0)            # no release area
    slope = _read(sources.slope, xy, nodata_as=np.nan)     # unknown
    runout = _read(sources.runout, xy, nodata_as=np.inf)   # beyond reach
    codes = _classify(pra, slope, runout)

    # Each sample stands for the ground halfway to its neighbours, so a run
    # is drawn from midpoint to midpoint and adjacent segments meet.
    edges = np.concatenate([[0.0], (along[:-1] + along[1:]) / 2.0, [total]])

    segments, cruxes = [], []
    for code, first, last in _bridge(_runs(codes), edges, float(settings["max_dip_m"])):
        start, end = float(edges[first]), float(edges[last + 1])
        segments.append({
            "class": CLASSES[code],
            "start_m": round(start, 1),
            "end_m": round(end, 1),
            "line": _wgs84_line(_cut(vertices, vertex_along, start, end)),
        })
        if RANK[code] > 0:
            lng, lat = _wgs84_points(xy[first:first + 1])[0]
            entry = {
                "number": len(cruxes) + 1,
                "class": CLASSES[code],
                "position": {"lat": lat, "lng": lng},
                "distance_m": round(float(along[first]), 1),
                "length_m": round(end - start, 1),
            }
            # How bad it gets, over the whole zone. nanmax, because a
            # bridged no-data hole inside it is part of the zone too.
            zone = slice(first, last + 1)
            if code == _RELEASE:
                entry["max_pra_percent"] = round(float(np.nanmax(pra[zone])), 1)
            elif code == _FALL:
                entry["max_slope_deg"] = round(float(np.nanmax(slope[zone])), 1)
            cruxes.append(entry)

    no_data_m = sum(s["end_m"] - s["start_m"] for s in segments if s["class"] == NO_DATA)
    return {
        "segments": segments,
        "cruxes": cruxes,
        "length_m": round(total, 1),
        "no_data_m": round(no_data_m, 1),
    }


# --- the line --------------------------------------------------------------


def _grid_vertices(route: dict) -> np.ndarray:
    """The route's vertices on the metric grid, repeats dropped."""
    if not isinstance(route, dict) or route.get("type") != "LineString":
        raise ValueError("Expected the route as a GeoJSON LineString.")
    try:
        lnglat = np.array([(float(p[0]), float(p[1])) for p in route["coordinates"]],
                          dtype=np.float64).reshape(-1, 2)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("The route's coordinates must be [lng, lat] pairs.") from exc
    if not np.isfinite(lnglat).all() or (np.abs(lnglat) > (180.0, 90.0)).any():
        raise ValueError("The route must be WGS84 (lat/lon).")

    xy = np.asarray(_TO_GRID.TransformPoints(lnglat.tolist()), dtype=np.float64)[:, :2]
    # A GPS recording stands still as often as it moves. Repeats are zero-length
    # steps, and interpolating along a line needs its distances to increase.
    moved = np.concatenate([[True], (np.diff(xy, axis=0) != 0.0).any(axis=1)])
    xy = xy[moved]
    if len(xy) < 2:
        raise ValueError("The route needs at least two distinct points.")
    return xy


def _cut(vertices: np.ndarray, along: np.ndarray, start: float, end: float) -> np.ndarray:
    """The stretch of the line between two distances along it."""
    def at(d: float) -> np.ndarray:
        return np.array([[np.interp(d, along, vertices[:, 0]),
                          np.interp(d, along, vertices[:, 1])]])

    inside = (along > start) & (along < end)
    return np.vstack([at(start), vertices[inside], at(end)])


def _wgs84_points(xy: np.ndarray) -> list[tuple[float, float]]:
    return [(round(lng, _DECIMALS), round(lat, _DECIMALS))
            for lng, lat, _ in _FROM_GRID.TransformPoints(xy.tolist())]


def _wgs84_line(xy: np.ndarray) -> dict:
    return {"type": "LineString",
            "coordinates": [list(p) for p in _wgs84_points(xy)]}


# --- the rasters -----------------------------------------------------------


def _read(path: Path, xy: np.ndarray, *, nodata_as: float) -> np.ndarray:
    """One raster's value under every sample, a piece of the line at a time.

    NaN off the raster. `nodata_as` is what a nodata cell reads as - NaN
    where nodata is a hole, a value where it is an answer.
    """
    return np.concatenate([
        exposure.sample_raster(path, xy[i:i + PIECE_SAMPLES], nodata_as=nodata_as)
        for i in range(0, len(xy), PIECE_SAMPLES)
    ])


def _classify(pra: np.ndarray, slope: np.ndarray, runout: np.ndarray) -> np.ndarray:
    """Each sample's class code: the first that applies, in ranking order."""
    settings = config.CRUX
    with np.errstate(invalid="ignore"):
        conditions = [
            pra > settings["pra_threshold"],
            slope >= settings["slope_threshold"],
            (runout >= 0.0) & (runout < settings["runout_reach"]),
            np.isnan(pra) | np.isnan(slope) | np.isnan(runout),
        ]
    return np.select(conditions, [_RELEASE, _FALL, _RUNOUT, _NO_DATA], default=_NONE)


# --- runs ------------------------------------------------------------------


def _runs(codes: np.ndarray) -> list[tuple[int, int, int]]:
    """(code, first sample, last sample) for each stretch of one class."""
    breaks = np.flatnonzero(np.diff(codes)) + 1
    firsts = np.concatenate([[0], breaks])
    lasts = np.concatenate([breaks, [len(codes)]]) - 1
    return [(int(codes[f]), int(f), int(l)) for f, l in zip(firsts, lasts)]


def _bridge(runs: list[tuple[int, int, int]], edges: np.ndarray,
            max_dip_m: float) -> list[tuple[int, int, int]]:
    """Runs with every short dip merged back into the zone around it.

    A dip is one or more consecutive runs, each ranked below a Danger class,
    shorter than `max_dip_m` all together, with a run of that same class on
    both sides. The three become one run of that class. Run edges are in
    metres along the line: edges[first] to edges[last + 1].

    Only lower-ranked runs can be a dip, so a spike of a higher class stays.
    The first and last runs have a neighbour on one side only and are never
    merged into anything. After a merge the grown zone is tried again, since
    it may reach another short dip beyond.
    """
    runs = list(runs)
    i = 0
    while i < len(runs):
        code, first, last = runs[i]
        if RANK[code] > 0:
            dip_start = edges[last + 1]
            j = i + 1
            while (j < len(runs) and RANK[runs[j][0]] < RANK[code]
                   and edges[runs[j][1]] - dip_start < max_dip_m):
                j += 1
            # Stopped on the first run that ranks as high or higher, on one
            # that is already past max_dip_m, or at the end of the line.
            if (i + 1 < j < len(runs) and runs[j][0] == code
                    and edges[runs[j][1]] - dip_start < max_dip_m):
                runs[i:j + 1] = [(code, first, runs[j][2])]
                continue
        i += 1
    return runs
