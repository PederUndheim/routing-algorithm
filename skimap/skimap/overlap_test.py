r"""skimap.overlap tried on the Isfjorden tours, routed through forest_1_2.

Run from the project directory:

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m skimap.overlap_test run

`run` is route -> score -> blend. Each is a stage of its own as well, so
trying other distances is `blend` alone - seconds, not a re-route:

    ... -m skimap.overlap_test blend --near 40 --far 120 --min-shared 300

Everything lands under data/test/overlap/isfjorden_forest_1_2/:

    routes.gpkg, corridors/       the tours routed through forest_1_2's surface
    stacked/corridors_<c>.tif     exposure.split_corridors, as it is today
    blended/corridors_<c>.tif     the fade, one disjoint raster per class
    compare.png                   the two side by side over a hillshade
    compare_tour<fid>.png         the same, cropped to each faded stretch
    variants/<label>/             blended/ and the pictures again, for a
                                  `blend --label <label>` run, so settings
                                  can be compared side by side

The pictures draw today's rasters with green on top and black at the bottom.
The blended rasters are disjoint, so their order does not matter.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from osgeo import gdal, osr

# paths reads no parameter, so it is safe before the variant's profile is in
# the environment. Everything that reads config is imported inside a stage.
from skimap import paths, track_variants

if TYPE_CHECKING:
    from skimap.overlap import Window

gdal.UseExceptions()

VARIANT = "forest_1_2"
TOURS_FILE = paths.TOURS_DIR / "isfjorden_tours.gpkg"
ROOT = paths.DATA / "test" / "overlap" / f"isfjorden_{VARIANT}"
ROUTES = ROOT / "routes.gpkg"
CORRIDORS = ROOT / "corridors"

PAD_M = 300.0
OPACITY = 0.8
CROP_PAD_M = 700.0
LINE_COLOURS = {"green": "#138a2c", "blue": "#1f4fd1", "red": "#d11f1f", "black": "#111111"}

# Drawn in this colour whatever it scored, so the fade can be tried against a
# harder class than this area happens to produce. Blend stage only - the
# stacked/ rasters from `score` keep the scored colours.
COLOUR_OVERRIDES = {2: "red"}


# --- stages -------------------------------------------------------------


def route(*, force: bool = False) -> bool:
    from skimap import routing, tours

    v = track_variants.Variant(VARIANT)
    track_variants._live(v)
    found = tours.read_tours(TOURS_FILE)
    results = routing.run_batch(
        found, out_dir=ROOT, force=force, merge=False,
        # A test directory holding only these tours: nothing to prune.
        prune=False,
        surface=track_variants.national_surface(v), cost_raster=v.cost_raster,
    )
    return not any(not r.ok for r in results)


def score() -> None:
    from skimap import exposure

    colours = exposure.score_routes(ROUTES)
    exposure.split_corridors(colours, CORRIDORS, ROOT / "stacked",
                             routes_path=ROUTES, stacked=True)


def blend(*, near_m: Optional[float] = None, far_m: Optional[float] = None,
          min_shared_m: Optional[float] = None,
          easier_priority: Optional[float] = None,
          priority_floor: Optional[float] = None,
          fade_in_m: Optional[float] = None, seam_m: Optional[float] = None,
          label: Optional[str] = None) -> None:
    from skimap import config, exposure, overlap

    out_root = ROOT if label is None else ROOT / "variants" / label

    lines = overlap.load_lines(ROUTES)
    for fid, colour in COLOUR_OVERRIDES.items():
        if fid in lines and lines[fid].colour != colour:
            print(f"tour {fid}: scored {lines[fid].colour}, drawn {colour} (COLOUR_OVERRIDES)")
            lines[fid].colour = colour
    files = {fid: p for fid, p in exposure.corridors_by_fid(CORRIDORS).items() if fid in lines}
    if not files:
        raise SystemExit(f"No scored routes with corridors under {ROOT}. Run 'route' and 'score'.")

    window = _window(files.values(), PAD_M)
    corridors = {fid: overlap.read(window, path) for fid, path in files.items()}
    lines = {fid: lines[fid] for fid in files}

    settings = {"near_m": near_m, "far_m": far_m, "min_shared_m": min_shared_m}
    settings = {k: float(config.OVERLAP[k] if v is None else v) for k, v in settings.items()}
    priority = float(config.OVERLAP["easier_priority"]
                     if easier_priority is None else easier_priority)
    floor = float(config.OVERLAP["priority_floor"] if priority_floor is None else priority_floor)
    fade_in = float(config.OVERLAP["fade_in_m"] if fade_in_m is None else fade_in_m)
    seam = float(config.OVERLAP["seam_m"] if seam_m is None else seam_m)
    line_weights = overlap.weights(lines, **settings, fade_in_m=fade_in)
    _report(lines, line_weights, _scores())

    severity, value = overlap.blend(corridors, lines, line_weights, window.centres(),
                                    easier_priority=priority, priority_floor=floor)
    before = overlap.stacked(corridors, lines)
    after = overlap.soft_classes(severity, value, pixel_m=window.pixel, seam_m=seam)

    out_dir = out_root / "blended"
    for colour, array in after.items():
        path = out_dir / f"corridors_{colour}.tif"
        if (array > 0).any():
            _write(window, array, path)
        elif path.exists():
            try:
                path.unlink()
            except OSError:
                print(f"  {path.name} is locked and now stale - no {colour} cells this run")

    shade = _hillshade(window)
    # Today's: most dangerous at the bottom, green drawn last.
    before_img = _paint(shade, [(c, before[c]) for c in reversed(overlap.CLASS_NAMES) if c in before])
    after_img = _paint(shade, [(c, after[c]) for c in overlap.CLASS_NAMES])
    after_title = (f"faded under easier tours  (near {settings['near_m']:g} m, "
                   f"far {settings['far_m']:g} m, min shared {settings['min_shared_m']:g} m, "
                   f"priority {priority:g} above {floor:g},\n"
                   f"fade-in {fade_in:g} m, seam {seam:g} m)")

    out_root.mkdir(parents=True, exist_ok=True)
    for old in out_root.glob("compare_tour*.png"):
        try:
            old.unlink()
        except OSError:
            pass    # locked in a viewer; _figure falls back to a _new name
    _figure(out_root / "compare.png", window, before_img, after_img, lines, line_weights,
            after_title=after_title)
    for fid, line in lines.items():
        faded = line_weights[fid] < 1.0
        if not faded.any():
            continue
        pts = line.points[faded]
        crop = (pts[:, 0].min() - CROP_PAD_M, pts[:, 1].min() - CROP_PAD_M,
                pts[:, 0].max() + CROP_PAD_M, pts[:, 1].max() + CROP_PAD_M)
        _figure(out_root / f"compare_tour{fid}.png", window, before_img, after_img, lines,
                line_weights, after_title=after_title, crop=crop)
    print(f"\npictures and rasters -> {out_root}")


def _scores() -> dict[int, tuple[float, float]]:
    """tour_fid -> (exp_score, exp_per_km), as `score` wrote them."""
    from osgeo import ogr

    from skimap import routing

    ds = ogr.Open(str(ROUTES))
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    out = {f.GetField("tour_fid"): (float(f.GetField("exp_score") or 0.0),
                                    float(f.GetField("exp_per_km") or 0.0)) for f in layer}
    ds = None
    return out


def _report(lines, line_weights, scores) -> None:
    print(f"\n{len(lines)} routes")
    for fid, line in sorted(lines.items()):
        w = line_weights[fid]
        length = float(line.station[-1])
        runs = _runs(w < 0.5, line.station)
        where = ", ".join(f"{a:.0f}-{b:.0f} m" for a, b in runs) or "-"
        score, per_km = scores.get(fid, (float("nan"), float("nan")))
        print(f"  tour {fid:>3}  {line.colour:<6} {length:>6.0f} m   exp_score {score:6.2f}"
              f" ({per_km:5.2f}/km)   faded along {sum(b - a for a, b in runs):>5.0f} m   {where}")


def _runs(mask: np.ndarray, station: np.ndarray) -> list[tuple[float, float]]:
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    return [(float(station[a]), float(station[b - 1])) for a, b in zip(edges[::2], edges[1::2])]


# --- the window ---------------------------------------------------------


def _window(files, pad_m: float) -> Window:
    """Every corridor's extent, padded. They share one lattice, so no snapping."""
    from skimap import config, overlap

    p = float(config.PIXEL_SIZE)
    boxes = [overlap.extent(path) for path in files]
    pad = round(pad_m / p) * p
    x0, y0 = min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad
    x1, y1 = max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad
    return overlap.Window(x0, y1, int(round((x1 - x0) / p)), int(round((y1 - y0) / p)), p)


def _write(window: Window, array: np.ndarray, path: Path) -> None:
    """Written beside `path` and moved into place. A raster open in ArcGIS or
    QGIS is locked; then the new one stays as .tmp.tif and the run goes on."""
    import os

    from skimap import config

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.tif")
    ds = gdal.GetDriverByName("GTiff").Create(
        str(tmp), window.width, window.height, 1, gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3"])
    ds.SetGeoTransform(window.geotransform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(0.0)
    band.WriteArray(array.astype(np.float32))
    ds = None
    try:
        os.replace(tmp, path)
    except OSError:
        print(f"  {path.name} is locked (open in a GIS?) - new raster left as {tmp.name}")
        return
    # Overviews and statistics a GIS built for the raster this replaced would
    # otherwise be drawn over the new one when zoomed out.
    for sidecar in (path.with_name(path.name + ".ovr"), path.with_name(path.name + ".aux.xml")):
        try:
            sidecar.unlink(missing_ok=True)
        except OSError:
            print(f"  could not remove stale {sidecar.name}")


# --- pictures -----------------------------------------------------------


def _hillshade(window: Window) -> np.ndarray:
    """A light hillshade of the window, 0..1. Plain grey if the DEM will not open."""
    from skimap import config

    try:
        warped = gdal.Warp("", str(paths.source("dem")), format="MEM",
                           outputBounds=window.bounds, width=window.width,
                           height=window.height, dstSRS=f"EPSG:{config.CRS_EPSG}",
                           resampleAlg="bilinear")
        shade = gdal.DEMProcessing("", warped, "hillshade", format="MEM",
                                   computeEdges=True, multiDirectional=True)
        arr = shade.GetRasterBand(1).ReadAsArray().astype(np.float64) / 255.0
    except Exception as error:  # noqa: BLE001 - a backdrop, not the result
        print(f"no hillshade ({error}); plain background")
        arr = np.full(window.shape, 0.7)
    return 0.45 + 0.55 * arr


def _paint(shade: np.ndarray, layers) -> np.ndarray:
    from skimap.corridor_review import render

    out = np.repeat(shade[..., None], 3, axis=2)
    for colour, values in layers:
        inside = values > 0.0
        if not inside.any():
            continue
        rgba = render._colorize(np.clip(values, 0.0, 1.0).astype(np.float64), inside, colour)
        rgba = rgba.astype(np.float64) / 255.0
        alpha = rgba[..., 3:4] * OPACITY
        out = out * (1.0 - alpha) + rgba[..., :3] * alpha
    return out


def _figure(png: Path, window: Window, before, after, lines, line_weights, *,
            after_title: str, crop=None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects

    x0, y0, x1, y1 = window.bounds
    fig, axes = plt.subplots(1, 2, figsize=(18, 9), sharex=True, sharey=True)
    halo = [patheffects.withStroke(linewidth=2.4, foreground="white")]
    for ax, image, title, show_fade in (
        (axes[0], before, "today: one raster per class, stacked", False),
        (axes[1], after, after_title, True),
    ):
        ax.imshow(image, extent=(x0, x1, y0, y1), interpolation="nearest")
        for fid, line in lines.items():
            colour = LINE_COLOURS.get(line.colour, "#000000")
            x, y = line.points[:, 0], line.points[:, 1]
            if show_fade:
                faded = line_weights[fid] < 0.5
                ax.plot(np.where(faded, np.nan, x), y, color=colour, lw=1.2, path_effects=halo)
                ax.plot(np.where(faded, x, np.nan), y, color=colour, lw=1.2, ls=(0, (2, 2)))
            else:
                ax.plot(x, y, color=colour, lw=1.2, path_effects=halo)
            ax.annotate(str(fid), (x[-1], y[-1]), fontsize=9, color=colour,
                        path_effects=halo, xytext=(4, 4), textcoords="offset points")
        ax.set_title(title, fontsize=11)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    if crop is not None:
        axes[0].set_xlim(max(crop[0], x0), min(crop[2], x1))
        axes[0].set_ylim(max(crop[1], y0), min(crop[3], y1))
    fig.tight_layout()
    try:
        fig.savefig(png, dpi=150)
    except OSError:
        fallback = png.with_name(png.stem + "_new.png")
        print(f"  {png.name} is locked (open in a viewer?) - saved as {fallback.name}")
        fig.savefig(fallback, dpi=150)
    plt.close(fig)


# --- cli ----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skimap.overlap_test",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("route", "run"):
        p = sub.add_parser(name)
        p.add_argument("--force", action="store_true", help="re-route everything")
    sub.add_parser("score")
    for name in ("blend", "run"):
        p = sub.choices[name] if name in sub.choices else sub.add_parser(name)
        p.add_argument("--near", type=float)
        p.add_argument("--far", type=float)
        p.add_argument("--min-shared", type=float)
        p.add_argument("--priority", type=float,
                       help="how many times stronger a harder band must be to take a cell")
        p.add_argument("--floor", type=float,
                       help="easier membership below this gets no priority")
        p.add_argument("--fade-in", type=float,
                       help="metres of route a harder tour comes in over past a shared stretch")
        p.add_argument("--seam", type=float, help="width of the cross-fade between colours, m")
        p.add_argument("--label", help="write to variants/<label>/ instead of over the default")
    args = parser.parse_args(argv)

    # Before anything reads config - see track_variants.
    v = track_variants._activate(VARIANT)
    track_variants._live(v)

    if args.stage in ("route", "run") and not route(force=args.force):
        print("some tours failed to route")
        if args.stage == "route":
            return 1
    if args.stage in ("score", "run"):
        score()
    if args.stage in ("blend", "run"):
        blend(near_m=args.near, far_m=args.far, min_shared_m=args.min_shared,
              easier_priority=args.priority, priority_floor=args.floor,
              fade_in_m=args.fade_in, seam_m=args.seam, label=args.label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
