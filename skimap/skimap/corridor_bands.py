r"""Corridor bands cut from the standard one, without routing again.

A corridor cell holds (1 - gap / G) ** gamma, where gap is how much dearer
than optimal a route through it is and G the band's budget (routing.route_one,
_max_gap). Float32, so the gap comes back out exactly:

    gap = G * (1 - w ** (1 / gamma))

and any NARROWER band is that gap read against a smaller budget. Wider ones
cannot be: past the standard band's edge the gap was never written.

This is how config.REVIEW_CORRIDOR_WIDTHS get onto disk - routing does not
write them - and `check` proves the method on a band routing DID write:

    python -m skimap.corridor_bands check  data/test/track_variants/max2 --width narrow
    python -m skimap.corridor_bands derive data/test/track_variants/max2 --width very_narrow

A model directory is the one holding routes.gpkg, corridors/ and, where it
has one, timings.csv. cost_opt comes from routes.gpkg; the engine from
timings.csv, because under r.walk the budget's cap is scaled (config.WALK).

`derive` rewrites a band only where the standard corridor is newer than it,
and deletes bands whose standard corridor is gone - so after a re-route, run
it again and the review width follows the routes.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, ogr

from skimap import config, exposure, routing

gdal.UseExceptions()
ogr.UseExceptions()

CREATE = ["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"]


def band_params(width: Optional[str]) -> dict:
    """The full parameter set of a band: standard, a routing width or a
    review-only one."""
    if width in (None, "standard"):
        return dict(config.CORRIDOR)
    extra = {**config.CORRIDOR_WIDTHS, **config.REVIEW_CORRIDOR_WIDTHS}
    if width not in extra:
        raise SystemExit(f"no corridor width {width!r}; known: {sorted(extra)}")
    return {**config.CORRIDOR, **extra[width]}


def budget(cost_opt: float, params: dict, engine: str) -> float:
    """routing._max_gap, with the engine passed rather than read from config."""
    cap = float(params["max_gap"])
    if engine == "walk":
        cap *= float(config.WALK["max_gap_scale"])
    return min(cost_opt * float(params["slack"]), cap)


def _costs(model_dir: Path) -> dict[int, float]:
    datasource = ogr.Open(str(model_dir / "routes.gpkg"))
    layer = datasource.GetLayerByName(routing.ROUTES_LAYER)
    costs = {int(f.GetField("tour_fid")): float(f.GetField("cost_opt") or 0.0)
             for f in layer}
    datasource = None
    return costs


def _engines(model_dir: Path) -> dict[int, str]:
    """Per tour, from timings.csv. Missing means production's r.cost."""
    path = model_dir / routing.TIMINGS
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {int(row["tour_fid"]): row.get("engine") or "cost"
                for row in csv.DictReader(handle)}


def cut(standard: Path, cost_opt: float, engine: str, width: str) -> tuple[np.ndarray, gdal.Dataset]:
    """The `width` band of one corridor, as an array with NODATA outside."""
    source = gdal.Open(str(standard))
    w = source.GetRasterBand(1).ReadAsArray().astype(np.float64)
    nodata = source.GetRasterBand(1).GetNoDataValue()
    inside = np.isfinite(w) & (w >= 0) & (w != nodata)

    std = band_params(None)
    dst = band_params(width)
    g_std = budget(cost_opt, std, engine)
    g_dst = budget(cost_opt, dst, engine)
    if g_dst > g_std:
        raise ValueError(f"{width} is wider than standard here - it cannot be cut from it")

    gap = np.full(w.shape, np.inf)
    gap[inside] = g_std * (1.0 - np.power(w[inside], 1.0 / float(std["gamma"])))
    keep = gap <= g_dst
    out = np.full(w.shape, float(config.NODATA), dtype=np.float32)
    out[keep] = np.power(1.0 - gap[keep] / g_dst, float(dst["gamma"]))
    return out, source


def _write(out: np.ndarray, like: gdal.Dataset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.tif")
    driver = gdal.GetDriverByName("GTiff")
    target = driver.Create(str(tmp), like.RasterXSize, like.RasterYSize, 1,
                           gdal.GDT_Float32, CREATE)
    target.SetGeoTransform(like.GetGeoTransform())
    target.SetProjection(like.GetProjection())
    band = target.GetRasterBand(1)
    band.SetNoDataValue(float(config.NODATA))
    band.WriteArray(out)
    band.FlushCache()
    target = None
    tmp.replace(path)


def _jobs(model_dir: Path):
    costs, engines = _costs(model_dir), _engines(model_dir)
    for fid, standard in sorted(exposure.corridors_by_fid(model_dir / "corridors").items()):
        if fid not in costs:
            print(f"  {fid}: corridor but no route in routes.gpkg - skipped")
            continue
        yield fid, standard, costs[fid], engines.get(fid, "cost")


def derive(model_dir: Path, width: str, *, force: bool = False) -> int:
    model_dir = Path(model_dir)
    folder = routing.width_dir(model_dir / "corridors", width)
    written = kept = 0
    wanted = set()
    for fid, standard, cost_opt, engine in _jobs(model_dir):
        target = folder / standard.name
        wanted.add(target.name)
        if (not force and target.is_file()
                and target.stat().st_mtime >= standard.stat().st_mtime):
            kept += 1
            continue
        out, like = cut(standard, cost_opt, engine, width)
        _write(out, like, target)
        written += 1
    gone = 0
    if folder.is_dir():
        for stale in folder.glob("*.tif"):
            if stale.name not in wanted:
                stale.unlink()
                gone += 1
    print(f"{model_dir.name}: {written} written, {kept} up to date, "
          f"{gone} orphans removed -> {folder}")
    return written


def check(model_dir: Path, width: str) -> bool:
    """Cut `width` from standard and compare with the band routing wrote."""
    model_dir = Path(model_dir)
    folder = routing.width_dir(model_dir / "corridors", width)
    tours = flipped = cells = 0
    worst = 0.0
    for fid, standard, cost_opt, engine in _jobs(model_dir):
        written = folder / standard.name
        if not written.is_file():
            continue
        out, _ = cut(standard, cost_opt, engine, width)
        # The dataset held in a name: chained, it is collected before the
        # band is read, and GDAL hands back a dangling band.
        dataset = gdal.Open(str(written))
        truth = dataset.GetRasterBand(1).ReadAsArray()
        dataset = None
        a, b = out != config.NODATA, truth != config.NODATA
        flipped += int((a != b).sum())
        cells += int(b.sum())
        both = a & b
        if both.any():
            worst = max(worst, float(np.abs(out[both] - truth[both]).max()))
        tours += 1
    print(f"{model_dir.name} {width}: {tours} tours, {cells} cells in the band; "
          f"{flipped} cells in one and not the other "
          f"({flipped / max(cells, 1):.4%}), worst value difference {worst:.2e}")
    return tours > 0 and flipped / max(cells, 1) < 1e-3 and worst < 1e-3


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skimap.corridor_bands",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, text in (("derive", "write a band cut from the standard one"),
                       ("check", "cut a band routing also wrote, and compare")):
        p = sub.add_parser(name, help=text)
        p.add_argument("models", nargs="+", type=Path, help="model directories")
        p.add_argument("--width", required=True)
        if name == "derive":
            p.add_argument("--force", action="store_true", help="rewrite up-to-date bands too")
    args = parser.parse_args(argv)

    if args.cmd == "check":
        ok = all([check(m, args.width) for m in args.models])
        print("MATCH" if ok else "DIFFERENT")
        return 0 if ok else 1
    for model in args.models:
        derive(model, args.width, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
