"""Least-cost routes and corridors through the national cost surface.

One route is three GRASS steps:

    r.cost        cumulative cost from each end. The one from the start also
                  writes a direction raster, recording which neighbour each
                  cell came from
    r.path        follow that direction raster back from the end to get the line
    v.generalize  Douglas-Peucker, so the line is not a staircase of pixels

Two spreads, not three, because the start-side one does double duty: its
direction raster builds the line, and its accumulation is the corridor's
`start->x` half. `start->x` plus `end->x` is the cost of the best route
through a cell, which is what makes a corridor definable at all - and it is
only a meaningful total because both halves are measured the same way. An
anisotropic spread would not give you that.

This used to run r.walk for the line, on the grounds that ski touring is
anisotropic - uphill and downhill are not the same journey. It was measured
and dropped. The cost surface already prices steepness (SLOPE runs from a
near-flat 0.05 below 30 degrees to BASE_MAX_COST above it, and
STEEP_SLOPE_BARRIER takes over past 45), so the two routers mostly agree:
over 808 tours routed both ways, 45% of the lines land within 50 m of each
other everywhere and 84% within 250 m, with a median worst separation of 60 m.

What r.walk did contribute, and nothing here replaces, is a penalty on
RE-ASCENT - no layer in the cost surface has a term for having already climbed
something. That shows on long tours in complex terrain: 22 of the 808 diverge
by more than a kilometre, and their median length is 7.0 km against 4.0 km
overall. Worth knowing when reading a long route. Dropping r.walk also took
the DEM out of routing entirely, along with the co-registration hazard that
came with pairing elevation and friction per cell, and made a route about 41%
cheaper to compute.

The surface is linked with r.external rather than imported, so the 1.65 GB
file is read in place, and the region is set per route to the pair's bounding
box plus a buffer - otherwise every spread would cover 19 Gpx.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from osgeo import gdal, ogr, osr

from skimap import config, paths
from skimap.tours import Tour

gdal.UseExceptions()
ogr.UseExceptions()

GRASS_PROJECT = "skimap25833"
COST_RASTER = "nat_cost"
# Only the r.walk engines read it; see config.WALK.
DEM_RASTER = "nat_dem"
ROUTES_LAYER = "routes"

# Written per route alongside the line. Everything here is either free (C_opt
# falls out of the corridor maths) or a length, so none of it costs a pass
# over the raster.
ROUTE_FIELDS = (
    ("tour_fid", ogr.OFTInteger),    # links back to the tour it came from
    ("name", ogr.OFTString),
    ("length_m", ogr.OFTReal),       # along the routed line
    ("straight_m", ogr.OFTReal),
    ("detour", ogr.OFTReal),         # length / straight, so 1.0 is a bee-line
    ("cost_opt", ogr.OFTReal),       # symmetric optimal cost, start to end
)


@dataclass(frozen=True)
class RouteResult:
    tour: Tour
    length_m: float
    cost_opt: float
    seconds: float
    corridor: Optional[Path]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def slug(text: str) -> str:
    """A filename-safe, GRASS-safe version of a tour name."""
    out = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return out or "unnamed"


# --- GRASS session ------------------------------------------------------


def _gisbase() -> str:
    """Where GRASS lives. GISBASE wins; otherwise take the one beside QGIS."""
    if os.environ.get("GISBASE"):
        return os.environ["GISBASE"]
    for base in sorted(Path("C:/Program Files").glob("QGIS*/apps/grass/grass*"), reverse=True):
        if (base / "etc" / "python").is_dir():
            return str(base)
    raise RuntimeError(
        "Cannot find GRASS. Set GISBASE to the install, e.g. "
        "C:/Program Files/QGIS 4.2.0/apps/grass/grass85"
    )


LINK_MARKERS = "link_markers"


def link_external(name: str, source: Path, grassdata: Path) -> None:
    """Link `source` as external raster `name`, unless it's already linked
    to this exact file.

    Plain `r.external` reads through the whole source once to compute its
    data range - harmless for a one-off, but start_session() used to redo it
    on every batch, and for the 16 GB national DEM that alone was ~145s of
    dead time before the first route started (measured). `-r` skips the scan
    entirely; safe here because r.cost/r.path read friction per cell, and
    nothing in this codebase reads nat_cost's range (no r.info/r.colors on it)
    - only re-add it if something later does. The marker file is what makes a
    relink a no-op on the next run:
    GRASS has no cheap way to ask "is this link still pointing at this file",
    so the source path and mtime are stamped alongside it by hand.
    """
    import grass.script as gs

    marker_dir = grassdata / LINK_MARKERS
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / f"{name}.txt"
    stamp = f"{source.resolve()}|{source.stat().st_mtime_ns}"

    linked = bool(gs.find_file(name, element="cell").get("file"))
    if linked and marker.exists() and marker.read_text(encoding="utf-8") == stamp:
        return

    # -o overrides the projection check: the rasters are EPSG:25833 but their
    # WKT does not always match GRASS's own to the letter.
    gs.run_command("r.external", input=str(source), output=name,
                   flags="or", overwrite=True, quiet=True)
    marker.write_text(stamp, encoding="utf-8")


def open_project(grassdata: Optional[Path] = None, *, mapset: str = "PERMANENT"):
    """Start GRASS on the shared project, without linking anything.

    Every entry into GRASS in this package goes through here, so there is one
    answer to where the install is, where grassdata lives and what the project
    is called. Callers link their own inputs afterwards with link_external.

    `mapset` other than PERMANENT is created on first use. Rasters written
    there stay out of everyone else's way while PERMANENT stays readable, so
    a pool of worker processes can each hold their own computational region -
    which is per-mapset, and is why a shared one cannot be parallelized.

    Returns (session, grassdata); the second is what link_external needs.
    """
    gisbase = _gisbase()
    os.environ["GISBASE"] = gisbase
    os.environ["PATH"] = os.pathsep.join(
        [str(Path(gisbase) / "bin"), str(Path(gisbase) / "scripts"), os.environ.get("PATH", "")]
    )
    python_path = str(Path(gisbase) / "etc" / "python")
    if python_path not in sys.path:
        sys.path.insert(0, python_path)

    import grass.script as gs
    import grass.script.setup as gsetup

    # create_project shells out to GRASS modules, so the runtime env has to be
    # live first or it fails without raising.
    gsetup.setup_runtime_env(gisbase)

    grassdata = grassdata or paths.DATA / "grass"
    grassdata.mkdir(parents=True, exist_ok=True)
    if not (grassdata / GRASS_PROJECT).is_dir():
        # GRASS 8.5 calls these projects; create_location is a shim that
        # quietly does nothing.
        gs.create_project(str(grassdata), GRASS_PROJECT, epsg=str(config.CRS_EPSG))

    session = gsetup.init(str(grassdata), GRASS_PROJECT, "PERMANENT")
    if mapset != "PERMANENT":
        switch_mapset(grassdata, mapset)
    return session, grassdata


def switch_mapset(grassdata: Path, mapset: str) -> None:
    """Move the open session into `mapset`, creating it if it is new.

    Separate from open_project because a caller often has to link something
    into PERMANENT first, where every mapset can read it, and only then step
    aside into its own. Going through open_project twice to do that would
    init a second session and leak the first one's GISRC.
    """
    import grass.script as gs

    # -c creates it; on an existing one it is an error, so ask first.
    exists = (grassdata / GRASS_PROJECT / mapset).is_dir()
    gs.run_command("g.mapset", mapset=mapset, quiet=True,
                   **({} if exists else {"flags": "c"}))


def start_session(grassdata: Optional[Path] = None, *,
                  surface: Optional[Path] = None,
                  cost_raster: str = COST_RASTER,
                  mapset: str = "PERMANENT"):
    """Start GRASS and link the cost surface in place.

    The DEM used to be linked here too, and checked against the surface for
    co-registration, because r.walk read the two as one grid and half a pixel
    of offset silently paired each elevation with a neighbouring cell's
    friction. Production routing is isotropic and never opens the DEM; the
    r.walk engines (config.WALK) do, and bring the check back with them.

    `mapset` other than PERMANENT routes in a mapset of its own, after
    linking into PERMANENT where it can read them. The computational region
    belongs to the mapset, so two batches in one mapset set it under each
    other - every spread then runs in the other tour's window, and fails or
    worse. Seen when two lab runs overlapped.
    """
    session, grassdata = open_project(grassdata)
    surface = surface or paths.national_surface()
    # A variant surface is linked under its own GRASS name, so it can sit in
    # the mapset beside the production one instead of relinking on every
    # switch between them.
    link_external(cost_raster, surface, grassdata)
    if _engine() != "cost":
        dem = paths.layer("dem")
        check_lattice(surface, dem)
        link_external(DEM_RASTER, dem, grassdata)
    if mapset != "PERMANENT":
        switch_mapset(grassdata, mapset)
    return session


def check_lattice(a: Path, b: Path) -> None:
    """Refuse two rasters whose cells do not line up.

    Checked on the georeferencing, not the arrays: half a pixel of offset
    leaves every array intact and pairs each cell with its neighbour's
    value - see skimap.alignment.
    """
    ga = gdal.Open(str(a)).GetGeoTransform()
    gb = gdal.Open(str(b)).GetGeoTransform()
    if ga[1] != gb[1] or ga[5] != gb[5] or ga[2] or ga[4] or gb[2] or gb[4]:
        raise RuntimeError(f"{a.name} and {b.name} have different or rotated pixels: "
                           f"{ga} vs {gb}")
    for i, size in ((0, ga[1]), (3, ga[5])):
        off = (ga[i] - gb[i]) / size
        if abs(off - round(off)) > 1e-6:
            raise RuntimeError(f"{a.name} sits {off % 1:.2f} of a pixel off {b.name}'s "
                               f"lattice; elevation would pair with a neighbour's cost.")


# --- one route ----------------------------------------------------------


def _import_point(name: str, xy: tuple[float, float]) -> None:
    import grass.script as gs

    gs.write_command("v.in.ascii", input="-", output=name, separator=",",
                     format="point", x=1, y=2, overwrite=True, quiet=True,
                     stdin=f"{xy[0]},{xy[1]}")


def _value_at(raster: str, point_vector: str) -> float:
    """Raster value under a point vector, as a float."""
    import grass.script as gs

    out = gs.read_command("r.what", map=raster, points=point_vector).strip()
    value = out.split("|")[-1].strip()
    if value in {"*", ""}:
        raise RuntimeError(
            f"{raster} is NULL at {point_vector}: the endpoints may be "
            "disconnected, or one of them sits outside the cost surface."
        )
    return float(value)


def _route_geometry(vector_map: str) -> ogr.Geometry:
    """Pull a vector line out of GRASS as an OGR geometry, via WKT.

    Read straight out of GRASS rather than exported to a file and re-read:
    at several hundred routes the temporary files are the slow part, and
    they would all have to be cleaned up afterwards anyway.
    """
    import grass.script as gs

    text = gs.read_command("v.out.ascii", input=vector_map, format="wkt").strip()
    parts = [line for line in text.splitlines() if line.strip().upper().startswith("LINESTRING")]
    if not parts:
        raise RuntimeError(f"No line geometry in {vector_map}")
    return ogr.CreateGeometryFromWkt(parts[0])


def _region_buffer(tour: Tour, ceiling_m: float) -> float:
    """This tour's region buffer: its own straight-line length, floored and
    capped at `ceiling_m`.

    A flat buffer on every tour spends most of its cells padding tours that
    never needed it - here the median tour is a ~3.4 km straight line, so a
    flat 5 km buffer was a bigger box than the route itself. Floored so a
    short tour still has room for a real detour around an obstacle, and
    capped at `ceiling_m` so nothing gets a bigger window than before.
    """
    floor_m = float(config.ROUTING["region_buffer_floor_m"])
    straight_m = tour.straight_km * 1000.0
    return min(ceiling_m, max(floor_m, straight_m))


def corridor_touches_edge(path: Path) -> dict[str, int]:
    """Live corridor cells sitting on the raster's own border, per side.

    The corridor is written at exactly the region extent and r.cost spreads
    only inside it, so a cell alive ON the border means the band was cut by
    the window. A corridor limited by terrain instead fades to null before it
    gets there. Empty dict means nothing reaches an edge.
    """
    dataset = gdal.Open(str(path))
    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray()
    nodata = band.GetNoDataValue()
    dataset = None
    if values is None:
        return {}
    live = np.isfinite(values) & (values != nodata)
    sides = {"north": live[0, :], "south": live[-1, :],
             "west": live[:, 0], "east": live[:, -1]}
    return {name: int(strip.sum()) for name, strip in sides.items() if strip.any()}


def _window_ladder(tour: Tour, ceiling_m: float) -> list[float]:
    """The buffers to try, in order: the natural one, then doublings.

    Only the first is used unless its corridor comes back touching an edge -
    see config.ROUTING["region_buffer_retry_cap_m"]. Doubling rather than
    jumping straight to the cap because the window is quadratic in the buffer
    and r.cost is linear in cells: the tours that need a second try mostly
    need one step, and paying the cap for them would cost 16x the area to fix
    a 2x problem.
    """
    first = _region_buffer(tour, ceiling_m)
    cap = float(config.ROUTING.get("region_buffer_retry_cap_m", 0.0))
    ladder = [first]
    while cap and ladder[-1] * 2 <= cap:
        ladder.append(ladder[-1] * 2)
    return ladder


def _spread_and_trace(tour: Tour, *, cost_raster: str, memory: int, tag: str,
                      start_pt: str, end_pt: str, direction: str,
                      from_start: str, from_end: str, gap: str, gap_pos: str,
                      line: str, smooth: str, scored: str,
                      params: dict, out_path: Path,
                      width_paths: dict[str, Path],
                      gap_path: Optional[Path] = None,
                      timings: Optional[dict] = None) -> tuple[ogr.Geometry, float]:
    """One window's worth of work: spread, trace, score, write the corridor.

    Everything here depends on the computational region already being set,
    and nothing here sets it. That is what lets route_one run it again in a
    wider window without any of this being written twice, and it is why the
    region is the caller's business rather than this function's.

    Returns the smoothed line and the symmetric optimal cost; the corridor
    goes to `out_path`, and each band of config.CORRIDOR_WIDTHS named in
    `width_paths` to its own.
    """
    import grass.script as gs

    timed = _timer(timings)
    with timed("spread"):
        cost_opt = _spreads(cost_raster=cost_raster, memory=memory, tag=tag,
                            start_pt=start_pt, end_pt=end_pt, direction=direction,
                            from_start=from_start, from_end=from_end, timings=timings)

    # How much worse than optimal a route through each cell would be. Clamped
    # at zero because floating point puts the cells on the optimal line a
    # hair below it.
    with timed("corridor"):
        gs.mapcalc(f"{gap} = ({from_start} + {from_end}) - {cost_opt}",
                   overwrite=True, quiet=True)
        gs.mapcalc(
            f"{gap_pos} = if(isnull({from_start}) || isnull({from_end}), null(), "
            f"if({gap} < 0, 0, {gap}))",
            overwrite=True, quiet=True,
        )

    with timed("line"):
        gs.run_command("r.path", input=direction, format="auto", start_points=end_pt,
                       vector_path=line, overwrite=True, quiet=True)
        gs.run_command("v.generalize", input=line, output=smooth, method="douglas",
                       threshold=float(config.ROUTING["smooth_threshold"]),
                       overwrite=True, quiet=True)
        geometry = _route_geometry(smooth)

    # The narrower and wider bands are the same gap read against another
    # budget, so they cost a pass over the region each and no spread.
    with timed("corridor"):
        for width, path in {None: out_path, **width_paths}.items():
            band = _band(params, width)
            max_gap = _max_gap(cost_opt, band)
            # 1 on the optimal line, falling to 0 at the edge of the slack band,
            # then raised to gamma to control how fast it falls away.
            gs.mapcalc(
                f"{scored} = float(pow(if({gap_pos} <= {max_gap}, "
                f"1 - ({gap_pos} / {max_gap}), null()), {band['gamma']}))",
                overwrite=True, quiet=True,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_corridor(scored, path)
        if gap_path is not None:
            # The raw gap, so a band at any other budget can be cut from it
            # afterwards without spreading again - only the lab asks.
            # Float32 loses digits a band threshold never reads, so -f.
            gap_path.parent.mkdir(parents=True, exist_ok=True)
            gs.run_command("r.out.gdal", input=gap_pos, output=str(gap_path),
                           format="GTiff", type="Float32", nodata=config.NODATA,
                           createopt="COMPRESS=DEFLATE,PREDICTOR=3,TILED=YES",
                           flags="cf", overwrite=True, quiet=True)
    return geometry, cost_opt


def _engine() -> str:
    engine = config.ROUTING.get("engine", "cost")
    if engine not in ("cost", "walk_line", "walk"):
        raise ValueError(f"config.ROUTING['engine'] is {engine!r}; "
                         f"one of 'cost', 'walk_line', 'walk'")
    return engine


def _timer(timings: Optional[dict]):
    """A context manager adding its block's wall time to timings[key]."""
    @contextmanager
    def timed(key: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            if timings is not None:
                timings[key] = timings.get(key, 0.0) + time.perf_counter() - t0
    return timed


def _walk_args() -> dict:
    walk = config.WALK
    return {"walk_coeff": walk["walk_coeff"], "slope_factor": float(walk["slope_factor"]),
            "lambda": float(walk["lambda"])}


def _spreads(*, cost_raster: str, memory: int, tag: str, start_pt: str, end_pt: str,
             direction: str, from_start: str, from_end: str,
             timings: Optional[dict]) -> float:
    """The two spreads the corridor is made of, and the direction raster the
    line is traced along. Returns cost_opt, in the corridor's own units.

    Their sum at a cell is the cost of the best route through that cell,
    which is what makes a corridor definable - and only while both are priced
    the same way and in the same direction of travel. See config.WALK for
    how each engine keeps to that.
    """
    import grass.script as gs

    engine = _engine()
    common = dict(memory=memory, overwrite=True, quiet=True)
    timed = _timer(timings)

    if engine == "cost":
        # The start-side spread carries outdir as well. That direction raster
        # records the way back to the start from every cell and is what
        # r.path walks to build the line, so this single spread covers both
        # the route and the corridor's `start->x` half.
        gs.run_command("r.cost", input=cost_raster, start_points=start_pt,
                       output=from_start, outdir=direction, **common)
        gs.run_command("r.cost", input=cost_raster, start_points=end_pt,
                       output=from_end, **common)
        return _value_at(from_start, end_pt)

    if engine == "walk_line":
        # The line from r.walk, the corridor from r.cost as in production.
        # The two disagree about what the optimum is, so the line need not
        # run along the corridor's spine.
        walk = f"walk_{tag}"
        gs.run_command("r.walk", elevation=DEM_RASTER, friction=cost_raster,
                       start_points=start_pt, output=walk, outdir=direction,
                       **_walk_args(), **common)
        if timings is not None:
            timings["walk_cost"] = _value_at(walk, end_pt)
        gs.run_command("g.remove", type="raster", name=walk, flags="f", quiet=True)
        gs.run_command("r.cost", input=cost_raster, start_points=start_pt,
                       output=from_start, **common)
        gs.run_command("r.cost", input=cost_raster, start_points=end_pt,
                       output=from_end, **common)
        return _value_at(from_start, end_pt)

    # "walk": from the end over -DEM is the cost from each cell TO the end,
    # walked the tour's way round; see config.WALK.
    negated = f"negdem_{tag}"
    with timed("negate"):
        gs.mapcalc(f"{negated} = -{DEM_RASTER}", overwrite=True, quiet=True)
    gs.run_command("r.walk", elevation=DEM_RASTER, friction=cost_raster,
                   start_points=start_pt, output=from_start, outdir=direction,
                   **_walk_args(), **common)
    gs.run_command("r.walk", elevation=negated, friction=cost_raster,
                   start_points=end_pt, output=from_end, **_walk_args(), **common)
    gs.run_command("g.remove", type="raster", name=negated, flags="f", quiet=True)
    cost_opt = _value_at(from_start, end_pt)
    if timings is not None:
        # The same trip priced from the other end. Equal unless the negation
        # is not doing what config.WALK says it does.
        timings["cost_check"] = _value_at(from_end, start_pt)
    return cost_opt


def _band(params: dict, width: Optional[str]) -> dict:
    """`params` for the standard band (width None), or narrowed or widened
    by config.CORRIDOR_WIDTHS."""
    return params if width is None else {**params, **config.CORRIDOR_WIDTHS[width]}


def _max_gap(cost_opt: float, params: dict) -> float:
    """How much dearer than optimal a route through a cell may be and still
    be in the band. A ceiling, not a fixed budget - see config.CORRIDOR. The
    slack term still governs anything below the ceiling, which is what keeps
    short tours band-shaped instead of collapsing to a disc.

    The ceiling is in the spread's own units, so under r.walk it is scaled
    by config.WALK["max_gap_scale"]."""
    cap = float(params["max_gap"])
    if _engine() == "walk":
        cap *= float(config.WALK["max_gap_scale"])
    return min(cost_opt * float(params["slack"]), cap)


def _write_corridor(raster: str, out_path: Path) -> None:
    import grass.script as gs

    gs.run_command("r.out.gdal", input=raster, output=str(out_path),
                   format="GTiff", type="Float32", nodata=config.NODATA,
                   createopt="COMPRESS=DEFLATE,PREDICTOR=3,TILED=YES",
                   flags="c", overwrite=True, quiet=True)


def width_dir(corridor_dir: Path, width: str) -> Path:
    """Where the `width` band of every corridor in `corridor_dir` goes: a
    sibling folder, corridors/ -> corridors_narrow/. Beside rather than
    inside, so whatever globs corridors/*.tif still finds the standard band
    and only that - merging, scoring, pruning and the lab all do."""
    return corridor_dir.with_name(f"{corridor_dir.name}_{width}")


def corridor_widths(corridor: Path) -> dict[str, Path]:
    """The narrower and wider bands written beside one standard corridor,
    those that are on disk. Empty for one routed before there were any."""
    found = {}
    for width in config.CORRIDOR_WIDTHS:
        path = width_dir(corridor.parent, width) / corridor.name
        if path.is_file():
            found[width] = path
    return found


def route_one(tour: Tour, corridor_dir: Path, *, buffer_m: float,
              cost_raster: str = COST_RASTER,
              widths: bool = True,
              gap_path: Optional[Path] = None,
              timings: Optional[dict] = None) -> tuple[ogr.Geometry, float, Path]:
    """Route one tour and write its corridor.

    `buffer_m` is a ceiling, not a fixed value - see `_region_buffer`.

    Routes again in a wider window if the corridor comes back touching the
    edge of the one it was routed in: such a corridor was cut by the box and
    not by the terrain, and the line inside it is not known to be the best
    one, because r.cost never looked past the edge. See `_window_ladder` and
    config.ROUTING["region_buffer_retry_cap_m"].

    `widths` also writes each band of config.CORRIDOR_WIDTHS into its own
    folder beside `corridor_dir` - see width_dir and corridor_widths.

    `gap_path` also writes the raw gap raster there. `timings`, if given, is
    filled with seconds per step, the window's cell count and how many
    windows it took - what the lab compares engines by.

    Returns the smoothed line, the symmetric optimal cost, and the corridor.
    """
    import grass.script as gs

    tag = f"{tour.fid}_{slug(tour.name)}"
    start_pt, end_pt = f"start_{tag}", f"end_{tag}"
    direction = f"dir_{tag}"
    from_start, from_end = f"symstart_{tag}", f"symend_{tag}"
    gap, gap_pos = f"gap_{tag}", f"gappos_{tag}"
    line, smooth = f"line_{tag}", f"smooth_{tag}"
    scored = f"score_{tag}"
    scratch = [direction, from_start, from_end, gap, gap_pos, scored]

    memory = int(config.ROUTING["grass_memory_mb"])
    xs, ys = (tour.start[0], tour.end[0]), (tour.start[1], tour.end[1])
    corridor_dir.mkdir(parents=True, exist_ok=True)
    out_path = corridor_dir / f"{tour.fid:03d}_{slug(tour.name)}.tif"
    params = config.CORRIDOR
    width_paths = ({width: width_dir(corridor_dir, width) / out_path.name
                    for width in config.CORRIDOR_WIDTHS} if widths else {})

    # Widest window first would be simpler and is the wrong way round: the
    # window is quadratic in the buffer and almost every tour is fine in its
    # natural one. So try that, look at what came back, and widen only where
    # the corridor says the box - not the terrain - is what stopped it.
    ladder = _window_ladder(tour, buffer_m)
    geometry, cost_opt = None, 0.0
    for attempt, region_buffer_m in enumerate(ladder):
        # The region is the pair's bounding box plus a buffer, snapped to the
        # cost surface.
        gs.run_command("g.region", raster=cost_raster, align=cost_raster,
                       w=min(xs) - region_buffer_m, e=max(xs) + region_buffer_m,
                       s=min(ys) - region_buffer_m, n=max(ys) + region_buffer_m)
        if timings is not None:
            timings["attempts"] = attempt + 1
            timings["cells"] = timings.get("cells", 0) + int(gs.region()["cells"])

        # Re-imported per attempt: v.in.ascii writes into the current region,
        # so points imported under the previous window are not reusable here.
        _import_point(start_pt, tour.start)
        _import_point(end_pt, tour.end)

        geometry, cost_opt = _spread_and_trace(
            tour, cost_raster=cost_raster, memory=memory, tag=tag,
            start_pt=start_pt, end_pt=end_pt, direction=direction,
            from_start=from_start, from_end=from_end, gap=gap, gap_pos=gap_pos,
            line=line, smooth=smooth, scored=scored, params=params,
            out_path=out_path, width_paths=width_paths,
            gap_path=gap_path, timings=timings,
        )

        # The widest band is the one to ask. The bands are nested, so it
        # reaches the edge whenever any does - and one cut off by the window
        # draws as a straight edge in the review whichever width it is.
        widest = max([None, *width_paths],
                     key=lambda width: _max_gap(cost_opt, _band(params, width)))
        touching = corridor_touches_edge(width_paths.get(widest, out_path))
        if not touching:
            break
        if attempt == len(ladder) - 1:
            # Out of ladder. Said out loud rather than letting a clipped
            # corridor pass as a finished one: at this width it is likelier
            # that the tour is wrong than that a route needs that much room.
            where = ", ".join(f"{k} {v}px" for k, v in sorted(touching.items()))
            print(f"    WARNING fid {tour.fid}: corridor still reaches the window "
                  f"edge ({where}) at a {region_buffer_m:.0f} m buffer, the cap - "
                  f"its route may not be the best one.")
            break
        sides = ", ".join(sorted(touching))
        print(f"    fid {tour.fid}: corridor reaches the {sides} edge of a "
              f"{region_buffer_m:.0f} m window - routing again at "
              f"{ladder[attempt + 1]:.0f} m")

    # Each route leaves a dozen full-region rasters behind. Over a few hundred
    # tours that is tens of GB in the mapset, for maps nothing reads again.
    gs.run_command("g.remove", type="raster", name=",".join(scratch),
                   flags="f", quiet=True)
    gs.run_command("g.remove", type="vector", name=",".join([start_pt, end_pt, line, smooth]),
                   flags="f", quiet=True)
    return geometry, cost_opt, out_path


# --- a corridor around a given line --------------------------------------
#
# A drawn, uploaded or edited line has no optimum to be near, so it gets a
# different corridor from a routed one: the ground within reach of the line
# itself. One spread from every cell the line crosses gives each cell its
# cost to reach from the line.
#
# A cell is in the band while reaching it from the line costs no more than
# one fixed budget, `max_cost`. Fixed on purpose: easy ground is cheap to
# cross, so the band spreads wide over it and leaves room to choose, and
# steep or exposed ground is dear, so the band stays tight there - the
# freedom follows the terrain, not the line. It used to be a share of the
# whole line's cost, which gave the same ground a narrower or wider band
# depending on how much route lay elsewhere; and a budget taken from the
# line's own cost per metre was tried and dropped, because it hands a line
# across steep ground the most room exactly where it should have the least.
#
# `max_m` caps it in plain distance as well: on a flat valley floor the
# budget alone would run for kilometres. Settings in config.LINE_CORRIDOR.
#
# Why not the routed corridor's own sum, seeded along the line: tried on real
# and drawn tracks, and it fails on every line that is not already optimal -
# which none drawn by hand or recorded by GPS is (27-50% dearer on three drawn
# ones, 15%-6.8x on recorded ones). Anything cheaper than the line scores as
# no detour at all, so it floods every cheaper way between the ends instead
# of the room around the line. On the optimal line itself it does reproduce
# the routed corridor exactly; that is all it is good for.


def _line_cells(xy: np.ndarray, west: float, north: float,
                res: float) -> tuple[np.ndarray, np.ndarray]:
    """(row, col) of each cell the line crosses, in order, 8-connected, and
    how far along the line each is entered, in metres.

    Densified to a metre so no cell is stepped over, then thinned wherever a
    cell's neighbours are diagonal to each other: a supercover walk takes
    every diagonal as two orthogonal steps where r.cost takes one, and left
    in, those corner cells overstate a slanted line's cost by up to a fifth.
    """
    step = np.diff(xy, axis=0)
    lengths = np.hypot(step[:, 0], step[:, 1])
    counts = np.maximum(1, np.ceil(lengths)).astype(int)
    within = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    fraction = within / np.repeat(counts, counts)
    dense = np.vstack([np.repeat(xy[:-1], counts, axis=0)
                       + fraction[:, None] * np.repeat(step, counts, axis=0),
                       xy[-1:]])
    dense_along = np.append(np.repeat(np.cumsum(lengths) - lengths, counts)
                            + fraction * np.repeat(lengths, counts), lengths.sum())

    cells = np.column_stack([np.floor((north - dense[:, 1]) / res),
                             np.floor((dense[:, 0] - west) / res)]).astype(int)
    entered = np.concatenate([[True], (np.diff(cells, axis=0) != 0).any(axis=1)])
    cells, along = cells[entered], dense_along[entered]
    if len(cells) == 1:
        return cells, along

    kept = [0]
    for i in range(1, len(cells) - 1):
        if np.abs(cells[i + 1] - cells[kept[-1]]).max() > 1:
            kept.append(i)
    kept.append(len(cells) - 1)
    return cells[kept], along[kept]


@dataclass
class _LineBand:
    """The band around a line, left in GRASS for the caller to write out or
    read, in the region it was made in - which is still the current one."""

    used: str              # raster: how far through its budget each cell is; 1 is the edge
    scratch: list[str]     # every raster made for it, for the caller to remove
    cells: np.ndarray      # the line's cells, (row, col) in the current region
    along: np.ndarray      # metres along the line where each is entered
    on_line: np.ndarray    # the surface under each
    line_cost: float
    # `used` against each narrower or wider budget asked for, by width.
    used_widths: dict[str, str]


def _line_params(width: Optional[str]) -> dict:
    """config.LINE_CORRIDOR for the standard band (width None), or narrowed
    or widened by config.LINE_CORRIDOR_WIDTHS."""
    params = config.LINE_CORRIDOR
    return params if width is None else {**params, **config.LINE_CORRIDOR_WIDTHS[width]}


def _line_band(line_xy: np.ndarray, *, cost_raster: str, tag: str,
               widths: Iterable[str] = ()) -> _LineBand:
    """Spread from the line through the surface, and score every cell by
    how much of the budget reaching it takes - see the note above
    _line_cells. Shared by the corridor and the optimiser, so a suggestion
    never leaves the band the map shows.

    `widths` scores the same spread against the budgets of those bands of
    config.LINE_CORRIDOR_WIDTHS too, in a window big enough for the widest."""
    import grass.script as gs
    from grass.script import array as garray

    xy = np.asarray(line_xy, dtype=np.float64)
    if xy.ndim != 2 or len(xy) < 2:
        raise ValueError("A line needs at least two points.")
    starts, reach, distance, used = (f"lstart_{tag}", f"lreach_{tag}",
                                     f"ldist_{tag}", f"lused_{tag}")
    bands = {None: _line_params(None), **{w: _line_params(w) for w in widths}}
    memory = int(config.ROUTING["grass_memory_mb"])
    west, east = xy[:, 0].min(), xy[:, 0].max()
    south, north = xy[:, 1].min(), xy[:, 1].max()

    # Costed and seeded in a window just big enough to hold the line, which
    # stays small however long the line is. The spread then runs in a wider
    # one; both are aligned to the surface, so the seeds land on the same
    # cells, and outside its own window the seed raster reads as null.
    gs.run_command("g.region", raster=cost_raster, align=cost_raster,
                   w=west - 50, e=east + 50, s=south - 50, n=north + 50)
    narrow = gs.region()
    res = narrow["ewres"]
    cells, along = _line_cells(xy, narrow["w"], narrow["n"], res)
    rows, cols = cells[:, 0], cells[:, 1]

    # -1 stands in for null: r.out.bin writes nulls as 0 otherwise, which
    # would read as free ground.
    cost = np.array(garray.array(mapname=cost_raster, null=-1, dtype=np.float64))
    on_line = cost[rows, cols]
    on_line[on_line < 0] = np.nan
    if np.isnan(on_line).all():
        raise RuntimeError("The line does not cross the cost surface.")
    # A gap in the surface under the line is charged as the dearest cell on
    # it, not as nothing - it should not make the line look cheap.
    on_line = np.where(np.isnan(on_line), np.nanmax(on_line), on_line)
    steps = np.hypot(*np.diff(cells, axis=0).T)
    line_cost = float(((on_line[:-1] + on_line[1:]) / 2.0 * steps).sum())

    seeds = garray.array(dtype=np.float32)
    seeds[...] = -1
    seeds[rows, cols] = 0
    seeds.write(starts, null=-1, overwrite=True, quiet=True)

    # One window, twice max_m out: the band never reaches past max_m, and the
    # spare is room for the cheapest way to a cell near the edge of the band
    # to swing out around something first. A routed corridor widens its
    # window and tries again when it touches an edge; this one has no need.
    # Sized for the widest band asked for, which the others fit inside.
    floor_m = float(config.ROUTING["region_buffer_floor_m"])
    buffer_m = max(2 * float(p["max_m"]) if float(p["max_m"]) > 0 else floor_m
                   for p in bands.values())
    gs.run_command("g.region", raster=cost_raster, align=cost_raster,
                   w=west - buffer_m, e=east + buffer_m,
                   s=south - buffer_m, n=north + buffer_m)
    wide = gs.region()
    gs.run_command("r.cost", input=cost_raster, start_raster=starts,
                   output=reach, memory=memory, overwrite=True, quiet=True)
    scratch = [starts, reach]
    if any(float(p["max_m"]) > 0 for p in bands.values()):
        gs.run_command("r.grow.distance", input=starts, distance=distance,
                       overwrite=True, quiet=True)
        scratch.append(distance)

    # How far through its budget each cell is: the cost to reach it against
    # max_cost, or its distance from the line against max_m, whichever is
    # further on. The band fades on that, so where the cap is what stops it
    # the edge still fades rather than cuts.
    names = {}
    for width, params in bands.items():
        name = used if width is None else f"{used}_{width}"
        share = f"{reach} / {float(params['max_cost'])}"
        if float(params["max_m"]) > 0:
            share = f"max({share}, {distance} / {float(params['max_m'])})"
        gs.mapcalc(f"{name} = float({share})", overwrite=True, quiet=True)
        scratch.append(name)
        names[width] = name

    # Into the wide window's own rows and columns, where the caller reads.
    offset = np.array([round((wide["n"] - narrow["n"]) / res),
                       round((narrow["w"] - wide["w"]) / res)])
    return _LineBand(used=used, scratch=scratch, cells=cells + offset, along=along,
                     on_line=on_line, line_cost=line_cost,
                     used_widths={w: n for w, n in names.items() if w is not None})


def line_corridor(line_xy: np.ndarray, out_path: Path, *,
                  cost_raster: str = COST_RASTER, tag: str = "line",
                  width_paths: Optional[dict[str, Path]] = None) -> float:
    """Write the corridor around `line_xy` (EPSG:25833, in order) to
    `out_path`, and return the line's own cost.

    `width_paths` also writes those bands of config.LINE_CORRIDOR_WIDTHS,
    each to its own path, from the same spread.

    The cost is what r.cost would charge to walk the cells the line crosses,
    so it is on the same scale as a routed Route's.
    """
    import grass.script as gs

    width_paths = width_paths or {}
    band = _line_band(line_xy, cost_raster=cost_raster, tag=tag, widths=width_paths)
    scored = f"lscore_{tag}"
    for width, path in {None: out_path, **width_paths}.items():
        used = band.used if width is None else band.used_widths[width]
        gs.mapcalc(
            f"{scored} = float(pow(if({used} <= 1, 1 - {used}, null()), "
            f"{_line_params(width)['gamma']}))",
            overwrite=True, quiet=True,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_corridor(scored, path)
    gs.run_command("g.remove", type="raster", name=",".join(band.scratch + [scored]),
                   flags="f", quiet=True)
    return band.line_cost


# --- improving a given line ----------------------------------------------
#
# Not routing the line again: finding the stretches of it where a clearly
# cheaper way runs close beside it, each one to be taken or left on its own.
#
# The search stays inside the line's own corridor (_line_band), so a
# suggestion is never a different valley - it is the better side of a gully,
# or round a steep roll, within ground the map already shows as near. In it,
# the line is cut into stations, and from each a spread finds the cheapest
# way to every station up to max_skip_m further on. Where one beats the
# line's own stretch between the two by enough, it is a candidate - enough
# being a share of the stretch's cost that grows with its length, so a long
# way has to be clearly better (_needed_saving). Candidates overlap, so the
# set shown is the one that makes the cheapest whole line: a pass over the
# stations choosing, at each, to keep the line or arrive by a candidate.
# That favours long ways, which skip the small cost of turning back to the
# line between two fixes; so a long one is then split into the shorter
# candidates it covers unless it saves long_gain_share more than they do.
# Every suggestion leaves the line at a station and rejoins it at a later
# one, and no two overlap, so each can be accepted without the others.
#
# Two kinds of line a cost surface would "improve" wrongly are kept out:
#   - a summit, or any out-and-back. Cutting the spur off is always cheaper
#     and never what was meant. So no suggestion spans a loop: any piece of
#     the line over loop_m long whose ends are closer than min_straightness
#     of its length. Checking only a suggestion's own two ends is not
#     enough - 1.5 km of line can hold a 600 m spur and still run straight
#     overall. Nor does a suggestion pass a turning point - a station where
#     the loop_m of line around it doubles back - since one that starts just
#     below a top spans no whole loop and would still cut the top off. It
#     may meet the line there. And it never joins two places on the line
#     heading more than max_turn_deg apart, which is going round a turn too
#     wide for either test to see.
#   - the other half of a loop or out-and-back. The band is the union around
#     the whole line, so beside the way out it also holds the way back. A
#     search keeps to the ground beside the stretch it may replace.
#   - a long way round. Steep ground costs so much more than flat that
#     going far round can still come out cheaper; past max_lengthening of
#     the stretch it is another route, not an improvement.
#   - a switchback skin track. Uphill zigzags are dearer per metre of
#     progress than going straight up, on a surface that does not know which
#     way is up. Broad ones are loops by the rule above; a suggestion that
#     never gets min_detour_m from the line is dropped as well, which is
#     what straightening tight ones does - it stays inside them.


# How far past its own stretch a search may reach onto ground beside the line,
# by sharing one graph with the stations near it. See _detours.
BLOCK_M = 250.0


def _band_graph(cost: np.ndarray, inside: np.ndarray):
    """The band's cells as a graph r.cost would walk: 8-connected, a step
    charged the mean of its two cells, times sqrt(2) on a diagonal.

    Returns the graph and each cell's node, -1 outside the band.
    """
    from scipy.sparse import csr_matrix

    node = np.full(cost.shape, -1, dtype=np.int64)
    rows, cols = np.nonzero(inside)
    node[rows, cols] = np.arange(len(rows))
    h, w = cost.shape
    heads, tails, weights = [], [], []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = (slice(0, h - dr), slice(max(0, -dc), w - max(0, dc)))
        b = (slice(dr, h), slice(max(0, dc), w - max(0, -dc)))
        both = (node[a] >= 0) & (node[b] >= 0)
        length = np.sqrt(2.0) if dr and dc else 1.0
        heads.append(node[a][both])
        tails.append(node[b][both])
        # A hair over the mean: scipy reads a stored zero as no edge at all.
        weights.append((cost[a][both] + cost[b][both]) / 2.0 * length + 1e-9)
    n = len(rows)
    graph = csr_matrix((np.concatenate(weights), (np.concatenate(heads), np.concatenate(tails))),
                       shape=(n, n))
    return graph, node


def _detours(cost: np.ndarray, inside: np.ndarray, cells: np.ndarray, along: np.ndarray,
             on_line: np.ndarray, res: float, params: dict) -> list[dict]:
    """Where to leave the line and where to rejoin it, and the way between.

    `cost` and `inside` are the window the line's `cells` are in; `along`
    and `on_line` are what _line_band gives with them. Pure, so it can be
    tested on a made-up grid. See the note above _band_graph.

    Returns, in order along the line: first and last (indices into
    `cells`), path (the cells between, both ends included), cost (the
    path's), line_cost (the line's own between the two) and minor (saves
    only what IMPROVE's `minor` asks, filling up to min_suggestions).
    """
    from scipy.ndimage import distance_transform_edt
    from scipy.sparse.csgraph import dijkstra

    steps = np.hypot(*np.diff(cells, axis=0).T)
    spent = np.concatenate([[0.0], np.cumsum((on_line[:-1] + on_line[1:]) / 2.0 * steps)])
    usable = inside & (cost >= 0)

    marks = np.append(np.arange(0.0, along[-1], float(params["station_m"])), along[-1])
    stations = np.unique(np.minimum(np.searchsorted(along, marks), len(cells) - 1))
    stations = stations[usable[cells[stations, 0], cells[stations, 1]]]
    if len(stations) < 2:
        return []
    station_along, station_spent = along[stations], spent[stations]

    max_skip = float(params["max_skip_m"])
    straightness = float(params["min_straightness"])
    ends = np.array([int(np.searchsorted(station_along, d + max_skip, side="right"))
                     for d in station_along])

    def apart_m(a: int, b: np.ndarray) -> np.ndarray:
        return np.hypot(*(cells[stations[b]] - cells[stations[a]]).T) * res

    # Where the line first turns back on itself after each station: the
    # nearest later station over loop_m of line away whose distance from it
    # is under min_straightness of that line. No suggestion may span one -
    # see the note above _band_graph.
    turns_back = np.full(len(stations), len(stations))
    for i in range(len(stations) - 1):
        j = np.arange(i + 1, ends[i])
        span = station_along[j] - station_along[i]
        loop = (span >= float(params["loop_m"])) & (apart_m(i, j) < straightness * span)
        if loop.any():
            turns_back[i] = j[np.argmax(loop)]

    # Where the line turns round: a summit, the far end of an out-and-back,
    # the hairpin of a switchback. The loop_m of line centred on the station
    # doubles back on itself. A suggestion may meet the line there, never
    # pass it by - a stretch that starts just below a top is not a loop by
    # the rule above, and would still cut the top off.
    half = float(params["loop_m"]) / 2.0
    lo = np.searchsorted(station_along, station_along - half)
    hi = np.searchsorted(station_along, station_along + half, side="right") - 1
    span = station_along[hi] - station_along[lo]
    apart = np.hypot(*(cells[stations[hi]] - cells[stations[lo]]).T) * res
    turn = (span >= half) & (apart < straightness * span)
    # The way the line is heading at each station, over the same loop_m. A
    # suggestion whose ends head more than max_turn_deg apart has gone round
    # a turn, however wide - a U whose legs are further apart than loop_m
    # never doubles back within it.
    heading = (cells[stations[hi]] - cells[stations[lo]]).astype(np.float64)
    heading /= np.maximum(np.hypot(*heading.T), 1e-9)[:, None]
    min_cos = np.cos(np.radians(float(params["max_turn_deg"])))
    # The first turn after each station, or past the end where there is none.
    next_turn = np.full(len(stations), len(stations))
    for i in range(len(stations) - 2, -1, -1):
        next_turn[i] = i + 1 if turn[i + 1] else next_turn[i + 1]

    # Which stretch of the line each cell of the band lies beside: how far
    # along the line the line cell nearest to it is. The band is the union
    # around the whole line, so near a loop tour's start it also holds the
    # ground beside its end - and a way from one station to the next must not
    # wander onto that. It may use only cells beside the stretch it could
    # replace, give or take margin_m. Where the line crosses itself, a cell
    # on both passes counts as the first.
    off_line = np.ones(cost.shape, dtype=bool)
    off_line[cells[:, 0], cells[:, 1]] = False
    _, (near_row, near_col) = distance_transform_edt(off_line, return_indices=True)
    along_grid = np.full(cost.shape, np.nan)
    along_grid[cells[::-1, 0], cells[::-1, 1]] = along[::-1]
    beside = along_grid[near_row, near_col]
    margin = float(params["margin_m"])

    # The stations each one may be joined to: up to max_skip_m on, and only
    # as far as no turning point is passed and no loop that starts inside
    # the stretch closes in it - for each b, the first place any station
    # from a to b-1 turns back.
    allowed: dict[int, np.ndarray] = {}
    for a in range(len(stations) - 1):
        b = np.arange(a + 1, min(int(ends[a]), int(next_turn[a]) + 1))
        if len(b):
            b = b[np.minimum.accumulate(turns_back[a:b[-1]]) > b]
        if len(b):
            b = b[heading[b] @ heading[a] >= min_cos]
        if len(b):
            allowed[a] = b

    # One graph per block of stations rather than one per station. Each
    # holds the ground beside the line from its first station to the
    # furthest any of them may be joined to. A block ends where the next
    # station starts, or may reach, more than BLOCK_M past the first's: so a
    # search reaches at most that far beyond its own stretch - and a block
    # never straddles a turn, where the stations before it may reach only
    # the turn and the ones after it kilometres down the way back.
    block_of = np.full(len(stations), -1)
    block_reach: list[tuple[float, float]] = []
    first_lo = first_hi = -np.inf
    for a, b in allowed.items():
        lo_m, hi_m = float(station_along[a]), float(station_along[b[-1]])
        if not block_reach or lo_m > first_lo + BLOCK_M or abs(hi_m - first_hi) > BLOCK_M:
            block_reach.append((lo_m, hi_m))
            first_lo, first_hi = lo_m, hi_m
        else:
            block_reach[-1] = (block_reach[-1][0], max(block_reach[-1][1], hi_m))
        block_of[a] = len(block_reach) - 1
    graphs: dict[int, tuple] = {}

    def graph_for(block: int) -> tuple:
        if block not in graphs:
            first_m, last_m = block_reach[block]
            mask = usable & (beside >= first_m - margin) & (beside <= last_m + margin)
            rows, cols = np.nonzero(mask)
            r0, c0 = int(rows.min()), int(cols.min())
            crop = (slice(r0, rows.max() + 1), slice(c0, cols.max() + 1))
            graph, node = _band_graph(cost[crop], mask[crop])
            node_rows, node_cols = np.nonzero(node >= 0)   # in node order
            graphs[block] = (graph, node, r0, c0, node_rows + r0, node_cols + c0)
        return graphs[block]

    def node_at(block: int, k: np.ndarray) -> np.ndarray:
        """The block graph's node for each of the line cells `k`, -1 off it."""
        _, node, r0, c0, _, _ = graph_for(block)
        r, c = cells[k, 0] - r0, cells[k, 1] - c0
        ok = (r >= 0) & (r < node.shape[0]) & (c >= 0) & (c < node.shape[1])
        out = np.full(len(k), -1)
        out[ok] = node[r[ok], c[ok]]
        return out

    # Every way that saves what a minor suggestion must, and which of them
    # also save what a full one must - the costs do not depend on the bar,
    # so the searches are done once for both.
    minor_params = {**params, **params["minor"]}
    candidates: dict[tuple[int, int], float] = {}
    major: set[tuple[int, int]] = set()
    for a, b in allowed.items():
        block = int(block_of[a])
        source = node_at(block, stations[[a]])[0]
        if source < 0:
            continue
        targets = node_at(block, stations[b])
        # Nothing dearer than the line's own way to the furthest station
        # can beat it to any of them, so the spread stops there.
        limit = station_spent[b[-1]] - station_spent[a]
        reached = dijkstra(graph_for(block)[0], directed=False, indices=source, limit=limit)
        found = np.where(targets >= 0, reached[np.maximum(targets, 0)], np.inf)
        line = station_spent[b] - station_spent[a]
        span = station_along[b] - station_along[a]
        good = (np.isfinite(found) & (apart_m(a, b) >= straightness * span)
                & (line - found >= np.minimum(_needed_saving(line, span, params),
                                              _needed_saving(line, span, minor_params))))
        clears = line - found >= _needed_saving(line, span, params)
        for j in np.flatnonzero(good):
            candidates[(a, int(b[j]))] = float(found[j])
            if clears[j]:
                major.add((a, int(b[j])))

    paths: dict[int, np.ndarray] = {}

    def path_of(a: int, b: int) -> np.ndarray:
        block = int(block_of[a])
        graph, _, _, _, node_rows, node_cols = graph_for(block)
        if a not in paths:
            _, paths[a] = dijkstra(graph, directed=False,
                                   indices=node_at(block, stations[[a]])[0],
                                   return_predecessors=True)
        walk, at = [], node_at(block, stations[[b]])[0]
        while at >= 0:
            walk.append(at)
            at = paths[a][at]
        walk.reverse()
        return np.column_stack([node_rows[walk], node_cols[walk]])

    min_join_cos = np.cos(np.radians(float(params["max_join_deg"])))

    def line_point(d: float) -> np.ndarray:
        return cells[min(int(np.searchsorted(along, d)), len(cells) - 1)].astype(np.float64)

    def joins_smoothly(path: np.ndarray, first: int, last: int) -> bool:
        """Leaves and rejoins the line heading its way - see max_join_deg.
        Each heading is over join_m, or half the way on a short one."""
        walked = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))]) * res
        join = min(float(params["join_m"]), walked[-1] / 2.0, (along[last] - along[first]) / 2.0)
        if join <= 0:
            return True
        leaving = path[int(np.searchsorted(walked, join))] - path[0]
        arriving = path[-1] - path[int(np.searchsorted(walked, walked[-1] - join, side="right")) - 1]
        line_out = line_point(along[first] + join) - cells[first]
        line_in = cells[last] - line_point(along[last] - join)
        for way, line in ((leaving, line_out), (arriving, line_in)):
            norms = np.hypot(*way) * np.hypot(*line)
            if norms > 0 and float(way @ line) / norms < min_join_cos:
                return False
        return True

    def fits(path: np.ndarray, first: int, last: int) -> bool:
        """Gets far enough from the line to be another way, is not so much
        longer than the stretch it replaces that it is another route, and
        joins the line going its way."""
        stretch = cells[first:last + 1]
        gaps = np.hypot(*(path[:, None, :] - stretch[None, :, :]).transpose(2, 0, 1))
        length = float(np.hypot(*np.diff(path, axis=0).T).sum()) * res
        return bool(gaps.min(axis=1).max() * res >= float(params["min_detour_m"])
                    and length <= float(params["max_lengthening"]) * (along[last] - along[first])
                    and joins_smoothly(path, first, last))

    def saving(a: int, b: int) -> float:
        return float(station_spent[b] - station_spent[a]) - candidates[(a, b)]

    def shorter(a: int, c: int, among: dict, p: dict) -> list[tuple[int, int]]:
        """(a, c), or the shorter suggestions it splits into. Kept whole only
        where it saves clearly more than the best two it could be split
        into - one long way round two separate fixes is two suggestions,
        each to take or leave; one long way that is much better than its
        parts is one."""
        whole, best, at = saving(a, c), 0.0, -1
        for b in range(a + 1, c):
            if (a, b) in among and (b, c) in among:
                parts = saving(a, b) + saving(b, c)
                if parts > best:
                    best, at = parts, b
        if at < 0 or whole > (1.0 + float(p["long_gain_share"])) * best:
            return [(a, c)]
        return shorter(a, at, among, p) + shorter(at, c, among, p)

    keep = np.diff(station_spent)

    def choose(among: dict[tuple[int, int], float], p: dict) -> list[dict]:
        """The best set of suggestions from `among`, each saving what `p`
        asks. Takes `among` over: what does not fit is dropped from it."""
        while True:
            chosen = [piece for a, c in _cheapest_whole(len(stations), keep, among)
                      for piece in shorter(a, c, among, p)]
            unfit = [(a, b) for a, b in chosen
                     if not fits(path_of(a, b), int(stations[a]), int(stations[b]))]
            if not unfit:
                break
            for pair in unfit:
                del among[pair]

        # A chosen way can come back to the line for a while between two
        # places it leaves it - two separate fixes, which the user should be
        # able to take one without the other. Split there, and keep the
        # pieces that are still worth suggesting on their own.
        found = []
        for a, b in chosen:
            for first, last, path in _off_line(path_of(a, b), cells, int(stations[a]),
                                               int(stations[b]), float(p["rejoin_m"]) / res):
                way = float(((cost[path[:-1, 0], path[:-1, 1]] + cost[path[1:, 0], path[1:, 1]])
                             / 2.0 * np.hypot(*np.diff(path, axis=0).T)).sum())
                line = float(spent[last] - spent[first])
                span = float(along[last] - along[first])
                if line - way >= _needed_saving(line, span, p) and fits(path, first, last):
                    found.append({"first": first, "last": last, "path": path,
                                  "cost": way, "line_cost": line, "minor": False})
        return found

    detours = choose({pair: candidates[pair] for pair in major}, params)

    # A line that is already good: fill up with the biggest smaller savings,
    # on stretches no full suggestion touches.
    wanted = int(params["min_suggestions"]) - len(detours)
    if wanted > 0:
        def clear_of_detours(a: int, b: int) -> bool:
            return all(stations[b] <= d["first"] or stations[a] >= d["last"] for d in detours)

        rest = {pair: found for pair, found in candidates.items() if clear_of_detours(*pair)}
        smaller = sorted(choose(rest, minor_params),
                         key=lambda d: d["line_cost"] - d["cost"], reverse=True)[:wanted]
        for d in smaller:
            d["minor"] = True
        detours = sorted(detours + smaller, key=lambda d: d["first"])
    return detours


def _needed_saving(line_cost, span_m, params: dict):
    """What a suggestion replacing `span_m` of line that costs `line_cost`
    must save to be worth showing: min_saving_share of it on a short
    stretch, rising by saving_share_per_km with every kilometre - a long way
    has to be clearly better to be worth taking over the line the user drew -
    and never under min_saving in cost. Works on arrays as well."""
    share = (float(params["min_saving_share"])
             + float(params["saving_share_per_km"]) * np.asarray(span_m) / 1000.0)
    return np.maximum(share * line_cost, float(params["min_saving"]))


def _off_line(path: np.ndarray, cells: np.ndarray, first: int, last: int,
              min_shared: float) -> list[tuple[int, int, np.ndarray]]:
    """The pieces of `path` that leave the line, as (first, last, path):
    where each leaves and rejoins it, as indices into `cells`, and its own
    cells, both ends on the line.

    `path` runs from cells[first] to cells[last]. Where it follows the line
    for at least `min_shared` steps, it is cut in two; a shorter stretch on
    the line is part of the piece around it. Only the line itself counts: a
    way a cell beside it is still drifting off or back, and cutting there
    trims a suggestion down to less than it saves.
    """
    where: dict[tuple[int, int], list[int]] = {}
    for k in range(first, last + 1):
        where.setdefault((int(cells[k, 0]), int(cells[k, 1])), []).append(k)

    # Each path cell that is on the line, and where along it - the first
    # place at or after the last one found, so a line that crosses itself
    # is read in its own order.
    on: list[Optional[int]] = []
    reached = first
    for r, c in path:
        later = [k for k in where.get((int(r), int(c)), []) if k >= reached]
        on.append(later[0] if later else None)
        if later:
            reached = later[0]

    touches = [i for i, k in enumerate(on) if k is not None]
    pieces: list[list[int]] = []   # [path index leaving, path index rejoining]
    for i, j in zip(touches[:-1], touches[1:]):
        follows = j == i + 1 and on[j] - on[i] <= 1
        if not follows:
            pieces.append([i, j])
    merged: list[list[int]] = []
    for piece in pieces:
        if merged and piece[0] - merged[-1][1] < min_shared:
            merged[-1][1] = piece[1]
        else:
            merged.append(piece)

    return [(on[i], on[j], path[i:j + 1]) for i, j in merged if on[j] > on[i]]


def _cheapest_whole(count: int, keep: np.ndarray,
                    candidates: dict[tuple[int, int], float]) -> list[tuple[int, int]]:
    """The candidates that make the cheapest line from the first station to
    the last, in order. `keep` is the line's own cost from each station to
    the next."""
    ending: dict[int, list[tuple[int, float]]] = {}
    for (a, b), found in candidates.items():
        ending.setdefault(b, []).append((a, found))

    best = np.full(count, np.inf)
    best[0] = 0.0
    came = np.full(count, -1)
    for b in range(1, count):
        best[b] = best[b - 1] + keep[b - 1]
        for a, found in ending.get(b, []):
            if best[a] + found < best[b]:
                best[b], came[b] = best[a] + found, a

    chosen, b = [], count - 1
    while b > 0:
        if came[b] < 0:
            b -= 1
        else:
            chosen.append((int(came[b]), b))
            b = int(came[b])
    return chosen[::-1]


def improve_line(line_xy: np.ndarray, *, cost_raster: str = COST_RASTER,
                 tag: str = "line") -> list[dict]:
    """The stretches of `line_xy` (EPSG:25833, in order) with a clearly
    cheaper way close beside them - see the note above _band_graph.

    Returns one dict per suggestion, in order along the line: start_m and
    end_m along it, where the suggestion leaves and rejoins it; xy, the new
    way between those two points of the line, smoothed as a routed line is;
    old_xy, the line's own stretch it replaces; cost and line_cost, the
    new way's and the old one's; and minor, for one that only fills up a
    line with few clear savings - see IMPROVE's min_suggestions.
    """
    import grass.script as gs
    from grass.script import array as garray

    xy = np.asarray(line_xy, dtype=np.float64)
    band = _line_band(xy, cost_raster=cost_raster, tag=tag)
    region = gs.region()
    res = region["ewres"]
    used = np.array(garray.array(mapname=band.used, null=-1, dtype=np.float64))
    cost = np.array(garray.array(mapname=cost_raster, null=-1, dtype=np.float64))
    gs.run_command("g.remove", type="raster", name=",".join(band.scratch),
                   flags="f", quiet=True)

    inside = (used >= 0) & (used <= 1) & (cost >= 0)
    detours = _detours(cost, inside, band.cells, band.along, band.on_line, res,
                       config.IMPROVE)

    vertex_along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])

    def at(d: float) -> np.ndarray:
        return np.array([np.interp(d, vertex_along, xy[:, 0]),
                         np.interp(d, vertex_along, xy[:, 1])])

    suggestions = []
    for detour in detours:
        start_m, end_m = float(band.along[detour["first"]]), float(band.along[detour["last"]])
        path = detour["path"]
        centres = np.column_stack([region["w"] + (path[:, 1] + 0.5) * res,
                                   region["n"] - (path[:, 0] + 0.5) * res])
        # From the line's own points, so it splices in exactly where it
        # leaves and rejoins - not from the centres of those two cells.
        way = _smoothed(np.vstack([at(start_m), centres[1:-1], at(end_m)]))
        inside_old = (vertex_along > start_m) & (vertex_along < end_m)
        suggestions.append({
            "start_m": start_m,
            "end_m": end_m,
            "xy": way,
            "old_xy": np.vstack([at(start_m), xy[inside_old], at(end_m)]),
            "cost": detour["cost"],
            "line_cost": detour["line_cost"],
            "minor": detour["minor"],
        })
    return suggestions


def _smoothed(xy: np.ndarray) -> np.ndarray:
    """Douglas-Peucker at the router's own threshold, ends kept, so a
    suggestion looks like a routed line and not a staircase of cells."""
    line = ogr.Geometry(ogr.wkbLineString)
    for x, y in xy:
        line.AddPoint_2D(float(x), float(y))
    simple = line.Simplify(float(config.ROUTING["smooth_threshold"]))
    return np.array(simple.GetPoints(), dtype=np.float64)[:, :2]


# --- comparing two sets of routes ---------------------------------------


SEPARATION_STEP_M = 50.0


def separation(a: ogr.Geometry, b: ogr.Geometry) -> tuple[float, float]:
    """Mean and worst distance from points along `a` to line `b`, in metres.

    One-directional and sampled, not a true Hausdorff distance. Enough to
    sort routes by how far they moved, which is all it is for.
    """
    length = a.Length()
    n = max(2, int(length / SEPARATION_STEP_M))
    d = [a.Value(length * i / n).Distance(b) for i in range(n + 1)]
    return float(np.mean(d)), float(np.max(d))


# --- batch --------------------------------------------------------------


def _open_routes(path: Path) -> tuple[ogr.DataSource, ogr.Layer]:
    """The routes GeoPackage, created with its schema if it is not there yet."""
    if path.exists():
        ds = ogr.Open(str(path), 1)
        return ds, ds.GetLayerByName(ROUTES_LAYER)

    path.parent.mkdir(parents=True, exist_ok=True)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    layer = ds.CreateLayer(ROUTES_LAYER, srs, ogr.wkbLineString)
    for name, kind in ROUTE_FIELDS:
        layer.CreateField(ogr.FieldDefn(name, kind))
    return ds, layer


def _done_fids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    ds = ogr.Open(str(path))
    layer = ds.GetLayerByName(ROUTES_LAYER)
    done = {feat.GetField("tour_fid") for feat in layer}
    ds = None
    return done


def _corridor_files(corridor_dir: Path, tour_fid: int) -> list[Path]:
    """Everything one tour's corridor left on disk, sidecars included.

    Matched on the numeric prefix rather than on `f"{fid:03d}_"`, so fid 58
    cannot claim fid 588's files, and a tour renamed since it was routed still
    finds the corridor it wrote under the old name. Its narrower and wider
    bands go with it, from their own folders.
    """
    out = []
    for directory in [corridor_dir, *_width_dirs(corridor_dir)]:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.tif*"):   # .tif, .tif.aux.xml, .tif.ovr
            match = re.match(r"^(\d+)_", path.name)
            if match and int(match.group(1)) == tour_fid:
                out.append(path)
    return out


def _width_dirs(corridor_dir: Path) -> list[Path]:
    """The width folders beside `corridor_dir`, by config.CORRIDOR_WIDTHS -
    not by globbing corridors_*, which would also match corridors_all.tif
    and any backup folder someone made by hand."""
    return [width_dir(corridor_dir, width) for width in config.CORRIDOR_WIDTHS]


def _corridor_fids(corridor_dir: Path) -> set[int]:
    """Tour ids that have a corridor raster on disk."""
    if not corridor_dir.is_dir():
        return set()
    out = set()
    for path in corridor_dir.glob("*.tif"):
        match = re.match(r"^(\d+)_", path.name)
        if match:
            out.add(int(match.group(1)))
    return out


def _clear_dir(directory: Path) -> None:
    """Empty `directory`, or leave it completely untouched.

    Deleting file by file is not atomic: hitting one that ArcGIS or QGIS has
    open throws partway through and leaves half a corridor directory beside a
    routes.gpkg that still lists every route as done. Renaming the directory
    first makes the whole thing one yes-or-no question, because Windows will
    not rename a directory that has an open file anywhere inside it.

    Probing the files individually does not work here: the lock these hold
    permits opening for write and still refuses deletion, so open() reports
    nothing wrong right up until unlink fails.
    """
    if not directory.is_dir():
        return
    staging = directory.with_name(directory.name + ".delete_me")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        directory.rename(staging)
    except OSError as exc:
        raise RuntimeError(
            f"Could not clear {directory} - a file inside it is open in "
            f"another process (usually QGIS or ArcGIS). Nothing has been "
            f"deleted; close it and re-run.\n  {exc}"
        ) from exc
    shutil.rmtree(staging)
    directory.mkdir(parents=True, exist_ok=True)


def prune_stale(tours: list[Tour], routes_path: Path, corridor_dir: Path) -> set[int]:
    """Drop routes that no longer match the tour file, corridors and all.

    Four ways a route goes stale, and resuming alone catches none of them:
    the tour was deleted, its endpoints moved, it was renamed, or its corridor
    is no longer on disk. `todo` only asks whether a fid has been routed
    before, so without this an edited tour keeps its old route forever.

    Deletion is the one that actively corrupts output rather than just going
    out of date - merge_corridors globs the whole directory, so an orphaned
    corridor keeps being folded into corridors_all.tif long after its tour is
    gone.

    The missing-corridor case is the same hazard mirrored: resume keys on
    routes.gpkg alone, so a route whose corridor has gone (an interrupted
    --force, a half-finished copy, a manual tidy-up) would be skipped as done
    and then quietly left out of the merge. Counting it as stale re-routes it.

    Returns the tour ids dropped. Any of them still in the tour file route
    again on this run, which is what makes a moved or renamed tour self-heal.
    """
    if not routes_path.exists():
        return set()

    current = {t.fid: t for t in tours}
    on_disk = {fid for fid in _corridor_fids(corridor_dir)}
    ds = ogr.Open(str(routes_path), 1)
    layer = ds.GetLayerByName(ROUTES_LAYER)

    reasons: dict[int, str] = {}
    doomed: list[int] = []
    for feat in layer:
        tour_fid = feat.GetField("tour_fid")
        tour = current.get(tour_fid)
        if tour is None:
            reason = "tour deleted"
        elif tour_fid not in on_disk:
            reason = "corridor missing"
        elif abs(float(feat.GetField("straight_m") or 0.0)
                 - tour.straight_km * 1000.0) > 0.5:
            # straight_m is written rounded to 0.1 m, so the tolerance is well
            # clear of rounding and still catches an endpoint nudged one pixel.
            reason = "endpoints moved"
        elif (feat.GetField("name") or "") != tour.name:
            reason = "renamed"
        else:
            continue
        reasons[tour_fid] = reason
        doomed.append(feat.GetFID())

    # Collected first: deleting from a layer that is still being iterated is
    # undefined for the GPKG driver.
    for fid in doomed:
        layer.DeleteFeature(fid)
    if doomed:
        ds.ExecuteSQL("VACUUM")
    ds = None

    files = 0
    for tour_fid in reasons:
        for path in _corridor_files(corridor_dir, tour_fid):
            path.unlink()
            files += 1

    if reasons:
        counts: dict[str, int] = {}
        for reason in reasons.values():
            counts[reason] = counts.get(reason, 0) + 1
        summary = ", ".join(f"{n} {reason}" for reason, n in sorted(counts.items()))
        print(f"Pruned {len(reasons)} stale route(s) and {files} corridor file(s): {summary}")
    return set(reasons)


def run_batch(
    tours: list[Tour],
    *,
    out_dir: Optional[Path] = None,
    buffer_m: Optional[float] = None,
    force: bool = False,
    merge: bool = True,
    prune: bool = True,
    surface: Optional[Path] = None,
    cost_raster: str = COST_RASTER,
    gap_dir: Optional[Path] = None,
    mapset: str = "PERMANENT",
) -> list[RouteResult]:
    """Route every tour, writing lines to routes.gpkg and corridors beside it.

    Resumable: a tour already in routes.gpkg is skipped unless `force`, so an
    interrupted batch of several hundred picks up where it stopped.

    `prune` first drops routes that no longer match the tour file - see
    prune_stale. It MUST be False whenever `tours` is a subset rather than the
    whole file, because every tour left out of the subset looks exactly like a
    deleted one; the CLI turns it off for --fid.

    Each tour's timings go to timings.csv beside routes.gpkg - see
    TIMING_FIELDS. `gap_dir` keeps every tour's raw gap raster there too.
    `mapset` - see start_session.
    """
    out_dir = out_dir or paths.ROUTES
    routes_path = out_dir / "routes.gpkg"
    corridor_dir = out_dir / "corridors"
    buffer_m = float(buffer_m if buffer_m is not None else config.ROUTING["region_buffer_m"])

    if force:
        # Corridors go too, not just the lines. A rename would otherwise
        # leave the old files sitting beside the new ones, with nothing to
        # say which run they came from.
        #
        # routes.gpkg goes first, and only if it really goes: the GPKG driver
        # reports a failed delete through its return code rather than by
        # raising, and a silently-kept routes.gpkg would make the whole run a
        # no-op that had still wiped every corridor.
        if routes_path.exists():
            ogr.GetDriverByName("GPKG").DeleteDataSource(str(routes_path))
            if routes_path.exists():
                raise RuntimeError(
                    f"Could not delete {routes_path} - it is most likely open "
                    "in QGIS or ArcGIS. Nothing has been changed; close it and "
                    "re-run."
                )
        _clear_dir(corridor_dir)
        for directory in _width_dirs(corridor_dir):
            _clear_dir(directory)
        (out_dir / TIMINGS).unlink(missing_ok=True)
    elif prune:
        # After --force there is nothing left to prune; before it, this is what
        # keeps routes.gpkg in step with a tour file that has been edited.
        prune_stale(tours, routes_path, corridor_dir)

    done = _done_fids(routes_path)
    todo = [t for t in tours if t.fid not in done]

    floor_m = float(config.ROUTING["region_buffer_floor_m"])
    print(f"{len(tours)} tours, {len(tours) - len(todo)} already routed, {len(todo)} to do")
    # Said rather than re-routed: a build from before the widths existed
    # would otherwise be routed again in full the first time it is resumed,
    # which is a day for the country and should be asked for with --force.
    for width in config.CORRIDOR_WIDTHS:
        have = _corridor_fids(width_dir(corridor_dir, width))
        lacking = len((done & {t.fid for t in tours}) - have)
        if lacking:
            print(f"  {lacking} routed tour(s) have no {width} corridor - "
                  f"--force to route them again with one")
    print(f"  buffer {floor_m:.0f}-{buffer_m:.0f} m, scaled to each tour's length -> {out_dir}")
    if not todo:
        if merge:
            merge_corridors(corridor_dir, out_dir / "corridors_all.tif")
        return []

    start_session(surface=surface, cost_raster=cost_raster, mapset=mapset)
    ds, layer = _open_routes(routes_path)
    results: list[RouteResult] = []
    started = time.time()

    for i, tour in enumerate(todo, 1):
        t0 = time.time()
        timings: dict = {}
        try:
            gap_path = (gap_dir / f"{tour.fid:03d}_{slug(tour.name)}.tif"
                        if gap_dir is not None else None)
            geometry, cost_opt, corridor = route_one(
                tour, corridor_dir, buffer_m=buffer_m, cost_raster=cost_raster,
                gap_path=gap_path, timings=timings)
            length = geometry.Length()
            _write_timings(out_dir / TIMINGS, tour, time.time() - t0, cost_opt, timings)

            feat = ogr.Feature(layer.GetLayerDefn())
            feat.SetField("tour_fid", tour.fid)
            feat.SetField("name", tour.name)
            feat.SetField("length_m", round(length, 1))
            feat.SetField("straight_m", round(tour.straight_km * 1000.0, 1))
            feat.SetField("detour", round(length / max(tour.straight_km * 1000.0, 1e-6), 3))
            feat.SetField("cost_opt", round(cost_opt, 1))
            feat.SetGeometry(geometry)
            layer.CreateFeature(feat)
            feat = None

            results.append(RouteResult(tour, length, cost_opt, time.time() - t0, corridor))
            status = f"{length / 1000:.2f} km  cost {cost_opt:,.0f}"
        except Exception as exc:  # noqa: BLE001 - reported, so one bad tour does not end the run
            results.append(RouteResult(tour, 0.0, 0.0, time.time() - t0, None,
                                       error=f"{type(exc).__name__}: {exc}"))
            status = f"FAILED  {type(exc).__name__}: {exc}"

        elapsed = time.time() - started
        print(f"[{i}/{len(todo)}] {tour.label:28s} {status}"
              f"   eta {elapsed / i * (len(todo) - i) / 60:.0f}m", flush=True)

    ds = None
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)} routed, {len(failed)} failed -> {routes_path}")
    for r in failed:
        print(f"  {r.tour.label}: {r.error}")

    if merge:
        merge_corridors(corridor_dir, out_dir / "corridors_all.tif")
    return results


TIMINGS = "timings.csv"
# Seconds per step of route_one, summed over every window it took. `spread`
# includes `negate`; `other` is region setup, point imports and clean-up.
TIMING_FIELDS = ("tour_fid", "engine", "seconds", "spread", "negate", "line",
                 "corridor", "other", "attempts", "cells", "cost_opt",
                 "walk_cost", "cost_check")


def _write_timings(path: Path, tour: Tour, seconds: float, cost_opt: float,
                   timings: dict) -> None:
    import csv

    steps = sum(timings.get(k, 0.0) for k in ("spread", "line", "corridor"))
    row = {"tour_fid": tour.fid, "engine": _engine(), "seconds": seconds,
           "other": seconds - steps, "cost_opt": cost_opt, **timings}
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TIMING_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({k: (round(v, 3) if isinstance(v, float) else v)
                         for k, v in row.items() if k in TIMING_FIELDS})


def merge_corridors(corridor_dir: Optional[Path] = None,
                    out_path: Optional[Path] = None,
                    *, files: Optional[Iterable[Path]] = None) -> Optional[Path]:
    """Every corridor combined into one raster, overlaps taking the maximum.

    `files` merges just those corridors instead of everything in
    `corridor_dir`, which is how skimap.exposure gets one raster per exposure
    class out of the same folder.

    A corridor is a 0..1 membership score, so MAX is the combination that
    keeps the scale meaning what it did: a cell reachable by two tours is as
    much "in a corridor" as its best one makes it. Summing would push
    popular ground above 1 and turn the scale into a count of tours.

    The union of the corridors spans most of the country while covering very
    little of it, so the file is written sparse: untouched blocks cost
    nothing on disk. That is also why the background is 0 rather than a
    nodata sentinel - a sparse block reads back as 0, and 0 is already what
    the outer edge of a corridor scores, so the two agree.
    """
    corridor_dir = corridor_dir or (paths.ROUTES / "corridors")
    out_path = out_path or (paths.ROUTES / "corridors_all.tif")
    files = sorted(files) if files is not None else sorted(corridor_dir.glob("*.tif"))
    if not files:
        print("No corridors to merge.")
        return None

    # All corridors come off the same region alignment, so their windows land
    # on one lattice and a merge is placement, never resampling.
    bounds, lattice = [], set()
    for f in files:
        ds = gdal.Open(str(f))
        gt = ds.GetGeoTransform()
        bounds.append((gt[0], gt[3] + ds.RasterYSize * gt[5],
                       gt[0] + ds.RasterXSize * gt[1], gt[3]))
        lattice.add((round(gt[0] % config.PIXEL_SIZE, 6), round(gt[3] % config.PIXEL_SIZE, 6)))
        ds = None
    if len(lattice) != 1:
        raise RuntimeError(f"Corridors sit on {len(lattice)} different lattices: {lattice}")

    minx = min(b[0] for b in bounds)
    miny = min(b[1] for b in bounds)
    maxx = max(b[2] for b in bounds)
    maxy = max(b[3] for b in bounds)
    width = int(round((maxx - minx) / config.PIXEL_SIZE))
    height = int(round((maxy - miny) / config.PIXEL_SIZE))

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dst = gdal.GetDriverByName("GTiff").Create(
        str(out_path), width, height, 1, gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3", "SPARSE_OK=TRUE",
                 "BIGTIFF=YES", "NUM_THREADS=ALL_CPUS"],
    )
    dst.SetGeoTransform((minx, config.PIXEL_SIZE, 0.0, maxy, 0.0, -config.PIXEL_SIZE))
    dst.SetProjection(srs.ExportToWkt())
    band = dst.GetRasterBand(1)
    band.SetNoDataValue(0.0)

    print(f"Merging {len(files)} corridors -> {out_path.name} "
          f"({width} x {height} px, {width * height / 1e9:.2f} Gpx sparse)")
    for f in files:
        ds = gdal.Open(str(f))
        gt = ds.GetGeoTransform()
        src = ds.GetRasterBand(1).ReadAsArray()
        nodata = ds.GetRasterBand(1).GetNoDataValue()
        ds = None
        if nodata is not None:
            src = np.where(src == nodata, 0.0, src)

        x = int(round((gt[0] - minx) / config.PIXEL_SIZE))
        y = int(round((maxy - gt[3]) / config.PIXEL_SIZE))
        existing = band.ReadAsArray(x, y, src.shape[1], src.shape[0])
        band.WriteArray(np.maximum(existing, src), x, y)

    band.FlushCache()
    dst.BuildOverviews("AVERAGE", [2, 4, 8, 16, 32, 64])
    dst = None
    print(f"  {out_path.stat().st_size / 1e6:.0f} MB")
    return out_path
