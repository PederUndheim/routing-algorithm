"""Points in, one route through them out - each leg least-cost over the
terrain or a drive along the roads - or any line in, and the corridor
around it.

A thin wrapper over skimap.routing and skimap.road_network, which is where
the actual routing lives. This only does the things the browser makes
necessary:

    - turn WGS84 lat/lng into the EPSG:25833 grid the cost surface is on,
      and the finished line back again
    - hold the single GRASS session the server routes through, and the
      road network, loaded once
    - turn each corridor GeoTIFF into a PNG for the map, and keep only the
      last few

No parameters: the surface is whatever `skimap.cli cost` last built, and
config.ROUTING supplies the rest. Anything tunable is tuned in config.py.
"""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
from osgeo import ogr, osr

from app.backend import corridor as corridor_png
from skimap import config, crux, paths, road_network, routing
from skimap.tours import Tour

WGS84_EPSG = 4326

# Where the corridor each route comes with is turned into a PNG and left for
# the browser to fetch. Scratch in the real sense: the GeoTIFF goes as soon
# as it is converted, and only the last few pictures are kept.
SCRATCH = paths.ROUTES / "app_scratch"
KEEP_CORRIDORS = 12

# The app gets its own mapset rather than working in PERMANENT.
#
# A computational region belongs to a mapset, and route_one sets one per
# route, from that pair's bounding box. Two things in PERMANENT at once
# therefore move the region out from under each other mid-spread, and both
# come back with nonsense - which is what happens the moment someone runs
# `skimap.cli route` while this server is up. Stepping aside into `app` makes
# the region private, and the surface is still read from PERMANENT, where
# every mapset can see it.
MAPSET = "app"

# GRASS is also process-global - one GISRC, one set of per-route map names -
# so routes are serialized even though the server is threaded.
_LOCK = threading.Lock()
_started = False
_session = None

# The road network, or why there is none. Road routes take no lock: they
# only read these arrays, and never touch GRASS, so a drive can be routed
# while a terrain route holds _LOCK.
_roads: road_network.RoadNetwork | None = None
_roads_missing = "The road network has not been loaded."


def _transform(from_epsg: int, to_epsg: int) -> osr.CoordinateTransformation:
    """A transformer that takes and returns (x, y), never (y, x).

    GDAL 3 honours each CRS's declared axis order, which for EPSG:4326 is
    lat/lng - the opposite of every other coordinate in this file. The
    traditional-order flag puts both sides in lng/lat so a point is (x, y)
    whichever CRS it is in.
    """
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(from_epsg)
    target.ImportFromEPSG(to_epsg)
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


TO_GRID = _transform(WGS84_EPSG, config.CRS_EPSG)
FROM_GRID = _transform(config.CRS_EPSG, WGS84_EPSG)


def start() -> None:
    """Open GRASS, link the cost surface, and step into the app's mapset.

    Called once before the first request rather than lazily, so the cost of
    it lands on server startup where it is visible, and a missing GRASS or
    an unbuilt surface fails before anything is listening.

    This is routing.start_session() with a mapset switch on the end - the
    link has to go into PERMANENT, which every mapset can read, before
    stepping aside into one that owns its own region. See MAPSET.
    """
    global _started, _session

    with _LOCK:
        if _started:
            return
        _session, grassdata = routing.open_project()
        routing.link_external(routing.COST_RASTER, paths.national_surface(), grassdata)
        routing.switch_mapset(grassdata, MAPSET)
        _load_roads()
        _started = True


def _load_roads() -> None:
    """Load the road network, and route once along one of its roads.

    Missing is not fatal: terrain routing works without it, and a road
    route then says how to build it. The one throwaway route is because the
    first Dijkstra in a process takes several seconds longer than the rest,
    and that belongs here rather than on someone's first drive.
    """
    global _roads, _roads_missing

    try:
        network = road_network.RoadNetwork.load()
    except FileNotFoundError as exc:
        _roads_missing = str(exc)
        return
    points = network.edge_points(0)
    network.route(tuple(points[0]), tuple(points[-1]))
    _roads = network


def surface_name() -> str:
    """The cost surface being routed through, for the startup banner."""
    return paths.national_surface().name


def roads_status() -> str:
    """The road network, for the startup banner."""
    if _roads is None:
        return f"none - {_roads_missing}"
    return f"{_roads.node_count:,} junctions"


def route_tour(points: list[tuple[float, float]], networks: list[str]) -> dict:
    """Route through (lat, lng) points in order, and join the legs into one
    line. Returns WGS84 GeoJSON, start to end.

    `networks` says how each leg goes, one per leg - so one fewer than the
    points: "terrain" over the cost surface, or "road" along the road
    network. A point where a road leg starts or ends is moved onto the road
    first, so the leg either side of it meets the drive exactly where the
    drive begins: a terrain leg walks to the road, not to where the click
    happened to land beside it.

    The terrain legs' corridors are merged into one picture; with no
    terrain leg there is none - the car stays on the road. `cost` is the sum
    over the legs when they share a network and None for a mix, since a
    terrain cost and a drive in seconds add up to nothing. `tunnels` and
    `ferries` are [start_m, end_m] along the joined line - what the app
    hands back to /crux to leave out.

    Raises ValueError, worded for the user, for a point too far from any
    road or two with no road between them; and whatever GRASS raises for a
    terrain leg - a point outside the surface, no walkable ground between
    two of them - as a RuntimeError with a usable message. The server turns
    both into a 400.
    """
    if len(points) < 2 or len(networks) != len(points) - 1:
        raise ValueError("Give at least two points, and one network per leg between them.")
    if "road" in networks and _roads is None:
        raise RuntimeError(_roads_missing)

    xy = [_to_grid(p) for p in points]
    for i in range(len(xy)):
        if "road" in networks[max(i - 1, 0):i + 1]:
            xy[i] = _roads.snapped(xy[i], _point_name(i, len(xy)))

    started = time.time()
    lines: list[np.ndarray] = [np.empty((0, 2))] * len(networks)
    costs = [0.0] * len(networks)
    drives: dict[int, road_network.RoadRoute] = {}

    # Drives first and outside the lock: they never touch GRASS.
    for i, network in enumerate(networks):
        if network == "road":
            drives[i] = _roads.route(xy[i], xy[i + 1])
            lines[i], costs[i] = drives[i].xy, drives[i].drive_s

    corridor = None
    terrain = [i for i, network in enumerate(networks) if network == "terrain"]
    if terrain:
        tifs: list[Path] = []
        with _LOCK:
            try:
                for i in terrain:
                    # One fid per leg: route_one names its outputs after the
                    # tour, and every leg's corridor is needed for the merge.
                    tour = Tour(fid=i, name="app", start=xy[i], end=xy[i + 1])
                    geometry, costs[i], tif = routing.route_one(
                        tour, SCRATCH, buffer_m=float(config.ROUTING["region_buffer_m"]))
                    tifs.append(tif)
                    geometry = _start_to_end(geometry, xy[i])
                    lines[i] = np.array(geometry.GetPoints(), dtype=np.float64)[:, :2]

                # Inside the lock: the next route writes the same GeoTIFFs.
                corridor_id = uuid4().hex[:12]
                bounds = corridor_png.to_png(tifs, SCRATCH / f"{corridor_id}.png")
            finally:
                for tif in tifs:
                    tif.unlink(missing_ok=True)
        _prune_corridors()
        corridor = {"png_path": f"/corridor/{corridor_id}.png", "bounds": bounds}
    seconds = time.time() - started

    line, starts_m = join_legs(lines)
    # Lengths while the line is still on the metric grid, as crux measures.
    length_m = float(np.hypot(*np.diff(line, axis=0).T).sum())
    straight_m = sum(math.dist(a, b) for a, b in zip(xy[:-1], xy[1:]))
    ends_m = starts_m[1:] + [length_m]
    lnglat = [[round(lng, 7), round(lat, 7)]
              for lng, lat, _ in FROM_GRID.TransformPoints(line.tolist())]

    answer = {
        "route": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"length_m": round(length_m, 1)},
                    "geometry": {"type": "LineString", "coordinates": lnglat},
                }
            ],
        },
        "corridor": corridor,
        "network": networks[0] if len(set(networks)) == 1 else "mixed",
        "length_m": round(length_m, 1),
        "straight_m": round(straight_m, 1),
        "detour": round(length_m / max(straight_m, 1e-6), 2),
        "cost": round(sum(costs), 1) if len(set(networks)) == 1 else None,
        "seconds": round(seconds, 1),
        "legs": [
            {"network": network, "start_m": round(a, 1), "end_m": round(b, 1),
             "cost": round(cost, 1)}
            for network, a, b, cost in zip(networks, starts_m, ends_m, costs)
        ],
    }
    if drives:
        answer["tunnels"] = [[round(starts_m[i] + a, 1), round(starts_m[i] + b, 1)]
                             for i, drive in drives.items() for a, b in drive.tunnels]
        answer["ferries"] = [[round(starts_m[i] + a, 1), round(starts_m[i] + b, 1)]
                             for i, drive in drives.items() for a, b in drive.ferries]
    return answer


def join_legs(lines: list[np.ndarray]) -> tuple[np.ndarray, list[float]]:
    """Each leg's line, (n, 2) on the grid, run together into one - and how
    far along it each leg starts.

    A leg that begins where the last one ended loses its first point, so
    the joined line never stands still. One that begins a little off - a
    terrain leg starts on the centre of its first cell, not the point
    itself - is joined by the short straight step between them, and starts
    where that step ends.
    """
    parts: list[np.ndarray] = []
    starts_m: list[float] = []
    length_m, last = 0.0, None
    for leg in lines:
        if last is not None:
            length_m += math.dist(last, leg[0])
        starts_m.append(length_m)
        length_m += float(np.hypot(*np.diff(leg, axis=0).T).sum())
        shared = last is not None and np.array_equal(leg[0], last)
        parts.append(leg[1:] if shared else leg)
        last = leg[-1]
    return np.vstack(parts), starts_m


def _point_name(index: int, count: int) -> str:
    """How an error names a point: by its place on the route."""
    if index == 0:
        return "start point"
    if index == count - 1:
        return "end point"
    return f"waypoint {index}"


def corridor(line: dict) -> dict:
    """The corridor around a line that did not come from the router - drawn,
    uploaded, or a routed one since edited. `line` is a WGS84 GeoJSON
    LineString.

    See routing.line_corridor for how it differs from a routed corridor.
    Raises ValueError for a line that is not one, which the server turns
    into a 400 like any other.
    """
    xy = crux.grid_vertices(line)

    started = time.time()
    with _LOCK:
        line_tif = SCRATCH / "line_app.tif"
        cost = routing.line_corridor(xy, line_tif, tag="app")
        # Inside the lock for route()'s reason: the next one writes here too.
        corridor_id = uuid4().hex[:12]
        bounds = corridor_png.to_png(line_tif, SCRATCH / f"{corridor_id}.png")
        line_tif.unlink(missing_ok=True)
    seconds = time.time() - started

    _prune_corridors()
    return {
        "corridor": {"png_path": f"/corridor/{corridor_id}.png", "bounds": bounds},
        "cost": round(cost, 1),
        "seconds": round(seconds, 1),
    }


def improve(line: dict) -> dict:
    """Where a line the router did not make could go a clearly cheaper way
    close beside itself - see routing.improve_line. `line` is a WGS84
    GeoJSON LineString.

    Each suggestion says where it leaves and rejoins the line (start_m,
    end_m, on the metric grid - `length_m` is the whole line on the same
    measure, for the app to scale to its own), the new way as a WGS84
    LineString from the one point to the other, both costs, and what ground
    the old stretch and the new way each cross (crux.ground) - which is
    what the user decides on, not the costs.

    Raises ValueError for a line that is not one, which the server turns
    into a 400 like any other.
    """
    xy = crux.grid_vertices(line)

    started = time.time()
    with _LOCK:
        found = routing.improve_line(xy, tag="app")
    # Outside the lock: the Crux Identifier's rasters are not GRASS.
    suggestions = [
        {
            "start_m": round(s["start_m"], 1),
            "end_m": round(s["end_m"], 1),
            "line": {"type": "LineString", "coordinates": _lnglat(s["xy"])},
            "cost": round(s["cost"], 1),
            "old_cost": round(s["line_cost"], 1),
            "before": crux.ground(s["old_xy"]),
            "after": crux.ground(s["xy"]),
        }
        for s in found
    ]
    return {
        "suggestions": suggestions,
        "length_m": round(float(np.hypot(*np.diff(xy, axis=0).T).sum()), 1),
        "seconds": round(time.time() - started, 1),
    }


def _lnglat(xy: np.ndarray) -> list[list[float]]:
    return [[round(lng, 7), round(lat, 7)]
            for lng, lat, _ in FROM_GRID.TransformPoints(np.asarray(xy).tolist())]


def corridor_file(corridor_id: str) -> Path:
    """Where `corridor_id`'s PNG is. The id is checked by the caller."""
    return SCRATCH / f"{corridor_id}.png"


def _prune_corridors() -> None:
    """Keep the last few PNGs, drop the rest.

    A browser may still be showing the previous route's corridor while you
    pick the next one, so they cannot go the moment a new one arrives; and
    nothing here is worth keeping across a restart either.
    """
    pngs = sorted(SCRATCH.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in pngs[KEEP_CORRIDORS:]:
        stale.unlink(missing_ok=True)


def _to_grid(latlng: tuple[float, float]) -> tuple[float, float]:
    lat, lng = latlng
    x, y, _ = TO_GRID.TransformPoint(lng, lat)
    return float(x), float(y)


def _start_to_end(geometry: ogr.Geometry,
                  start_xy: tuple[float, float]) -> ogr.Geometry:
    """The same line, running start to end.

    r.path walks the direction raster backwards from the end point, so what
    comes out of GRASS runs end to start - fine for a line on a map, wrong
    for anything that reads the direction. Which way round it is gets checked
    rather than assumed: comparing the two ends costs nothing and does not
    depend on that GRASS detail staying put.
    """
    last_index = geometry.GetPointCount() - 1
    if last_index < 1:
        return geometry

    first = geometry.GetPoint_2D(0)
    last = geometry.GetPoint_2D(last_index)
    if math.dist(first, start_xy) <= math.dist(last, start_xy):
        return geometry

    flipped = ogr.Geometry(ogr.wkbLineString)
    for i in range(last_index, -1, -1):
        flipped.AddPoint_2D(*geometry.GetPoint_2D(i))
    return flipped
