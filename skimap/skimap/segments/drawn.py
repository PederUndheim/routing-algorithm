"""What you drew, resolved against the routes.

A drawn feature carries one thing you have to supply - a colour - and one
you may leave blank. `tour_fid` picks which route it applies to; empty means
whichever route it lies along, which is right almost always and wrong only
where two routes run close enough to be confused. `assign` reports the
margin so an ambiguous one shows up rather than being silently guessed.

Lines become station windows; polygons stay geometry and are painted as
stencils later. That is the whole difference between the two tools and it is
resolved here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import ogr

from skimap import config
from skimap.segments import aoi
from skimap.segments.routes import Route

ogr.UseExceptions()

# The class vocabulary is EXPOSURE_CLASSES', in its order, so the digits are
# just positions in it and severity is an index. Both spellings are accepted
# because a shapefile integer field types faster than a text one.
CLASS_NAMES: tuple[str, ...] = tuple(name for _, name in config.EXPOSURE_CLASSES)
SEVERITY: dict[str, int] = {name: i for i, name in enumerate(CLASS_NAMES)}
CODES: dict[str, str] = {**{str(i + 1): n for i, n in enumerate(CLASS_NAMES)},
                         **{n: n for n in CLASS_NAMES}}

FIELDS = (("colour", ogr.OFTString, 16),
          ("tour_fid", ogr.OFTInteger, 10),
          ("note", ogr.OFTString, 64))


@dataclass
class Drawn:
    fid: int
    kind: str                  # "line" | "poly"
    colour: str
    geometry: ogr.Geometry
    tour_fid: int = 0
    route: Optional[int] = None
    s0: float = 0.0
    s1: float = 0.0
    margin: float = 0.0        # how much nearer the chosen route is than the next
    distance: float = 0.0

    @property
    def ambiguous(self) -> bool:
        return not self.tour_fid and self.margin < 100.0


def template(path: Path, geometry_type: int, *, layer: Optional[str] = None) -> Path:
    """An empty layer to digitize into, with the fields painting expects."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    drv = ogr.GetDriverByName("ESRI Shapefile")
    if path.exists():
        drv.DeleteDataSource(str(path))
    ds = drv.CreateDataSource(str(path))
    lyr = ds.CreateLayer(layer or path.stem, aoi.srs(), geometry_type)
    for name, kind, width in FIELDS:
        defn = ogr.FieldDefn(name, kind)
        defn.SetWidth(width)
        lyr.CreateField(defn)
    ds = None
    return path


def read(path: Path, kind: str, *, layer: Optional[str] = None) -> list[Drawn]:
    """Everything drawn into one layer. Unreadable colours are skipped, loudly."""
    path = Path(path)
    if not path.exists():
        return []
    ds, lyr = aoi.open_layer(path, layer)
    out: list[Drawn] = []
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None or geom.IsEmpty():
            continue
        raw = str(feat.GetField("colour") or "").strip().lower()
        if raw not in CODES:
            print(f"  !! {kind} {feat.GetFID()}: colour {raw!r} is not one of "
                  f"{sorted(CODES)} - skipped")
            continue
        out.append(Drawn(fid=feat.GetFID(), kind=kind, colour=CODES[raw],
                         geometry=geom.Clone(),
                         tour_fid=int(feat.GetField("tour_fid") or 0)))
    ds = None
    return out


def _vertices(geom: ogr.Geometry) -> np.ndarray:
    if geom.GetGeometryType() in (ogr.wkbPolygon, ogr.wkbPolygon25D):
        geom = geom.GetGeometryRef(0)
    return np.asarray(geom.GetPoints(), dtype=np.float64)[:, :2]


def assign(features: list[Drawn], routes: dict[int, Route]) -> None:
    """Give each feature its route and, for lines, its station window."""
    if not routes:
        raise ValueError("no routes to assign against")
    end_snap = float(config.SEGMENTS["end_snap_m"])

    for d in features:
        verts = _vertices(d.geometry)
        scored = sorted((float(r.station_of(verts)[1].mean()), fid)
                        for fid, r in routes.items())
        d.distance = scored[0][0]
        d.margin = (scored[1][0] - scored[0][0]) if len(scored) > 1 else float("inf")
        d.route = d.tour_fid if d.tour_fid in routes else scored[0][1]

        route = routes[d.route]
        if d.kind == "line":
            station = np.sort(route.station_of(verts)[0])
        else:
            # A polygon's honest span is the part of the ROUTE it contains,
            # not the spread of its corners - a wide polygon's corners
            # project further along the line than the ground it covers. Only
            # used for reporting; stencils are painted by geometry.
            clipped = route.geometry.Intersection(d.geometry)
            if clipped is not None and not clipped.IsEmpty():
                pts = []
                for i in range(clipped.GetGeometryCount() or 1):
                    part = clipped.GetGeometryRef(i) if clipped.GetGeometryCount() else clipped
                    pts.extend(part.GetPoints())
                station = np.sort(route.station_of(
                    np.asarray(pts, dtype=np.float64)[:, :2])[0])
            else:
                station = np.sort(route.station_of(verts)[0])

        s0, s1 = float(station[0]), float(station[-1])
        # Snapping the ends is what makes "the rest of the route" drawable
        # without precision. Overshooting a route end already clamps, since
        # the nearest point on a finite line is its endpoint; undershooting
        # would otherwise leave a sliver of the default colour behind.
        d.s0 = 0.0 if s0 <= end_snap else s0
        d.s1 = route.length_m if s1 >= route.length_m - end_snap else s1


def timeline(fid: int, features: list[Drawn], routes: dict[int, Route]
             ) -> tuple[list[tuple[float, float, str]], list[str]]:
    """One route's length divided into (s0, s1, colour), covering it entirely.

    Only lines take part. Polygons are stencils painted over the result, so
    they neither leave a gap here nor need the line under them removed.
    """
    route = routes[fid]
    heal = float(config.SEGMENTS["gap_heal_m"])
    default = str(config.SEGMENTS["default"])
    segs = sorted([d for d in features if d.route == fid and d.kind == "line"],
                  key=lambda d: d.s0)
    notes: list[str] = []
    if not segs:
        return [(0.0, route.length_m, default)], notes

    for a, b in zip(segs, segs[1:]):
        delta = b.s0 - a.s1
        if abs(delta) <= heal:
            mid = (a.s1 + b.s0) / 2.0
            notes.append(f"healed a {abs(delta):.0f} m "
                         f"{'overlap' if delta < 0 else 'gap'} -> cut at {mid:.0f} m")
            a.s1 = b.s0 = mid

    out: list[tuple[float, float, str]] = []
    cursor = 0.0
    for d in segs:
        if d.s0 > cursor + 1e-6:
            out.append((cursor, d.s0, default))
        out.append((max(d.s0, cursor), d.s1, d.colour))
        cursor = max(cursor, d.s1)
    if cursor < route.length_m - 1e-6:
        out.append((cursor, route.length_m, default))
    return out, notes
