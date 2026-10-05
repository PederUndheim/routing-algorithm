r"""Routing through a machine-learned cost surface, on six Isfjorden tours.

Somebody else's model predicts, per 10 m cell, the probability that a skier is
there. This routes tours 1034-1039 through that instead of the national
surface, and colours the corridors the way production does - scored against
PRA and runout, overlaps faded (skimap.overlap) - so the two can be looked at
side by side. Run from the project directory:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.ml_cost_test run --cost log

`run` is surface -> tours -> route -> score -> picture. Each is a stage of its
own too; `route` is resumable and `--force` re-routes. `--cost` picks how
probability becomes cost (see COST_FUNCTIONS), default linear.

Everything lands under data/test/ml_cost_surface/:

    kirketaket_prediction_probability_med_3epoch.tif   the model's output, as delivered
    tours.gpkg                the six tours, starts moved onto the surface
    <cost>/                   one per cost function, side by side:
        cost_surface.tif          the probability as cost
        routes.gpkg, corridors/   routed through it
        colored_corridors/        corridors_<class>.tif, as exposure writes nationally
        compare.png               the surface with these routes and production's,
                                  beside the coloured corridors

## Probability as cost

    linear   cost = 100 - 99 * p / 0.99, clamped to [1, 100]
    log      cost = -ln(p + LOG_EPSILON) + LOG_FLOOR

Nodata stays nodata under both, which the router treats as impassable.

`linear` is the plain reading of "0 is 100, 0.99 is 1". Its range is the
national surface's (config.MIN_COST .. BASE_MAX_COST), but not its level:
median probability is 0.34, so the median cell costs 66 and the cheapest route
still averages 20-30 per 10 m where production's averages under 2. So cost_opt
is 10-30x production's, and the corridors are narrow - config.CORRIDOR caps the
band at max_gap = 300 cost units above optimal, a few cells of this.

`log` sums -ln(p) along the route, which is -ln of the product: the router
finds the jointly most probable path, cells taken as independent. LOG_EPSILON
sits inside the log because p = 0 occurs and -ln(0) is infinite; at 1e-5 a
zero-probability cell costs 11.5. LOG_FLOOR sits outside, and is a charge per
cell for distance alone. It matters here in a way it does not for `linear`:
p = 0.99 costs 0.01, so a detour across high-probability ground is nearly
free, and nothing else stops a route wandering to find it. At 1e-5 it is
effectively off; raise it (0.05-0.1) if the routes take the long way round.

The scale of either is irrelevant to where the route goes - multiplying every
cell by a constant changes no argmin - but not to the corridor, whose max_gap
ceiling is in absolute cost. On `log` a 4 km route costs a few hundred, so the
slack term (20% of cost_opt) governs the band, as it does in production.

## The surface is a strip

About 14.7 x 4 km. Everything outside it is nodata to the router, so a route
cannot leave it even where production's would - compare.png draws both.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from osgeo import gdal, ogr

from skimap import config, paths

gdal.UseExceptions()
ogr.UseExceptions()

ROOT = paths.DATA / "test" / "ml_cost_surface"
PROBABILITY = ROOT / "kirketaket_prediction_probability_med_3epoch.tif"
TOURS_FILE = ROOT / "tours.gpkg"

FIDS = tuple(range(1034, 1040))

LINEAR_AT_ZERO = 100.0
LINEAR_AT_TOP = 1.0
LINEAR_TOP_PROBABILITY = 0.99

LOG_EPSILON = 1e-5
LOG_FLOOR = 1e-5

PAD_M = 500.0
LINE_COLOURS = {"green": "#138a2c", "blue": "#1f4fd1", "red": "#d11f1f", "black": "#111111"}


# --- probability -> cost ------------------------------------------------


def linear_cost(p: np.ndarray) -> np.ndarray:
    cost = LINEAR_AT_ZERO - (LINEAR_AT_ZERO - LINEAR_AT_TOP) * (p / LINEAR_TOP_PROBABILITY)
    return np.clip(cost, LINEAR_AT_TOP, LINEAR_AT_ZERO)


def log_cost(p: np.ndarray) -> np.ndarray:
    # Clipped at 0 from below: p is at most 0.995 here, but a probability of
    # exactly 1 would otherwise give -1e-5 + 1e-5 minus rounding, and r.cost
    # refuses negative cost.
    return np.maximum(-np.log(np.clip(p, 0.0, 1.0) + LOG_EPSILON) + LOG_FLOOR, 0.0)


COST_FUNCTIONS: dict[str, tuple[Callable[[np.ndarray], np.ndarray], str]] = {
    "linear": (linear_cost, "cost = 100 - 99 p / 0.99, clamped to [1, 100]"),
    "log": (log_cost, f"cost = -ln(p + {LOG_EPSILON:g}) + {LOG_FLOOR:g}"),
}


@dataclass(frozen=True)
class Setup:
    """Where one cost function's surface and results live."""

    name: str

    @property
    def to_cost(self) -> Callable[[np.ndarray], np.ndarray]:
        return COST_FUNCTIONS[self.name][0]

    @property
    def formula(self) -> str:
        return COST_FUNCTIONS[self.name][1]

    @property
    def root(self) -> Path:
        return ROOT / self.name

    @property
    def cost(self) -> Path:
        return self.root / "cost_surface.tif"

    @property
    def routes(self) -> Path:
        return self.root / "routes.gpkg"

    @property
    def corridors(self) -> Path:
        return self.root / "corridors"

    @property
    def coloured(self) -> Path:
        return self.root / "colored_corridors"

    @property
    def grass_name(self) -> str:
        # Its own GRASS name per function, so each sits in the mapset beside
        # nat_cost and the variants' surfaces instead of replacing one.
        return f"ml_kirketaket_{self.name}"


# --- stages -------------------------------------------------------------


def surface(setup: Setup, *, force: bool = False) -> Path:
    """cost_surface.tif from the probability raster, on the same grid.

    Rebuilt when the probability raster or this file is newer, so editing a
    cost function is enough - the router relinks it because its mtime changed.
    """
    newest_input = max(PROBABILITY.stat().st_mtime, Path(__file__).stat().st_mtime)
    if setup.cost.exists() and not force and setup.cost.stat().st_mtime >= newest_input:
        print(f"{setup.name}/{setup.cost.name} is up to date")
        return setup.cost

    src = gdal.Open(str(PROBABILITY))
    band = src.GetRasterBand(1)
    p = band.ReadAsArray().astype(np.float64)
    hole = _holes(band, p)

    cost = setup.to_cost(np.where(hole, 0.0, p)).astype(np.float32)
    cost[hole] = config.NODATA

    setup.root.mkdir(parents=True, exist_ok=True)
    tmp = setup.cost.with_suffix(".tmp.tif")
    out = gdal.GetDriverByName("GTiff").Create(
        str(tmp), src.RasterXSize, src.RasterYSize, 1, gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"])
    out.SetGeoTransform(src.GetGeoTransform())
    out.SetProjection(src.GetProjection())
    out_band = out.GetRasterBand(1)
    out_band.SetNoDataValue(config.NODATA)
    out_band.WriteArray(cost)
    out = src = None
    tmp.replace(setup.cost)

    valid = cost[~hole]
    print(f"{PROBABILITY.name} -> {setup.name}/{setup.cost.name}   ({setup.formula})")
    print(f"  {valid.size} cells, {hole.sum()} nodata; cost min {valid.min():.3g}, "
          f"p10 {np.quantile(valid, 0.1):.3g}, median {np.median(valid):.3g}, "
          f"p90 {np.quantile(valid, 0.9):.3g}, max {valid.max():.3g}")
    return setup.cost


def _holes(band, values: np.ndarray) -> np.ndarray:
    nodata = band.GetNoDataValue()
    hole = ~np.isfinite(values)
    if nodata is not None:
        hole |= values == nodata
    return hole


def build_tours() -> list:
    """tours.gpkg: FIDS from the national tour file, each endpoint that falls
    off the surface moved due north to the centre of the first valid cell.

    Shared by every cost function: where the surface has data does not depend
    on how it is priced. Written with the national fids, so a route here and
    production's route of the same tour share a tour_fid. Rebuilt every time:
    it is derived, and re-running after a change to tours.gpkg is what should
    pick that up.
    """
    from skimap import tours as tours_module

    found = {t.fid: t for t in tours_module.read_tours(paths.TOURS) if t.fid in FIDS}
    missing = sorted(set(FIDS) - set(found))
    if missing:
        raise SystemExit(f"No tour with fid {missing} in {paths.TOURS}")

    ds = gdal.Open(str(PROBABILITY))
    band = ds.GetRasterBand(1)
    valid = ~_holes(band, band.ReadAsArray().astype(np.float64))
    gt = ds.GetGeoTransform()
    ds = None

    tours_module.create_template(TOURS_FILE, overwrite=True)
    out = ogr.Open(str(TOURS_FILE), 1)
    layer = out.GetLayerByName(tours_module.LAYER)
    for fid in FIDS:
        tour = found[fid]
        start = _onto_surface(tour.start, valid, gt)
        end = _onto_surface(tour.end, valid, gt)
        for role, before, after in (("start", tour.start, start), ("end", tour.end, end)):
            if after != before:
                print(f"  tour {fid} {role}: moved {after[1] - before[1]:.0f} m north "
                      f"({before[0]:.0f}, {before[1]:.0f}) -> ({after[0]:.0f}, {after[1]:.0f})")
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetFID(fid)
        feature.SetField("name", tour.name)
        line = ogr.Geometry(ogr.wkbLineString)
        line.AddPoint_2D(*start)
        line.AddPoint_2D(*end)
        feature.SetGeometry(line)
        layer.CreateFeature(feature)
    out = None
    print(f"{len(FIDS)} tours -> {TOURS_FILE}")
    return tours_module.read_tours(TOURS_FILE)


def _onto_surface(xy: tuple[float, float], valid: np.ndarray, gt) -> tuple[float, float]:
    """`xy` if it is on a valid cell; otherwise straight north to the first one.

    x is kept exactly - only y changes - so the trailhead moves along the line
    it would be walked on, and lands at the centre of the cell it enters.
    """
    col = int(np.floor((xy[0] - gt[0]) / gt[1]))
    row = int(np.floor((xy[1] - gt[3]) / gt[5]))
    rows, cols = valid.shape
    if not 0 <= col < cols:
        raise SystemExit(f"({xy[0]:.0f}, {xy[1]:.0f}) is east or west of the surface - "
                         f"moving north cannot bring it on")
    if 0 <= row < rows and valid[row, col]:
        return xy
    candidates = np.flatnonzero(valid[:min(row, rows - 1) + 1, col]) if row >= 0 else []
    if len(candidates) == 0:
        raise SystemExit(f"({xy[0]:.0f}, {xy[1]:.0f}) has no surface due north of it")
    first = int(candidates.max())
    return xy[0], gt[3] + (first + 0.5) * gt[5]


def route(setup: Setup, tours, *, force: bool = False) -> bool:
    from skimap import routing

    results = routing.run_batch(
        tours, out_dir=setup.root, force=force, merge=False,
        # tours.gpkg here is the whole tour set of this test, so pruning is
        # safe - and it is what re-routes a tour whose start was moved again.
        prune=True,
        surface=setup.cost, cost_raster=setup.grass_name,
    )
    return not any(not r.ok for r in results)


def score(setup: Setup) -> None:
    """Exposure on each route, then the corridors coloured with overlaps faded."""
    from skimap import exposure

    colours = exposure.score_routes(setup.routes)
    exposure.split_corridors(colours, setup.corridors, setup.coloured,
                             routes_path=setup.routes)
    _report(setup)


def _report(setup: Setup) -> None:
    """These routes against production's routes of the same tours, and against
    every other cost function's that has been run."""
    from skimap import routing

    ours = _routes(setup.routes)
    others = {"production": _routes(paths.ROUTES / "routes.gpkg")}
    for name in COST_FUNCTIONS:
        if name != setup.name and Setup(name).routes.exists():
            others[name] = _routes(Setup(name).routes)

    corridor_cells = _corridor_cells(setup)
    print(f"\n{setup.name}: {setup.formula}")
    print(f"  {'fid':>5} {'length m':>9} {'cost_opt':>10} {'exp':>6} {'colour':6} {'corridor ha':>11}"
          + "".join(f" | {name:>10} sep mean/max" for name in others))
    for fid in FIDS:
        if fid not in ours:
            print(f"  {fid:>5} not routed")
            continue
        a = ours[fid]
        line = (f"  {fid:>5} {a['length_m']:>9.0f} {a['cost_opt']:>10.1f} "
                f"{a['exp_score']:>6.1f} {a['colour'] or '-':6} "
                f"{corridor_cells.get(fid, 0) / 100:>11.1f}")
        for name, routes_ in others.items():
            b = routes_.get(fid)
            if b is None:
                line += f" | {'-':>23}"
                continue
            mean, worst = routing.separation(a["geometry"], b["geometry"])
            line += f" | {b['colour'] or '-':>6} {mean:>6.0f} / {worst:>6.0f} m"
        print(line)
    print("  production's routes start at the original trailhead, ~90 m further south")


def _corridor_cells(setup: Setup) -> dict[int, int]:
    """tour_fid -> cells its corridor covers, before any overlap fading."""
    from skimap import exposure

    out = {}
    for fid, path in exposure.corridors_by_fid(setup.corridors).items():
        ds = gdal.Open(str(path))
        band = ds.GetRasterBand(1)
        values = band.ReadAsArray()
        nodata = band.GetNoDataValue()
        inside = values > 0.0 if nodata is None else (values != nodata) & (values > 0.0)
        out[fid] = int(inside.sum())
        ds = None
    return out


def _routes(path: Path) -> dict[int, dict]:
    from skimap import routing

    out: dict[int, dict] = {}
    if not path.exists():
        return out
    ds = ogr.Open(str(path))
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    have = {layer.GetLayerDefn().GetFieldDefn(i).GetName()
            for i in range(layer.GetLayerDefn().GetFieldCount())}
    for feature in layer:
        fid = feature.GetField("tour_fid")
        if fid not in FIDS:
            continue
        out[fid] = {
            "geometry": feature.GetGeometryRef().Clone(),
            "length_m": float(feature.GetField("length_m") or 0.0),
            "cost_opt": float(feature.GetField("cost_opt") or 0.0),
            "exp_score": float(feature.GetField("exp_score") or 0.0) if "exp_score" in have else 0.0,
            "colour": feature.GetField("colour") if "colour" in have else None,
        }
    ds = None
    return out


# --- picture ------------------------------------------------------------


def picture(setup: Setup) -> Path:
    """compare.png: the probability surface with both sets of routes, beside
    the coloured corridors over a hillshade."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects

    from skimap import overlap
    from skimap.overlap_test import _hillshade, _paint

    x0, y0, x1, y1 = overlap.extent(PROBABILITY)
    p = float(config.PIXEL_SIZE)
    pad = round(PAD_M / p) * p
    window = overlap.Window(x0 - pad, y1 + pad, int(round((x1 - x0 + 2 * pad) / p)),
                            int(round((y1 - y0 + 2 * pad) / p)), p)
    wx0, wy0, wx1, wy1 = window.bounds

    ds = gdal.Open(str(PROBABILITY))
    probability = overlap.read(window, PROBABILITY)
    band = ds.GetRasterBand(1)
    inside_src = ~_holes(band, band.ReadAsArray().astype(np.float64))
    ds = None
    inside = np.zeros(window.shape, dtype=bool)
    r0, c0 = int(round(pad / p)), int(round(pad / p))
    inside[r0:r0 + inside_src.shape[0], c0:c0 + inside_src.shape[1]] = inside_src

    shade = _hillshade(window)
    classes = [(c, overlap.read(window, setup.coloured / f"corridors_{c}.tif"))
               for c in overlap.CLASS_NAMES if (setup.coloured / f"corridors_{c}.tif").exists()]
    coloured = _paint(shade, classes)

    ours, theirs = _routes(setup.routes), _routes(paths.ROUTES / "routes.gpkg")
    halo = [patheffects.withStroke(linewidth=2.4, foreground="white")]
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True, sharey=True)

    axes[0].imshow(shade, extent=(wx0, wx1, wy0, wy1), cmap="gray", vmin=0, vmax=1)
    im = axes[0].imshow(np.where(inside, probability, np.nan), extent=(wx0, wx1, wy0, wy1),
                        cmap="viridis", vmin=0.0, vmax=1.0, alpha=0.75, interpolation="nearest")
    fig.colorbar(im, ax=axes[0], fraction=0.02, pad=0.01, label="probability of a skier")
    axes[0].set_title(f"ML probability surface, {setup.name} cost ({setup.formula}) - "
                      f"these routes (white), production's (orange, dashed)")
    axes[1].imshow(coloured, extent=(wx0, wx1, wy0, wy1), interpolation="nearest")
    axes[1].set_title("corridors through it, coloured by exposure, overlaps faded")

    for fid, route_ in ours.items():
        xy = np.asarray(route_["geometry"].GetPoints())[:, :2]
        # r.path walks from the end back to the start, so the first vertex is
        # the summit. The trailhead is shared by all six - no room for labels.
        axes[0].plot(xy[:, 0], xy[:, 1], color="white", lw=1.4)
        axes[0].annotate(str(fid), xy[0], fontsize=9, color="white",
                         xytext=(4, 4), textcoords="offset points")
        colour = LINE_COLOURS.get(route_["colour"] or "", "#000000")
        axes[1].plot(xy[:, 0], xy[:, 1], color=colour, lw=1.2, path_effects=halo)
        axes[1].annotate(str(fid), xy[0], fontsize=9, color=colour, path_effects=halo,
                         xytext=(4, 4), textcoords="offset points")
    for route_ in theirs.values():
        xy = np.asarray(route_["geometry"].GetPoints())[:, :2]
        axes[0].plot(xy[:, 0], xy[:, 1], color="#ff8c1a", lw=1.2, ls=(0, (4, 2)))

    for ax in axes:
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color="black", lw=0.8, ls=":")
        ax.set_xlim(wx0, wx1)
        ax.set_ylim(wy0, wy1)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()

    png = setup.root / "compare.png"
    try:
        fig.savefig(png, dpi=150)
    except OSError:
        png = png.with_name("compare_new.png")
        print(f"  compare.png is locked (open in a viewer?) - saved as {png.name}")
        fig.savefig(png, dpi=150)
    plt.close(fig)
    print(f"picture -> {png}")
    return png


# --- cli ----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skimap.ml_cost_test",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="stage", required=True)

    def add(name: str, help_: str, *, force_help: Optional[str] = None, cost: bool = True):
        p = sub.add_parser(name, help=help_)
        if cost:
            p.add_argument("--cost", choices=sorted(COST_FUNCTIONS), default="linear",
                           help="how probability becomes cost (default linear)")
        if force_help:
            p.add_argument("--force", action="store_true", help=force_help)
        return p

    add("surface", "probability -> <cost>/cost_surface.tif", force_help="rebuild it")
    add("tours", "tours.gpkg, starts moved onto the surface", cost=False)
    add("route", "route the tours through <cost>/cost_surface.tif", force_help="re-route everything")
    add("score", "exposure, then corridors coloured with overlaps faded")
    add("picture", "<cost>/compare.png")
    add("run", "surface, tours, route, score, picture",
        force_help="rebuild the surface and re-route")
    args = parser.parse_args(argv)

    force = getattr(args, "force", False)
    setup = Setup(args.cost) if hasattr(args, "cost") else None
    if args.stage in ("surface", "run"):
        surface(setup, force=force)
    if args.stage in ("tours", "run"):
        build_tours()
    if args.stage in ("route", "run"):
        from skimap import tours as tours_module
        if not TOURS_FILE.exists():
            raise SystemExit(f"No {TOURS_FILE.name} yet - run the 'tours' stage.")
        if not setup.cost.exists():
            raise SystemExit(f"No {setup.name}/{setup.cost.name} yet - run the 'surface' stage.")
        if not route(setup, tours_module.read_tours(TOURS_FILE), force=force):
            print("some tours failed to route")
            return 1
    if args.stage in ("score", "run"):
        score(setup)
    if args.stage in ("picture", "run"):
        picture(setup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
