"""Avalanche exposure along the routed lines, and corridors grouped by it.

A stage of its own, deliberately, run after `route`: routing is the hours,
scoring is the seconds, and a changed weight or class break must not mean
re-walking the cost surface. The only thing written back into
data/routing_output is the score on each line; the four class rasters land
in data/colored_corridors and nothing else goes there.

The score is NVE's ExpScore. Walk the line at a fixed spacing and, at every
sample, add two terms:

    release   pra / 100, rescaled into [rr, 1]
    runout    exp(-(lambda * d)^alpha), where d is the metres to the nearest
              release area in the Flow-Py runout simulation

then sum each over the line and add them, the runout total scaled by `rr`.
That `rr` is the whole reason the two are addable - see accident_ratio().

It is a dose, not a rate. Twice the distance through the same terrain is
twice the score, which is the intent: exposure is something you accumulate
by being there. config.EXPOSURE_CLASSES is therefore in absolute score, and
exp_per_km is written alongside so the length term stays visible in the
attribute table rather than having to be inferred from it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, ogr

from skimap import config, paths, routing

gdal.UseExceptions()
ogr.UseExceptions()

# Added to routes.gpkg in place. The two components are kept beside the total
# because they answer different questions - a route can reach the same score
# by crossing a few start zones or by spending a long time under a big face,
# and those are not the same trip.
EXPOSURE_FIELDS = (
    ("exp_release", ogr.OFTReal),   # release-area term, summed along the line
    ("exp_runout", ogr.OFTReal),    # runout term, already scaled by rr
    ("exp_score", ogr.OFTReal),     # the two added: what colour classifies on
    ("exp_per_km", ogr.OFTReal),    # exp_score / length, since score is a dose
    ("colour", ogr.OFTString),      # green | blue | red | black
)


def accident_ratio() -> float:
    """What one unit of runout exposure is worth against one of release.

    Accidents attributed to each kind of ground, over the share of trip time
    spent in it. Runout ground is where most of a day is spent and few
    accidents happen; release ground is the reverse. The ratio comes out near
    0.073, so a metre in a start zone carries about fourteen metres' worth of
    runout exposure - which is what makes the two terms addable at all.
    """
    e = config.EXPOSURE
    return ((e["accident_runout"] / e["trip_runout"])
            / (e["accident_release"] / e["trip_release"]))


# --- sampling ------------------------------------------------------------


def sample_points(geometry: ogr.Geometry, spacing_m: float) -> np.ndarray:
    """Points every `spacing_m` along the line, plus the far end.

    Evenly spaced rather than at the line's own vertices, because the sum is
    a dose: each sample has to stand for the same length of route. r.path
    writes a vertex per cell and v.generalize then thins the straights and
    keeps the bends, so vertex positions carry the smoothing's opinion about
    curvature - summing over them would quietly weight corners double.
    """
    xy = np.asarray(geometry.GetPoints(), dtype=np.float64)[:, :2]
    return sample_stations(xy, spacing_m)[1]


def sample_stations(xy: np.ndarray, spacing_m: float) -> tuple[np.ndarray, np.ndarray]:
    """sample_points for a line given as an (n, 2) array, with each sample's
    distance along the line as well: (distances, points)."""
    if len(xy) < 2:
        return np.zeros(len(xy)), xy

    step = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
    along = np.concatenate([[0.0], np.cumsum(step)])
    total = float(along[-1])
    if total <= 0.0:
        return np.zeros(1), xy[:1]

    wanted = np.append(np.arange(0.0, total, spacing_m), total)
    return wanted, np.column_stack([np.interp(wanted, along, xy[:, 0]),
                                    np.interp(wanted, along, xy[:, 1])])


def sample_raster(path: Path, xy: np.ndarray, *, nodata_as: float = np.nan) -> np.ndarray:
    """Raster value under each point; NaN off the raster, `nodata_as` on nodata.

    NaN for both by default. Pass a value where the raster's nodata is an
    answer rather than a hole - the runout raster's 10000 is "beyond reach",
    which is something known about that ground.

    One window read covering the route rather than a 1x1 read per point: a
    few hundred routes at several hundred samples each is ~400k reads, and on
    a 600 MB tiled raster every one of them is a block lookup. The window is
    the route's own bounding box - 600 x 600 cells for a 6 km line, which is
    nothing to hold.
    """
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    inverse = gdal.InvGeoTransform(ds.GetGeoTransform())

    px = np.floor(inverse[0] + inverse[1] * xy[:, 0] + inverse[2] * xy[:, 1]).astype(np.int64)
    py = np.floor(inverse[3] + inverse[4] * xy[:, 0] + inverse[5] * xy[:, 1]).astype(np.int64)

    out = np.full(len(xy), np.nan)
    on = (px >= 0) & (py >= 0) & (px < ds.RasterXSize) & (py < ds.RasterYSize)
    if on.any():
        x0, x1 = int(px[on].min()), int(px[on].max())
        y0, y1 = int(py[on].min()), int(py[on].max())
        window = band.ReadAsArray(x0, y0, x1 - x0 + 1, y1 - y0 + 1).astype(np.float64)
        out[on] = window[py[on] - y0, px[on] - x0]
    ds = None

    if nodata is not None:
        out[out == nodata] = nodata_as
    return out


# --- the two terms -------------------------------------------------------


def release_term(pra_percent: np.ndarray) -> np.ndarray:
    """Release-area exposure per sample, from PRA percent.

    The national PRA is integer percent 1..99 - not the 0..1 fraction the
    thesis pipeline used - so it is divided down here. Rescaling the result
    into [rr, 1] rather than [0, 1] is what stops a 1% release area scoring
    as nothing: standing in a mapped start zone at all is already worth more
    than the runout ground around it.
    """
    fraction = pra_percent / 100.0
    scored = accident_ratio() + (1.0 - accident_ratio()) * fraction
    return np.where(np.isnan(fraction) | (fraction <= 0.0), 0.0, scored)


def runout_term(distance_m: np.ndarray) -> np.ndarray:
    """Runout exposure per sample, from metres to the nearest release area.

    Two cases score zero. Off the raster is the obvious one. The other is
    d == 0, which marks ground that IS a release area rather than ground an
    avalanche runs out into: the curve puts those at 1.0, its maximum, but
    release exposure is exactly what the other term measures, and letting
    both fire would double every metre of start zone.
    """
    lam = float(config.EXPOSURE["weibull_lambda"])
    alpha = float(config.EXPOSURE["weibull_alpha"])
    with np.errstate(invalid="ignore"):
        scored = np.exp(-((lam * distance_m) ** alpha))
    return np.where(np.isnan(distance_m) | (distance_m <= 0.0), 0.0, scored)


def classify(score: float) -> str:
    """The colour for a score, per config.EXPOSURE_CLASSES."""
    colour = config.EXPOSURE_CLASSES[0][1]
    for lower, name in config.EXPOSURE_CLASSES:
        if score >= lower:
            colour = name
    return colour


def score_line(geometry: ogr.Geometry, pra: Path, runout: Path) -> tuple[float, float, float]:
    """One route's (release, runout, total) exposure."""
    xy = sample_points(geometry, float(config.EXPOSURE["sample_spacing_m"]))
    release = float(release_term(sample_raster(pra, xy)).sum())
    run = float(runout_term(sample_raster(runout, xy)).sum()) * accident_ratio()
    return release, run, release + run


# --- scoring the routes --------------------------------------------------


def _ensure_fields(layer: ogr.Layer) -> None:
    """Add the exposure fields if this layer has not been scored before."""
    defn = layer.GetLayerDefn()
    have = {defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())}
    for name, kind in EXPOSURE_FIELDS:
        if name in have:
            continue
        field = ogr.FieldDefn(name, kind)
        if kind == ogr.OFTString:
            field.SetWidth(16)
        layer.CreateField(field)


def score_routes(routes_path: Optional[Path] = None) -> dict[int, str]:
    """Score every line in routes.gpkg in place. Returns tour_fid -> colour."""
    routes_path = Path(routes_path) if routes_path else (paths.ROUTES / "routes.gpkg")
    if not routes_path.exists():
        raise FileNotFoundError(
            f"No routes at {routes_path}. Run 'python -m skimap.cli route' first."
        )
    pra, runout = paths.source("pra"), paths.source("runout")

    ds = ogr.Open(str(routes_path), 1)
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    if layer is None:
        raise KeyError(f"No layer {routing.ROUTES_LAYER!r} in {routes_path}")
    _ensure_fields(layer)

    # Geometries first, edits after: writing to a layer that is still being
    # iterated is undefined for the GPKG driver.
    lines: list[tuple[int, int, float, ogr.Geometry]] = []
    for feat in layer:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        lines.append((feat.GetFID(), feat.GetField("tour_fid"),
                      float(feat.GetField("length_m") or 0.0), geom.Clone()))

    print(f"Scoring {len(lines)} routes against {pra.name} and {runout.name}")
    colours: dict[int, str] = {}
    layer.StartTransaction()
    for n, (fid, tour_fid, length_m, geom) in enumerate(lines, 1):
        release, run, total = score_line(geom, pra, runout)
        colour = classify(total)
        colours[tour_fid] = colour

        feat = layer.GetFeature(fid)
        feat.SetField("exp_release", round(release, 2))
        feat.SetField("exp_runout", round(run, 2))
        feat.SetField("exp_score", round(total, 2))
        feat.SetField("exp_per_km", round(total / max(length_m / 1000.0, 1e-6), 2))
        feat.SetField("colour", colour)
        layer.SetFeature(feat)
        feat = None

        if n % 100 == 0 or n == len(lines):
            print(f"  {n}/{len(lines)}", flush=True)
    layer.CommitTransaction()
    ds = None

    counts = defaultdict(int)
    for colour in colours.values():
        counts[colour] += 1
    print(f"\nScores written to {routes_path}")
    for lower, colour in config.EXPOSURE_CLASSES:
        print(f"  {colour:6s} >= {lower:6.0f}   {counts[colour]:4d} routes")
    return colours


# --- corridors, grouped by colour ----------------------------------------


def corridors_by_fid(corridor_dir: Path) -> dict[int, Path]:
    """tour_fid -> its corridor, read off the `<fid>_<slug>.tif` naming.

    Keyed on the fid prefix rather than rebuilt from the tour name, so a tour
    renamed since it was routed still finds the corridor it produced.
    """
    found: dict[int, Path] = {}
    for path in sorted(corridor_dir.glob("*.tif")):
        match = re.match(r"^(\d+)_", path.name)
        if match:
            found[int(match.group(1))] = path
    return found


def split_corridors(colours: dict[int, str],
                    corridor_dir: Optional[Path] = None,
                    out_dir: Optional[Path] = None, *,
                    routes_path: Optional[Path] = None,
                    stacked: bool = False) -> dict[str, Path]:
    """One corridor raster per exposure class, and nothing else.

    Where corridors of different classes overlap, skimap.overlap draws the
    shared ground once, in the easiest class that goes there, and cross-fades
    where the colours meet - see config.OVERLAP. That needs the lines as well
    as the corridors, hence `routes_path`. `stacked` writes the old output
    instead: each class merged on its own, overlaps drawn in both.

    The output directory holds exactly the four class rasters. The per-route
    corridors and corridors_all.tif stay where `route` wrote them, in
    routing_output/ - they are the routing stage's output, not this one's,
    and duplicating them here doubles a few GB to no end.

    The cost is that these four files are only interpretable against the
    routes that produced them: re-route without re-scoring and the colours
    describe routes that no longer exist. Re-run `exposure` after `route`.
    """
    corridor_dir = Path(corridor_dir) if corridor_dir else (paths.ROUTES / "corridors")
    out_dir = Path(out_dir) if out_dir else paths.COLORED_CORRIDORS
    out_dir.mkdir(parents=True, exist_ok=True)

    available = corridors_by_fid(corridor_dir)
    missing = sorted(set(colours) - set(available))
    if missing:
        print(f"\n{len(missing)} scored routes have no corridor on disk: {missing[:10]}"
              f"{' ...' if len(missing) > 10 else ''}")

    if not stacked:
        from skimap import overlap   # imported here: overlap imports this module

        routes_path = Path(routes_path) if routes_path else (paths.ROUTES / "routes.gpkg")
        lines = overlap.load_lines(routes_path, colours=colours)
        files = {fid: available[fid] for fid in colours if fid in available}
        return overlap.write_classes(lines, files, out_dir)

    grouped: dict[str, list[Path]] = defaultdict(list)
    for tour_fid, colour in colours.items():
        if tour_fid in available:
            grouped[colour].append(available[tour_fid])

    written: dict[str, Path] = {}
    for _, colour in config.EXPOSURE_CLASSES:
        files = grouped.get(colour, [])
        if not files:
            print(f"\nNo {colour} routes - nothing to merge.")
            continue
        out_path = out_dir / f"corridors_{colour}.tif"
        print(f"\n{colour}: {len(files)} corridors")
        routing.merge_corridors(out_path=out_path, files=files)
        written[colour] = out_path
    return written


def run(routes_path: Optional[Path] = None,
        corridor_dir: Optional[Path] = None,
        out_dir: Optional[Path] = None, *,
        stacked: bool = False) -> dict[str, Path]:
    """Score the routes, then split their corridors by the class that gives."""
    colours = score_routes(routes_path)
    return split_corridors(colours, corridor_dir, out_dir,
                           routes_path=routes_path, stacked=stacked)
