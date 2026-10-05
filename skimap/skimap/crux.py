"""The Crux Identifier: where along a Route the terrain asks for attention.

Walk the line from start to end, one sample per 10 m cell. Two kinds of
ground matter, and a sample is the first of these that applies:

    Steep slope     slope 30 degrees or steeper
    Runout area     0 <= runout < 10000 m. 0 is release ground itself,
                    and deliberately counts

Everything else is none, or No data where a raster is missing. The map this
is read against shades slope from 30 degrees up, so a Steep slope is the
thing under the cursor and the classes line up with what is already on
screen.

Probable release area and Fall hazard are not classes of their own. They
are what a Steep slope turns out to be: a steep area holding PRA above
pra_threshold anywhere in it is a probable release area, one reaching
fall_threshold is a fall hazard, and it can be both. Each shows as a mark on
the area's own Crux, and makes the whole area red rather than orange. PRA
off steep ground is ignored - the slope map shows nothing there, so a marker
would point at terrain that looks flat.

Consecutive samples of one class form a run; runs are merged into areas:

    - No data or none shorter than split_gap_m between two danger runs is
      not a break, and reads as the lower of the two around it.
    - Runout shorter than steep_gap_m between two steep areas joins them
      into one. Climbing a slope, crossing a bench, and carrying on up is
      one decision, not three, and the whole span takes the worst class.
    - A Runout area shorter than min_runout_m reads as none: a line
      clipping the fringe of a runout zone for a cell is not worth drawing.

An area is one segment, and one colour, so the line never changes colour
without a reason. A Crux is the first sample of an area whose class ranks
ABOVE the area before it - none and No data rank 0, Runout area 1, Steep
slope 2. So arriving at steep ground always places a marker, and so does the
first runout after safe ground, while runout running out below a slope you
have just crossed does not: you were already told about that slope, and the
line turning orange says the rest. It is the one place a colour carries no
marker of its own, and it is deliberate.

What counts as missing. Only the slope raster's nodata is a hole. PRA's
nodata (-128) is where the model found no release area at all, and the
runout raster's (10000) is ground beyond its reach: on a mountain window
around two thirds of cells are the first and a quarter the second, so
reading either as "unknown" would grey out most of every route. A sample
whose slope is missing is Runout area if the runout raster puts it in one,
and No data otherwise - a known danger outranks a missing raster.

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

STEEP_SLOPE = "steep_slope"
RUNOUT_AREA = "runout_area"
NONE = "none"
NO_DATA = "no_data"

# Index = the code a sample carries. RANK is what ranking compares, and what
# decides where a Crux goes: a marker where an area outranks the one before.
CLASSES = (NO_DATA, NONE, RUNOUT_AREA, STEEP_SLOPE)
RANK = (0, 0, 1, 2)
_NO_DATA, _NONE, _RUNOUT, _STEEP = range(4)

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

        segments    the areas, in order: class, start_m, end_m, a WGS84
                    line, and for a Steep slope what it turns out to be -
                    probable_release_area, fall_hazard, max_slope_deg and
                    max_pra_percent
        cruxes      the areas that outrank the one before them, in route
                    order: number, position {lat, lng}, distance_m from the
                    start, length_m of the area, and the same class and
                    hazard fields its segment carries
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

    areas = _areas(_runs(codes), edges, settings)

    # One area, one segment, one colour. A Crux goes on an area that
    # outranks the one before it, so every rise in severity is marked and a
    # fall back to runout below a slope already marked is not.
    segments, cruxes = [], []
    before = _NONE   # the line starts out of danger, so its first area rises
    for code, first, last in areas:
        start, end = float(edges[first]), float(edges[last + 1])
        hazards = _hazards(code, slice(first, last + 1), pra, slope, settings)
        segments.append({
            "class": CLASSES[code],
            "start_m": round(start, 1),
            "end_m": round(end, 1),
            "line": _wgs84_line(_cut(vertices, vertex_along, start, end)),
            **hazards,
        })
        rises, before = RANK[code] > RANK[before], code
        if rises:
            lng, lat = _wgs84_points(xy[first:first + 1])[0]
            cruxes.append({
                "number": len(cruxes) + 1,
                "class": CLASSES[code],
                "position": {"lat": lat, "lng": lng},
                "distance_m": round(float(along[first]), 1),
                "length_m": round(end - start, 1),
                **hazards,
            })

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
    """Each sample's class code: the first that applies, in ranking order.

    PRA is not read here. It says what a Steep slope turns out to be, not
    whether one is there - see _hazards.
    """
    settings = config.CRUX
    with np.errstate(invalid="ignore"):
        conditions = [
            slope >= settings["steep_threshold"],
            (runout >= 0.0) & (runout < settings["runout_reach"]),
            np.isnan(slope) | np.isnan(runout),
        ]
    return np.select(conditions, [_STEEP, _RUNOUT, _NO_DATA], default=_NONE)


def _hazards(code: int, zone: slice, pra: np.ndarray, slope: np.ndarray,
             settings: dict) -> dict:
    """What a Steep slope area turns out to be, over the whole area.

    A steep area is a probable release area if PRA passes its threshold
    anywhere in it, and a fall hazard if the slope reaches fall_threshold
    anywhere in it. Both can be true, and both are drawn. Nothing but a
    Steep slope carries any of this: PRA off steep ground is ignored, and
    a Runout area's own steepness is not what makes it one.
    """
    if code != _STEEP:
        return {}
    with np.errstate(invalid="ignore"):
        release = bool(np.any(pra[zone] > settings["pra_threshold"]))
        fall = bool(np.any(slope[zone] >= settings["fall_threshold"]))
    hazards = {
        "probable_release_area": release,
        "fall_hazard": fall,
        "max_slope_deg": round(float(np.nanmax(slope[zone])), 1),
    }
    if release:
        hazards["max_pra_percent"] = round(float(np.nanmax(pra[zone])), 1)
    return hazards


# --- runs ------------------------------------------------------------------


def _runs(codes: np.ndarray) -> list[tuple[int, int, int]]:
    """(code, first sample, last sample) for each stretch of one class."""
    breaks = np.flatnonzero(np.diff(codes)) + 1
    firsts = np.concatenate([[0], breaks])
    lasts = np.concatenate([breaks, [len(codes)]]) - 1
    return [(int(codes[f]), int(f), int(l)) for f, l in zip(firsts, lasts)]


def _areas(runs: list[tuple[int, int, int]], edges: np.ndarray,
           settings: dict) -> list[tuple[int, int, int]]:
    """Runs merged into the areas a route is actually made of.

    Three passes, in this order. Each is a reason two runs are really one
    piece of ground, and every one of them only ever merges - no pass
    invents a class that was not in the runs it joined.
    """
    runs = _drop_short_runouts(runs, edges, float(settings["min_runout_m"]))
    runs = _close_gaps(runs, edges, float(settings["split_gap_m"]))
    return _merge_steep(runs, edges, float(settings["steep_gap_m"]))


def _close_gaps(runs: list[tuple[int, int, int]], edges: np.ndarray,
                split_gap_m: float) -> list[tuple[int, int, int]]:
    """Safe ground under `split_gap_m` between two danger runs is no break.

    At 10 m a sample a line along a zone's edge flickers in and out of it,
    and every flicker would otherwise end one area and start another. The
    gap reads as the lower of the two runs around it, so closing it never
    promotes anything: a flicker of none inside a runout becomes runout,
    and one between runout and steep becomes runout too.

    Only a gap with a danger run on both sides closes. Safe ground at
    either end of the line stays safe however short.
    """
    out = list(runs)
    for i, (code, first, last) in enumerate(runs):
        if (RANK[code] == 0 and 0 < i < len(runs) - 1
                and edges[last + 1] - edges[first] < split_gap_m):
            out[i] = (min(runs[i - 1][0], runs[i + 1][0], key=RANK.__getitem__),
                      first, last)
    return _join_touching(out)


def _merge_steep(runs: list[tuple[int, int, int]], edges: np.ndarray,
                 steep_gap_m: float) -> list[tuple[int, int, int]]:
    """Two steep areas under `steep_gap_m` apart, with only runout between,
    read as one area.

    Climbing a slope, crossing the bench below the next pitch and carrying
    on up is one decision. The runout between is swallowed and the whole
    span becomes Steep slope, which is also what makes it one colour: the
    worst of what it holds.

    Safe ground never merges, however short - _close_gaps has already
    closed the gaps that were only flicker, so what is left is real.
    """
    out: list[tuple[int, int, int]] = []
    for run in runs:
        out.append(run)
        if run[0] != _STEEP:
            continue
        # Walk back over the runout since the previous steep area, if the
        # whole gap is runout and short enough to be one piece of ground.
        gap = 0.0
        for i in range(len(out) - 2, -1, -1):
            code, first, last = out[i]
            if code == _STEEP:
                out[i:] = [(_STEEP, first, run[2])]
                break
            if code != _RUNOUT:
                break
            gap += edges[last + 1] - edges[first]
            if gap >= steep_gap_m:
                break
    return _join_touching(out)


def _join_touching(runs: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Adjacent runs of one class read as one run."""
    merged: list[tuple[int, int, int]] = []
    for code, first, last in runs:
        if merged and merged[-1][0] == code:
            merged[-1] = (code, merged[-1][1], last)
        else:
            merged.append((code, first, last))
    return merged


def _drop_short_runouts(runs: list[tuple[int, int, int]], edges: np.ndarray,
                        min_runout_m: float) -> list[tuple[int, int, int]]:
    """Runs with every Runout area shorter than `min_runout_m` read as None.

    First of the three passes, so that a fringe of runout too thin to draw
    is gone before the gaps around it are measured. None runs left side by
    side become one.
    """
    merged: list[tuple[int, int, int]] = []
    for code, first, last in runs:
        if code == _RUNOUT and edges[last + 1] - edges[first] < min_runout_m:
            code = _NONE
        if merged and merged[-1][0] == code:
            merged[-1] = (code, merged[-1][1], last)
        else:
            merged.append((code, first, last))
    return merged
