r"""What spreading steep ground (config.STEEP_SPREAD) did to the routes.

Not a unit test - the lab experiment's scorecard. The lab itself answers "how
far did each line move"; this answers "moved to where": off steep ground, or
just away from it, and at what price.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    $py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
    & $py -m tests.steep_spread_report pick --count 15     # tours worth testing
    & $py -m skimap.lab run steep_spread_control --jobs 8
    & $py -m skimap.lab run steep_spread_square1 --jobs 8 --against steep_spread_control
    ...
    & $py -m tests.steep_spread_report compare             # the scorecard

Every measure but `ctl_cost` reads the national rasters, never a lab surface,
so a variant cannot score well by having redrawn the thing it is scored on:

  steep_m       route metres on a cell >= 30 deg - on the ORIGINAL slope
  near10_m      metres within one cell (10 m) of such a cell, not on one
  near20_m      metres within two cells (20 m), not on one
  exp_per_km    exposure per km, from PRA and runout (skimap.exposure)
  ctl_cost      the line's cost on the CONTROL surface - what the detour
                costs in today's terms. A rise is the price of the change.

Writes data/test/lab/steep_spread_report.csv, one row per tour and profile.

    & $py -m tests.steep_spread_report arcgis

puts everything in data/test/lab/steep_spread_arcgis/ as files ArcGIS reads -
the lab's own surfaces are VRTs, which it does not:

  cost_<profile>.tif        the cost surface each profile routed on, + .lyrx
                            in the production symbology
  spread_added_<variant>    what the spread added: variant minus control,
                            in cost units, nodata where it added nothing
  steep_ge30.tif            the cells that spread - slope >= 30 deg
  corridors_<profile>.tif   every tour's corridor, overlaps MAXed, + .lyrx
  routes.gpkg               every profile's routes in one layer, field
                            `profile`, with the scorecard columns per line

Rasters span the whole tour set, which is two regions 1000 km apart, so they
are sparse GeoTIFFs: blocks with no tile in them are never written.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, ogr

from skimap import config, exposure, paths, routing

gdal.UseExceptions()

LAB = paths.DATA / "test" / "lab"
CONTROL = "steep_spread_control"
VARIANTS = ("steep_spread_disk1", "steep_spread_square1",
            "steep_spread_half1", "steep_spread_square2")
STEP_M = 2.0          # samples along the line; a fifth of a cell
STEEP_DEG = 30.0


# --- sampling --------------------------------------------------------------


def _window(path: Path, xy: np.ndarray, pad_px: int):
    """The raster under the points' bbox plus pad_px, and each point's cell
    in it. Off-raster is NaN."""
    ds = gdal.Open(str(path))
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    col = np.floor((xy[:, 0] - gt[0]) / gt[1]).astype(int)
    row = np.floor((xy[:, 1] - gt[3]) / gt[5]).astype(int)
    c0, r0 = col.min() - pad_px, row.min() - pad_px
    c1, r1 = col.max() + pad_px + 1, row.max() + pad_px + 1
    out = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
    sc0, sr0 = max(c0, 0), max(r0, 0)
    sc1, sr1 = min(c1, ds.RasterXSize), min(r1, ds.RasterYSize)
    arr = band.ReadAsArray(sc0, sr0, sc1 - sc0, sr1 - sr0).astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        arr[arr == np.float32(nodata)] = np.nan
    out[sr0 - r0:sr1 - r0, sc0 - c0:sc1 - c0] = arr
    return out, row - r0, col - c0


def _grow(mask: np.ndarray, r: int) -> np.ndarray:
    """Square dilation by r cells."""
    out = mask.copy()
    rows, cols = mask.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            dst = out[max(0, -dy):rows - max(0, dy), max(0, -dx):cols - max(0, dx)]
            src = mask[max(0, dy):rows - max(0, -dy), max(0, dx):cols - max(0, -dx)]
            dst |= src
    return out


def steep_metres(geom: ogr.Geometry) -> dict:
    xy = exposure.sample_points(geom, STEP_M)
    slope, r, c = _window(paths.layer("slope"), xy, pad_px=3)
    steep = np.nan_to_num(slope, nan=0.0) >= STEEP_DEG
    on = steep[r, c]
    near1 = _grow(steep, 1)[r, c] & ~on
    near2 = _grow(steep, 2)[r, c] & ~on
    return {"steep_m": on.sum() * STEP_M,
            "near10_m": near1.sum() * STEP_M,
            "near20_m": near2.sum() * STEP_M}


def surface_cost(geom: ogr.Geometry, surface: Path) -> float:
    """Approximate line integral of cost: sum of cell cost per 10 m walked.
    Same units as r.cost's cost_opt, close enough to compare two lines."""
    xy = exposure.sample_points(geom, STEP_M)
    cost, r, c = _window(surface, xy, pad_px=0)
    v = cost[r, c]
    v[v >= config.COST_NODATA] = np.nan
    return float(np.nansum(v) * STEP_M / config.PIXEL_SIZE)


# --- reading routes ----------------------------------------------------------


def read_routes(path: Path) -> dict[int, dict]:
    ds = ogr.Open(str(path))
    out = {}
    for f in ds.GetLayerByName(routing.ROUTES_LAYER):
        g = f.GetGeometryRef()
        if g is None:
            continue
        defn = f.GetDefnRef()
        has = lambda k: defn.GetFieldIndex(k) >= 0
        out[f.GetField("tour_fid")] = {
            "name": f.GetField("name") or "",
            "geom": g.Clone(),
            "length_m": float(f.GetField("length_m") or 0.0),
            "exp_per_km": float(f.GetField("exp_per_km")) if has("exp_per_km")
                          and f.GetField("exp_per_km") is not None else None,
        }
    return out


def _scored(path: Path) -> dict[int, dict]:
    """Routes with exposure, scoring them in place first if they are not."""
    routes = read_routes(path)
    if any(r["exp_per_km"] is None for r in routes.values()):
        exposure.score_routes(path)
        routes = read_routes(path)
    return routes


# --- pick ----------------------------------------------------------------------


def pick(count: int, exclude: set[int]) -> list[int]:
    """Production tours whose route runs the most metres along steep ground
    without being on it - where a spread should bite if it bites anywhere."""
    from skimap import tours as tours_mod

    live = {t.fid for t in tours_mod.read_tours()}
    rows = []
    for fid, r in read_routes(paths.ROUTES / "routes.gpkg").items():
        if fid not in live or fid in exclude or r["length_m"] < 1000:
            continue
        m = steep_metres(r["geom"])
        rows.append((m["near10_m"] / (r["length_m"] / 1000.0), fid, r["name"], m))
    rows.sort(reverse=True)
    print(f"{'fid':>5}  {'tour':28s} {'near10 m/km':>11} {'steep m':>8}")
    for per_km, fid, name, m in rows[:count]:
        print(f"{fid:>5}  {name[:28]:28s} {per_km:11.0f} {m['steep_m']:8.0f}")
    return [fid for _, fid, _, _ in rows[:count]]


# --- compare -------------------------------------------------------------------


def compare(variants: tuple[str, ...], out_csv: Path) -> None:
    control_dir = LAB / CONTROL
    control = _scored(control_dir / "routes.gpkg")
    control_vrt = control_dir / "cost_surface.vrt"
    base = {fid: {**steep_metres(r["geom"]),
                  "ctl_cost": surface_cost(r["geom"], control_vrt)}
            for fid, r in control.items()}

    rows = []
    for fid, r in control.items():
        rows.append({"profile": CONTROL, "fid": fid, "name": r["name"],
                     "length_m": r["length_m"], "exp_per_km": r["exp_per_km"],
                     "sep_max_m": 0.0, **base[fid]})

    print(f"\n{len(control)} tours, measured against {CONTROL}\n")
    head = (f"  {'profile':22s} {'moved>50m':>9} {'>250m':>6} {'sep med':>8} "
            f"{'len':>7} {'steep m':>8} {'near10 m':>9} {'near20 m':>9} "
            f"{'exp/km':>7} {'ctl cost':>9}")
    print(head)
    total = lambda key, src: sum(v[key] for v in src.values())
    exp_km = lambda src: np.mean([v["exp_per_km"] for v in src.values()])
    print(f"  {CONTROL:22s} {'':>9} {'':>6} {'':>8} "
          f"{total('length_m', control) / 1000:6.1f}k {total('steep_m', base):8.0f} "
          f"{total('near10_m', base):9.0f} {total('near20_m', base):9.0f} "
          f"{exp_km(control):7.2f} {total('ctl_cost', base):9.0f}")

    for name in variants:
        path = LAB / name / "routes.gpkg"
        if not path.exists():
            print(f"  {name:22s} not routed yet")
            continue
        routes = {k: v for k, v in _scored(path).items() if k in control}
        stats = {}
        for fid, r in routes.items():
            mean_a, max_a = routing.separation(r["geom"], control[fid]["geom"])
            mean_b, max_b = routing.separation(control[fid]["geom"], r["geom"])
            stats[fid] = {**steep_metres(r["geom"]),
                          "ctl_cost": surface_cost(r["geom"], control_vrt),
                          "sep_max_m": max(max_a, max_b)}
            rows.append({"profile": name, "fid": fid, "name": r["name"],
                         "length_m": r["length_m"], "exp_per_km": r["exp_per_km"],
                         **stats[fid]})
        seps = np.array([s["sep_max_m"] for s in stats.values()])
        pct = lambda a, b: f"{(a - b) / b:+.0%}" if b else "  n/a"
        base_sub = {f: base[f] for f in routes}
        ctl_sub = {f: control[f] for f in routes}
        print(f"  {name:22s} {int((seps >= 50).sum()):>4}/{len(seps):<4} "
              f"{int((seps >= 250).sum()):>6} {np.median(seps):7.0f}m "
              f"{pct(total('length_m', routes), total('length_m', ctl_sub)):>7} "
              f"{pct(total('steep_m', stats), total('steep_m', base_sub)):>8} "
              f"{pct(total('near10_m', stats), total('near10_m', base_sub)):>9} "
              f"{pct(total('near20_m', stats), total('near20_m', base_sub)):>9} "
              f"{pct(exp_km(routes), exp_km(ctl_sub)):>7} "
              f"{pct(total('ctl_cost', stats), total('ctl_cost', base_sub)):>9}")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    keys = ["profile", "fid", "name", "length_m", "sep_max_m", "steep_m",
            "near10_m", "near20_m", "exp_per_km", "ctl_cost"]
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(row[k], 2) if isinstance(row[k], float) else row[k])
                        for k in keys})
    print(f"\n  Totals over the tour set; % is against the control. -> {out_csv}")


# --- arcgis --------------------------------------------------------------------

ARCGIS = LAB / "steep_spread_arcgis"
STYLES = paths.DATA / "styles_arcgis"
CREATE = ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=DEFLATE",
          "PREDICTOR=2", "SPARSE_OK=TRUE", "BIGTIFF=YES"]


def _blank(path: Path, like: gdal.Dataset, dtype: int, nodata: float) -> gdal.Dataset:
    """An all-nodata sparse GeoTIFF on `like`'s grid. Writes nothing yet."""
    path.unlink(missing_ok=True)
    ds = gdal.GetDriverByName("GTiff").Create(
        str(path), like.RasterXSize, like.RasterYSize, 1, dtype, options=CREATE)
    ds.SetGeoTransform(like.GetGeoTransform())
    ds.SetProjection(like.GetProjection())
    ds.GetRasterBand(1).SetNoDataValue(nodata)
    return ds


def _offset(out: gdal.Dataset, src_gt) -> tuple[int, int]:
    gt = out.GetGeoTransform()
    return (int(round((src_gt[0] - gt[0]) / gt[1])),
            int(round((src_gt[3] - gt[3]) / gt[5])))


def _finish(ds: gdal.Dataset, path: Path, resampling: str = "NEAREST") -> None:
    """Overviews, so ArcGIS does not ask to build pyramids over 8 billion cells."""
    gdal.SetConfigOption("SPARSE_OK_OVERVIEW", "ON")
    ds.BuildOverviews(resampling, [4, 16, 64, 256])
    ds = None
    print(f"  {path.name}")


def _lyrx(style: str, target: Path) -> None:
    """A copy of one of data/styles_arcgis/*.lyrx pointed at `target`, saved
    beside it: drag it into a map and it opens styled."""
    import json

    doc = json.loads((STYLES / style).read_text(encoding="utf-8-sig"))
    layer = doc["layerDefinitions"][0]
    layer["name"] = target.stem
    layer["dataConnection"]["workspaceConnectionString"] = "DATABASE=."
    layer["dataConnection"]["dataset"] = target.name
    target.with_suffix(".lyrx").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _tiles(profile: str) -> list[Path]:
    return sorted((LAB / profile / "tiles").glob("*/cost_surface.tif"))


def export_arcgis(profiles: tuple[str, ...]) -> None:
    ARCGIS.mkdir(parents=True, exist_ok=True)
    like = gdal.Open(str(LAB / CONTROL / "cost_surface.vrt"))
    print(f"-> {ARCGIS}")

    # The surfaces, straight from each profile's VRT.
    for name in profiles:
        out = ARCGIS / f"cost_{name}.tif"
        out.unlink(missing_ok=True)
        ds = gdal.Translate(str(out), str(LAB / name / "cost_surface.vrt"),
                            creationOptions=CREATE)
        _finish(ds, out)
        _lyrx("cost_surface.tif.lyrx", out)

    # The source cells, from the national slope over the same tiles.
    slope_ds = gdal.Open(str(paths.layer("slope")))
    slope_gt = slope_ds.GetGeoTransform()
    out = ARCGIS / "steep_ge30.tif"
    ds = _blank(out, like, gdal.GDT_Byte, 0)
    for tile in _tiles(CONTROL):
        t = gdal.Open(str(tile))
        gt = t.GetGeoTransform()
        sx = int(round((gt[0] - slope_gt[0]) / slope_gt[1]))
        sy = int(round((gt[3] - slope_gt[3]) / slope_gt[5]))
        slope = slope_ds.GetRasterBand(1).ReadAsArray(sx, sy, t.RasterXSize, t.RasterYSize)
        ds.GetRasterBand(1).WriteArray((slope >= STEEP_DEG).astype(np.uint8),
                                       *_offset(ds, gt))
    _finish(ds, out)

    # What each variant added: the final surfaces' difference, so it is
    # exactly what the router saw change - after roads, barriers and tracks.
    for name in profiles:
        if name == CONTROL:
            continue
        out = ARCGIS / f"spread_added_{name}.tif"
        ds = _blank(out, like, gdal.GDT_Int16, 0)
        for tile in _tiles(name):
            base = LAB / CONTROL / "tiles" / tile.parent.name / "cost_surface.tif"
            t, b = gdal.Open(str(tile)), gdal.Open(str(base))
            a = t.ReadAsArray().astype(np.int32)
            diff = a - b.ReadAsArray().astype(np.int32)
            diff[a == config.COST_NODATA] = 0
            ds.GetRasterBand(1).WriteArray(np.clip(diff, -32768, 32767).astype(np.int16),
                                           *_offset(ds, t.GetGeoTransform()))
        _finish(ds, out)

    # Corridors, MAXed where two tours' bands overlap.
    for name in profiles:
        out = ARCGIS / f"corridors_{name}.tif"
        ds = _blank(out, like, gdal.GDT_Float32, config.NODATA)
        band = ds.GetRasterBand(1)
        for tif in sorted((LAB / name / "corridors").glob("*.tif")):
            c = gdal.Open(str(tif))
            x, y = _offset(ds, c.GetGeoTransform())
            new = c.ReadAsArray().astype(np.float32)
            new[new == np.float32(config.NODATA)] = np.nan
            old = band.ReadAsArray(x, y, c.RasterXSize, c.RasterYSize)
            old = np.where(old == np.float32(config.NODATA), np.nan, old)
            merged = np.fmax(old, new)
            band.WriteArray(np.where(np.isnan(merged), config.NODATA, merged)
                            .astype(np.float32), x, y)
        _finish(ds, out)
        _lyrx("green.lyrx", out)

    # Routes: one layer, every profile, so one map can filter or colour by it.
    out = ARCGIS / "routes.gpkg"
    out.unlink(missing_ok=True)
    dst = ogr.GetDriverByName("GPKG").CreateDataSource(str(out))
    layer, have = None, set()
    for name in profiles:
        src = ogr.Open(str(LAB / name / "routes.gpkg"))
        src_layer = src.GetLayerByName(routing.ROUTES_LAYER)
        if layer is None:
            layer = dst.CreateLayer("routes", src_layer.GetSpatialRef(), ogr.wkbLineString)
            layer.CreateField(ogr.FieldDefn("profile", ogr.OFTString))
            have.add("profile")
        defn = src_layer.GetLayerDefn()
        for i in range(defn.GetFieldCount()):
            field = defn.GetFieldDefn(i)
            if field.GetName() not in have:
                layer.CreateField(field)
                have.add(field.GetName())
        layer.StartTransaction()
        for feat in src_layer:
            f = ogr.Feature(layer.GetLayerDefn())
            f.SetField("profile", name)
            for i in range(defn.GetFieldCount()):
                f.SetField(defn.GetFieldDefn(i).GetName(), feat.GetField(i))
            f.SetGeometry(feat.GetGeometryRef())
            layer.CreateFeature(f)
        layer.CommitTransaction()
    dst = None
    print(f"  {out.name}")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m tests.steep_spread_report")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pick", help="rank production tours by metres along steep ground")
    s.add_argument("--count", type=int, default=15)
    s.add_argument("--exclude", type=int, action="append", default=[])
    s = sub.add_parser("compare", help="the scorecard, every variant against the control")
    s.add_argument("--variant", action="append", dest="variants")
    s.add_argument("--out", type=Path, default=LAB / "steep_spread_report.csv")
    sub.add_parser("arcgis", help="every surface, corridor and route as files ArcGIS reads")
    args = p.parse_args(argv)

    if args.cmd == "pick":
        print(pick(args.count, set(args.exclude)))
    elif args.cmd == "arcgis":
        export_arcgis((CONTROL,) + VARIANTS)
    else:
        compare(tuple(args.variants or VARIANTS), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
