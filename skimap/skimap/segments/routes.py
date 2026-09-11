"""Stationing: where along its route a cell sits.

The whole method rests on this one idea. Give every corridor cell the arc
length of the nearest point on its route, and a cut at a station is
automatically perpendicular to the route and automatically spans the full
width of the band, however faint it has become at the edge.

Drawing the cuts as actual perpendicular LINES would be the obvious
alternative and it does not work: on the inside of a bend, perpendiculars at
two nearby stations cross each other, and the ground between them gets
carved into slivers belonging to neither. Stationing has no such failure -
the nearest-point map is defined everywhere and single-valued.

Its one weakness is a route that doubles back close to itself, where a cell
lies near two very different stations and the nearer one wins arbitrarily.
`self_proximity` measures that, so a route it would misbehave on can be
reported rather than quietly mis-painted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import ogr

from skimap import config, paths, routing

ogr.UseExceptions()


@dataclass
class Route:
    """One routed line, densified and indexed for nearest-point queries."""

    tour_fid: int
    name: str
    length_m: float
    station: np.ndarray        # arc length of each sample
    points: np.ndarray         # (n, 2) sample coordinates
    geometry: ogr.Geometry

    def __post_init__(self):
        from scipy.spatial import cKDTree
        self._tree = cKDTree(self.points)

    def station_of(self, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(station, distance) of the nearest route point to each of `xy`."""
        distance, index = self._tree.query(xy)
        return self.station[index], distance

    def self_proximity(self, *, apart_m: float = 300.0, near_m: float = 120.0) -> float:
        """Share of the line that passes close to a distant part of itself.

        Above a few percent, stationing is ambiguous somewhere on this route
        and a cut may land in two places. Out-and-back tours score high.
        """
        n = len(self.points)
        if n > 4000:                      # O(n^2); thin before measuring
            take = np.linspace(0, n - 1, 4000).astype(int)
            pts, sta = self.points[take], self.station[take]
        else:
            pts, sta = self.points, self.station
        d = np.hypot(pts[:, 0][:, None] - pts[:, 0][None, :],
                     pts[:, 1][:, None] - pts[:, 1][None, :])
        far = np.abs(sta[:, None] - sta[None, :]) > apart_m
        return float(((d < near_m) & far).any(axis=1).mean())


def densify(geometry: ogr.Geometry, step_m: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Points every `step_m` along a line, plus its far end, with stations.

    Evenly spaced rather than at the line's own vertices: v.generalize thins
    the straights and keeps the bends, so vertex spacing carries the
    smoothing's opinion about curvature and would leave corners sampled far
    more densely than straights.
    """
    xy = np.asarray(geometry.GetPoints(), dtype=np.float64)[:, :2]
    seg = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
    along = np.concatenate([[0.0], np.cumsum(seg)])
    length = float(along[-1])
    if length <= 0.0:
        return np.zeros(1), xy[:1], 0.0
    station = np.append(np.arange(0.0, length, step_m), length)
    points = np.column_stack([np.interp(station, along, xy[:, 0]),
                              np.interp(station, along, xy[:, 1])])
    return station, points, length


def load(routes_path: Optional[Path] = None, *, only: Optional[set[int]] = None,
         step_m: Optional[float] = None) -> dict[int, Route]:
    """tour_fid -> Route, for the tours asked for (or all of them)."""
    routes_path = Path(routes_path) if routes_path else (paths.ROUTES / "routes.gpkg")
    if not routes_path.exists():
        raise FileNotFoundError(
            f"No routes at {routes_path}. Run 'python -m skimap.cli route' first."
        )
    step_m = float(step_m if step_m is not None else config.SEGMENTS["step_m"])

    ds = ogr.Open(str(routes_path))
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    if layer is None:
        raise KeyError(f"No layer {routing.ROUTES_LAYER!r} in {routes_path}")

    found: dict[int, Route] = {}
    for feat in layer:
        fid = feat.GetField("tour_fid")
        if only is not None and fid not in only:
            continue
        geom = feat.GetGeometryRef()
        if geom is None or geom.GetPointCount() < 2:
            continue
        station, points, length = densify(geom, step_m)
        found[fid] = Route(
            tour_fid=fid,
            name=str(feat.GetField("name") or ""),
            length_m=length,
            station=station,
            points=points,
            geometry=geom.Clone(),
        )
    ds = None

    missing = (only or set()) - set(found)
    if missing:
        raise KeyError(f"No route in {routes_path.name} for tour(s) {sorted(missing)}")
    return found
