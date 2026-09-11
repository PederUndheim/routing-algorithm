"""One start/end pair in, one least-cost route out.

A thin wrapper over skimap.routing, which is where the actual routing lives.
This only does the three things the browser makes necessary:

    - turn WGS84 lat/lng into the EPSG:25833 grid the cost surface is on,
      and the finished line back again
    - hold the single GRASS session the server routes through
    - throw away the corridor, which route_one always writes and the app
      never draws

No parameters: the surface is whatever `skimap.cli cost` last built, and
config.ROUTING supplies the rest. Anything tunable is tuned in config.py.
"""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from uuid import uuid4

from osgeo import ogr, osr

from app.backend import corridor as corridor_png
from skimap import config, paths, routing
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
        _started = True


def surface_name() -> str:
    """The cost surface being routed through, for the startup banner."""
    return paths.national_surface().name


def route(start_latlng: tuple[float, float],
          end_latlng: tuple[float, float]) -> dict:
    """Route between two (lat, lng) pairs. Returns WGS84 GeoJSON.

    Raises whatever GRASS raises - a point outside the surface, or two ends
    with no walkable ground between them, both come back as a RuntimeError
    with a usable message. The server turns that into a 400.
    """
    start_xy = _to_grid(start_latlng)
    end_xy = _to_grid(end_latlng)
    tour = Tour(fid=0, name="app", start=start_xy, end=end_xy)

    started = time.time()
    with _LOCK:
        geometry, cost, corridor_tif = routing.route_one(
            tour, SCRATCH, buffer_m=float(config.ROUTING["region_buffer_m"]))

        # Inside the lock: route_one names its outputs after the tour, so a
        # second route would overwrite this GeoTIFF before it was read.
        corridor_id = uuid4().hex[:12]
        bounds = corridor_png.to_png(corridor_tif, SCRATCH / f"{corridor_id}.png")
        corridor_tif.unlink(missing_ok=True)
    seconds = time.time() - started

    _prune_corridors()
    geometry = _start_to_end(geometry, start_xy)

    # Length while the line is still on the metric grid; degrees would need
    # a geodesic sum to mean anything.
    length_m = geometry.Length()
    straight_m = tour.straight_km * 1000.0
    geometry.Transform(FROM_GRID)

    return {
        "route": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"length_m": round(length_m, 1)},
                    "geometry": json.loads(geometry.ExportToJson()),
                }
            ],
        },
        "corridor": {"png_path": f"/corridor/{corridor_id}.png", "bounds": bounds},
        "length_m": round(length_m, 1),
        "straight_m": round(straight_m, 1),
        "detour": round(length_m / max(straight_m, 1e-6), 2),
        "cost": round(cost, 1),
        "seconds": round(seconds, 1),
    }


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
