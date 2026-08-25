"""Least-cost routes and corridors through the national cost surface.

One route is four GRASS steps:

    r.walk        cumulative walking cost from the start, plus a direction
                  raster recording which neighbour each cell came from
    r.cost        symmetric cumulative cost from each end, for the corridor
    r.path        follow the direction raster back from the end to get the line
    v.generalize  Douglas-Peucker, so the line is not a staircase of pixels

r.walk is anisotropic - it costs uphill and downhill differently - which is
what makes it right for ski touring and why it needs the DEM as well as the
surface. r.cost is symmetric, and the corridor needs that: `start->x` plus
`end->x` is only a meaningful total when the two halves are measured the same
way, which an anisotropic spread does not give you.

Both rasters are linked with r.external rather than imported, so the 1.65 GB
surface is read in place, and the region is set per route to the pair's
bounding box plus a buffer - otherwise every spread would cover 19 Gpx.
"""

from __future__ import annotations

import os
import re
import sys
import time
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
    corridors: dict[str, Path]
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


def check_lattice() -> None:
    """Refuse to route if the surface and the DEM are not co-registered.

    r.walk reads the two as one grid, so half a pixel of offset between them
    silently pairs each elevation with a neighbouring cell's friction. It is
    invisible in either raster alone, hence the check up front.
    """
    offsets = {}
    for label, path in (("cost surface", paths.national_surface()), ("DEM", paths.source("dem"))):
        ds = gdal.Open(str(path))
        gt = ds.GetGeoTransform()
        offsets[label] = (gt[0] % config.PIXEL_SIZE, gt[3] % config.PIXEL_SIZE)
        ds = None

    if len(set(offsets.values())) != 1:
        detail = ", ".join(f"{k} {v}" for k, v in offsets.items())
        raise RuntimeError(
            f"Cost surface and DEM are on different lattices ({detail}). "
            "r.walk would pair each elevation with a neighbouring cell's friction. "
            "Rebuild the surface with the current skimap.raster."
        )


LINK_MARKERS = "link_markers"


def _ensure_linked(name: str, source: Path, grassdata: Path) -> None:
    """Link `source` as external raster `name`, unless it's already linked
    to this exact file.

    Plain `r.external` reads through the whole source once to compute its
    data range - harmless for a one-off, but start_session() used to redo it
    on every batch, and for the 16 GB national DEM that alone was ~145s of
    dead time before the first route started (measured). `-r` skips the scan
    entirely; safe here because r.walk/r.cost/r.path read friction and
    elevation per cell, and nothing in this codebase reads nat_cost/nat_dem's
    range (no r.info/r.colors on them) - only re-add it if something later
    does. The marker file is what makes a relink a no-op on the next run:
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


def start_session(grassdata: Optional[Path] = None):
    """Start GRASS and link the national rasters in place."""
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
    check_lattice()

    _ensure_linked(COST_RASTER, paths.national_surface(), grassdata)
    _ensure_linked(DEM_RASTER, paths.source("dem"), grassdata)
    return session


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


def route_one(tour: Tour, corridor_dir: Path, *, buffer_m: float,
              modes: Optional[Iterable[str]] = None) -> tuple[ogr.Geometry, float, dict[str, Path]]:
    """Route one tour and write its corridors.

    `buffer_m` is a ceiling, not a fixed value - see `_region_buffer`.

    Returns the smoothed line, the symmetric optimal cost, and the corridor
    file written per mode.
    """
    import grass.script as gs

    modes = list(modes) if modes else [config.DEFAULT_CORRIDOR_MODE]
    tag = f"{tour.fid}_{slug(tour.name)}"
    start_pt, end_pt = f"start_{tag}", f"end_{tag}"
    direction, walk_cost = f"dir_{tag}", f"walk_{tag}"
    from_start, from_end = f"symstart_{tag}", f"symend_{tag}"
    gap, gap_pos = f"gap_{tag}", f"gappos_{tag}"
    line, smooth = f"line_{tag}", f"smooth_{tag}"
    scratch = [direction, walk_cost, from_start, from_end, gap, gap_pos]

    memory = int(config.ROUTING["grass_memory_mb"])

    # The region is the pair's bounding box plus a buffer, snapped to the cost
    # surface. A route that runs to the edge of it was clipped by the window
    # rather than by the terrain, so the ceiling is worth raising if that shows.
    region_buffer_m = _region_buffer(tour, buffer_m)
    xs, ys = (tour.start[0], tour.end[0]), (tour.start[1], tour.end[1])
    gs.run_command("g.region", raster=COST_RASTER, align=COST_RASTER,
                   w=min(xs) - region_buffer_m, e=max(xs) + region_buffer_m,
                   s=min(ys) - region_buffer_m, n=max(ys) + region_buffer_m)

    _import_point(start_pt, tour.start)
    _import_point(end_pt, tour.end)

    # The direction raster is the point of this call - it records the way back
    # to the start from every cell, and r.path walks it to build the line.
    gs.run_command("r.walk", elevation=DEM_RASTER, friction=COST_RASTER,
                   start_points=start_pt, output=walk_cost, outdir=direction,
                   lambda_=float(config.ROUTING["lambda"]), memory=memory,
                   overwrite=True, quiet=True)

    # Symmetric spreads from both ends: their sum at a cell is the cost of the
    # best route through that cell, which is what makes a corridor definable.
    for point, out in ((start_pt, from_start), (end_pt, from_end)):
        gs.run_command("r.cost", input=COST_RASTER, start_points=point,
                       output=out, memory=memory, overwrite=True, quiet=True)

    cost_opt = _value_at(from_start, end_pt)

    # How much worse than optimal a route through each cell would be. Clamped
    # at zero because floating point puts the cells on the optimal line a
    # hair below it.
    gs.mapcalc(f"{gap} = ({from_start} + {from_end}) - {cost_opt}", overwrite=True, quiet=True)
    gs.mapcalc(
        f"{gap_pos} = if(isnull({from_start}) || isnull({from_end}), null(), "
        f"if({gap} < 0, 0, {gap}))",
        overwrite=True, quiet=True,
    )

    gs.run_command("r.path", input=direction, format="auto", start_points=end_pt,
                   vector_path=line, overwrite=True, quiet=True)
    gs.run_command("v.generalize", input=line, output=smooth, method="douglas",
                   threshold=float(config.ROUTING["smooth_threshold"]),
                   overwrite=True, quiet=True)
    geometry = _route_geometry(smooth)

    corridor_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for mode in modes:
        params = config.CORRIDOR_MODES[mode]
        max_gap = cost_opt * float(params["slack"])
        scored = f"score_{tag}_{mode}"
        scratch.append(scored)
        # 1 on the optimal line, falling to 0 at the edge of the slack band,
        # then raised to gamma to control how fast it falls away.
        gs.mapcalc(
            f"{scored} = float(pow(if({gap_pos} <= {max_gap}, "
            f"1 - ({gap_pos} / {max_gap}), null()), {params['gamma']}))",
            overwrite=True, quiet=True,
        )
        # The mode is only in the name when there is more than one to tell
        # apart, so the usual single-corridor run reads as one file per tour.
        stem = f"{tour.fid:03d}_{slug(tour.name)}"
        out_path = corridor_dir / (f"{stem}_{mode}.tif" if len(modes) > 1 else f"{stem}.tif")
        gs.run_command("r.out.gdal", input=scored, output=str(out_path),
                       format="GTiff", type="Float32", nodata=config.NODATA,
                       createopt="COMPRESS=DEFLATE,PREDICTOR=3,TILED=YES",
                       flags="c", overwrite=True, quiet=True)
        written[mode] = out_path

    # Each route leaves a dozen full-region rasters behind. Over a few hundred
    # tours that is tens of GB in the mapset, for maps nothing reads again.
    gs.run_command("g.remove", type="raster", name=",".join(scratch),
                   flags="f", quiet=True)
    gs.run_command("g.remove", type="vector", name=",".join([start_pt, end_pt, line, smooth]),
                   flags="f", quiet=True)
    return geometry, cost_opt, written


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
    """Everything one tour's corridor left on disk, sidecars and modes included.

    Matched on the numeric prefix rather than on `f"{fid:03d}_"`, so fid 58
    cannot claim fid 588's files, and a tour renamed since it was routed still
    finds the corridor it wrote under the old name.
    """
    if not corridor_dir.is_dir():
        return []
    out = []
    for path in corridor_dir.glob("*.tif*"):   # .tif, .tif.aux.xml, .tif.ovr
        match = re.match(r"^(\d+)_", path.name)
        if match and int(match.group(1)) == tour_fid:
            out.append(path)
    return out


def prune_stale(tours: list[Tour], routes_path: Path, corridor_dir: Path) -> set[int]:
    """Drop routes that no longer match the tour file, corridors and all.

    Three ways a route goes stale, and resuming alone catches none of them:
    the tour was deleted, its endpoints moved, or it was renamed. `todo` only
    asks whether a fid has been routed before, so without this an edited tour
    keeps its old route forever.

    Deletion is the one that actively corrupts output rather than just going
    out of date - merge_corridors globs the whole directory, so an orphaned
    corridor keeps being folded into corridors_all.tif long after its tour is
    gone.

    Returns the tour ids dropped. Any of them still in the tour file route
    again on this run, which is what makes a moved or renamed tour self-heal.
    """
    if not routes_path.exists():
        return set()

    current = {t.fid: t for t in tours}
    ds = ogr.Open(str(routes_path), 1)
    layer = ds.GetLayerByName(ROUTES_LAYER)

    reasons: dict[int, str] = {}
    doomed: list[int] = []
    for feat in layer:
        tour_fid = feat.GetField("tour_fid")
        tour = current.get(tour_fid)
        if tour is None:
            reason = "tour deleted"
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
    modes: Optional[Iterable[str]] = None,
    force: bool = False,
    merge: bool = True,
    prune: bool = True,
) -> list[RouteResult]:
    """Route every tour, writing lines to routes.gpkg and corridors beside it.

    Resumable: a tour already in routes.gpkg is skipped unless `force`, so an
    interrupted batch of several hundred picks up where it stopped.

    `prune` first drops routes that no longer match the tour file - see
    prune_stale. It MUST be False whenever `tours` is a subset rather than the
    whole file, because every tour left out of the subset looks exactly like a
    deleted one; the CLI turns it off for --fid.
    """
    out_dir = out_dir or paths.ROUTES
    routes_path = out_dir / "routes.gpkg"
    corridor_dir = out_dir / "corridors"
    buffer_m = float(buffer_m if buffer_m is not None else config.ROUTING["region_buffer_m"])

    if force:
        # Corridors go too, not just the lines. A rename or a change of mode
        # would otherwise leave the old files sitting beside the new ones,
        # with nothing to say which run they came from.
        if routes_path.exists():
            ogr.GetDriverByName("GPKG").DeleteDataSource(str(routes_path))
        for stale in corridor_dir.glob("*.tif"):
            stale.unlink()
    elif prune:
        # After --force there is nothing left to prune; before it, this is what
        # keeps routes.gpkg in step with a tour file that has been edited.
        prune_stale(tours, routes_path, corridor_dir)

    done = _done_fids(routes_path)
    todo = [t for t in tours if t.fid not in done]

    floor_m = float(config.ROUTING["region_buffer_floor_m"])
    print(f"{len(tours)} tours, {len(tours) - len(todo)} already routed, {len(todo)} to do")
    print(f"  buffer {floor_m:.0f}-{buffer_m:.0f} m, scaled to each tour's length -> {out_dir}")
    if not todo:
        if merge:
            merge_corridors(corridor_dir, out_dir / "corridors_all.tif")
        return []

    start_session()
    ds, layer = _open_routes(routes_path)
    results: list[RouteResult] = []
    started = time.time()

    for i, tour in enumerate(todo, 1):
        t0 = time.time()
        try:
            geometry, cost_opt, corridors = route_one(
                tour, corridor_dir, buffer_m=buffer_m, modes=modes)
            length = geometry.Length()

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

            results.append(RouteResult(tour, length, cost_opt, time.time() - t0, corridors))
            status = f"{length / 1000:.2f} km  cost {cost_opt:,.0f}"
        except Exception as exc:  # noqa: BLE001 - reported, so one bad tour does not end the run
            results.append(RouteResult(tour, 0.0, 0.0, time.time() - t0, {},
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
