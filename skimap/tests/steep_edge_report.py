r"""What closing the edge of steep ground (config.STEEP_EDGE) did to the routes.

Not a unit test - the lab experiment's scorecard. The lab itself answers "how
far did each line move"; this answers "moved to where": off steep ground, or
just away from it, and at what price. The control is production as it is now.

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    $py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
    & $py -m tests.steep_edge_report pick --count 15       # tours worth testing
    & $py -m skimap.lab run steep_edge_control --jobs 8
    & $py -m skimap.lab run steep_edge_corners --jobs 8 --against steep_edge_control
    ...
    & $py -m tests.steep_edge_report compare               # the scorecard

Every measure but `ctl_cost` reads the national rasters, never a lab surface,
so a variant cannot score well by having redrawn the thing it is scored on:

  steep_m       route metres on a cell >= 30 deg - on the ORIGINAL slope
  near10_m      metres within one cell (10 m) of such a cell, not on one
  near20_m      metres within two cells (20 m), not on one
  exp_score     exposure, from PRA and runout (skimap.exposure). Compared as
                total exposure per total km, so a 250 m tour cannot swing it
  ctl_cost      the line's cost on the CONTROL surface - what the detour
                costs in today's terms. A rise is the price of the change.
                Approximate (the smoothed line, sampled), so +-1% is noise.

Totals hide direction, so each measure also gets a count of the tours it
went up on and down on.

Writes data/test/lab/steep_edge_report.csv, one row per tour and profile.

    & $py -m tests.steep_edge_report arcgis

puts everything in data/test/lab/steep_edge_arcgis/ as files ArcGIS reads -
the lab's own surfaces are VRTs, which it does not:

  cost_<profile>.tif        the cost surface each profile routed on, + .lyrx
                            in the production symbology
  edge_added_<variant>      what the variant added: variant minus control,
                            in cost units, nodata where it added nothing
  steep_ge30.tif            slope >= 30 deg, the ground whose edge it is
  corridors_<profile>.tif   every tour's corridor, overlaps MAXed, + .lyrx
  routes.gpkg               every profile's routes in one layer, field
                            `profile`, with the scorecard columns per line

Rasters span the whole tour set, which is regions 1000 km apart, so they
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
CONTROL = "steep_edge_control"
VARIANTS = ("steep_edge_corners", "steep_edge_corners_buffer1",
            "steep_edge_corners_buffer2", "steep_edge_corners_buffer3",
            "steep_edge_corners_buffer5")
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
            "exp_score": float(f.GetField("exp_score")) if has("exp_score")
                         and f.GetField("exp_score") is not None else None,
        }
    return out


def _scored(path: Path) -> dict[int, dict]:
    """Routes with exposure, scoring them in place first if they are not."""
    routes = read_routes(path)
    if any(r["exp_score"] is None for r in routes.values()):
        exposure.score_routes(path)
        routes = read_routes(path)
    return routes


# --- pick ----------------------------------------------------------------------


def pick(count: int, exclude: set[int]) -> list[int]:
    """Production tours whose route runs the most metres along steep ground
    without being on it - where a change at the edge bites if it bites anywhere."""
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
                  "ctl_cost": surface_cost(r["geom"], control_vrt),
                  "length_m": r["length_m"], "exp_score": r["exp_score"]}
            for fid, r in control.items()}

    rows = [{"profile": CONTROL, "fid": fid, "name": r["name"], "sep_max_m": 0.0,
             **base[fid]} for fid, r in control.items()]

    total = lambda key, src: sum(v[key] for v in src.values())
    exp_km = lambda src: total("exp_score", src) / (total("length_m", src) / 1000.0)
    keys = ("length_m", "steep_m", "near10_m", "near20_m", "exp", "ctl_cost")

    print(f"\n{len(control)} tours, each variant against {CONTROL} (production now)\n")
    print(f"  {'':32s} {'moved':>6} {'moved':>6} {'sep':>6}"
          + "".join(f"{k:>11}" for k in ("length", "on >=30", "<10 m", "<20 m",
                                          "exp/km", "ctl cost")))
    print(f"  {'':32s} {'>50 m':>6} {'>250 m':>6} {'median':>6}")
    print(f"  {CONTROL:32s} {'':>6} {'':>6} {'':>6}"
          f"{total('length_m', base) / 1000:9.1f}km{total('steep_m', base):9.0f} m"
          f"{total('near10_m', base):9.0f} m{total('near20_m', base):9.0f} m"
          f"{exp_km(base):11.2f}{total('ctl_cost', base):11.0f}")

    for name in variants:
        path = LAB / name / "routes.gpkg"
        if not path.exists():
            print(f"  {name:32s} not routed yet")
            continue
        routes = {k: v for k, v in _scored(path).items() if k in control}
        stats = {}
        for fid, r in routes.items():
            mean_a, max_a = routing.separation(r["geom"], control[fid]["geom"])
            mean_b, max_b = routing.separation(control[fid]["geom"], r["geom"])
            stats[fid] = {**steep_metres(r["geom"]),
                          "ctl_cost": surface_cost(r["geom"], control_vrt),
                          "length_m": r["length_m"], "exp_score": r["exp_score"],
                          "sep_max_m": max(max_a, max_b)}
            rows.append({"profile": name, "fid": fid, "name": r["name"], **stats[fid]})

        seps = np.array([v["sep_max_m"] for v in stats.values()])
        ref = {f: base[f] for f in routes}
        change = {
            "length_m": total("length_m", stats) / total("length_m", ref) - 1,
            "steep_m": total("steep_m", stats) / total("steep_m", ref) - 1,
            "near10_m": total("near10_m", stats) / total("near10_m", ref) - 1,
            "near20_m": total("near20_m", stats) / total("near20_m", ref) - 1,
            "exp": exp_km(stats) / exp_km(ref) - 1,
            "ctl_cost": total("ctl_cost", stats) / total("ctl_cost", ref) - 1,
        }
        print(f"  {name:32s} {int((seps >= 50).sum()):>6} {int((seps >= 250).sum()):>6} "
              f"{np.median(seps):5.0f}m" + "".join(f"{change[k]:+11.1%}" for k in keys))

        # Which way, tour by tour - a total can be one tour.
        def updown(key, tol):
            if key == "exp":
                d = np.array([stats[f]["exp_score"] / max(stats[f]["length_m"], 1)
                              - ref[f]["exp_score"] / max(ref[f]["length_m"], 1)
                              for f in stats]) * 1000.0
            else:
                d = np.array([stats[f][key] - ref[f][key] for f in stats])
            return f"{int((d > tol).sum())}/{int((d < -tol).sum())}"
        tols = {"length_m": 10, "steep_m": 10, "near10_m": 10, "near20_m": 10,
                "exp": 0.05, "ctl_cost": 10}
        print(f"  {'  tours up/down':32s} {'':>6} {'':>6} {'':>6}"
              + "".join(f"{updown(k, tols[k]):>11}" for k in keys))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = ["profile", "fid", "name", "length_m", "sep_max_m", "steep_m",
            "near10_m", "near20_m", "exp_score", "ctl_cost"]
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(row[k], 2) if isinstance(row[k], float) else row[k])
                        for k in cols})
    print(f"\n  % is the change in the total over the tour set against the control; "
          f"exp/km is total exposure per total km.\n  -> {out_csv}")


# --- arcgis --------------------------------------------------------------------

ARCGIS = LAB / "steep_edge_arcgis"
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


def export_arcgis(profiles: tuple[str, ...], *, corridors: bool = True) -> None:
    """Rasters for `profiles`; routes.gpkg always for every profile there is.

    Passing a subset adds those profiles' rasters and leaves the others' files
    as they are - steep_ge30.tif is only rewritten along with the control.
    """
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

    # The steep ground, from the national slope over the same tiles.
    if CONTROL in profiles:
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
        out = ARCGIS / f"edge_added_{name}.tif"
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
    for name in profiles if corridors else ():
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

    export_routes((CONTROL,) + VARIANTS)


def export_routes(profiles: tuple[str, ...]) -> None:
    """Every profile's routes in one layer, so one map can filter or colour by it.

    Exposure is scored first where a profile's routes have none yet, so every
    line carries exp_score and exp_per_km. A profile not routed is skipped.
    """
    profiles = tuple(n for n in profiles if (LAB / n / "routes.gpkg").exists())
    for name in profiles:
        _scored(LAB / name / "routes.gpkg")
    out = ARCGIS / "routes.gpkg"
    try:
        out.unlink(missing_ok=True)
    except PermissionError:
        # Open in ArcGIS, which holds a GeoPackage locked. Write beside it.
        import time
        out = ARCGIS / f"routes_{time.strftime('%H%M')}.gpkg"
        print(f"  routes.gpkg is open elsewhere - writing {out.name} instead")
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


# --- national ------------------------------------------------------------------

# The production routes of 2026-09-18, on the surface before STEEP_EDGE -
# the frozen copy the corridor review reads.
NATIONAL_OLD = paths.DATA / "review" / "frozen" / "baseline_20260918"
NATIONAL_NEW = paths.DATA / "test" / "track_variants" / "edge_buffer2"
NATIONAL_OUT = paths.DATA / "test" / "surface_compare"


def compare_national(old_dir: Path, new_dir: Path, out_dir: Path, *, min_sep: float) -> None:
    """Every tour routed on two national surfaces: the ones whose lines differ,
    as two GeoPackages - the old line and the new one, matched by tour_fid -
    with the measures above on each line, and a summary over all tours.

    Only tours known to be the same in both are compared: same tour_fid AND
    both lines ending where the other's do (within a metre - a route starts
    and ends on the cell of its tour's points, so an unchanged tour gives
    identical ends). A tour added or moved between the two runs is left out
    rather than read as the surface's doing.
    """
    import math

    old = _scored(old_dir / "routes.gpkg")
    new = _scored(new_dir / "routes.gpkg")

    def same_ends(a: ogr.Geometry, b: ogr.Geometry) -> bool:
        a0, a1 = a.GetPoint_2D(0), a.GetPoint_2D(a.GetPointCount() - 1)
        b0, b1 = b.GetPoint_2D(0), b.GetPoint_2D(b.GetPointCount() - 1)
        return (max(math.dist(a0, b0), math.dist(a1, b1)) <= 1.0
                or max(math.dist(a0, b1), math.dist(a1, b0)) <= 1.0)

    both = sorted(set(old) & set(new))
    fids = [f for f in both if same_ends(old[f]["geom"], new[f]["geom"])]
    print(f"{len(old)} old, {len(new)} new, {len(both)} tour ids in both, "
          f"{len(fids)} with the same endpoints - compared; "
          f"{len(both) - len(fids)} moved and {len(set(new) - set(old))} new tours left out")

    stats = {}
    for n, fid in enumerate(fids, 1):
        o, w = old[fid], new[fid]
        mean_a, max_a = routing.separation(w["geom"], o["geom"])
        mean_b, max_b = routing.separation(o["geom"], w["geom"])
        stats[fid] = {
            "sep_max_m": max(max_a, max_b), "sep_mean_m": (mean_a + mean_b) / 2.0,
            "old": {**steep_metres(o["geom"]), "length_m": o["length_m"], "exp_score": o["exp_score"]},
            "new": {**steep_metres(w["geom"]), "length_m": w["length_m"], "exp_score": w["exp_score"]},
        }
        if n % 100 == 0:
            print(f"  measured {n}/{len(fids)}", flush=True)

    differ = [f for f in fids if stats[f]["sep_max_m"] >= min_sep]
    seps = np.array([stats[f]["sep_max_m"] for f in fids])

    # The summary, over ALL tours - the unchanged ones are part of the answer.
    tot = lambda side, key: sum(stats[f][side][key] for f in fids)
    exp_km = lambda side: tot(side, "exp_score") / (tot(side, "length_m") / 1000.0)
    def updown(key, tol):
        if key == "exp":
            d = np.array([stats[f]["new"]["exp_score"] / max(stats[f]["new"]["length_m"], 1)
                          - stats[f]["old"]["exp_score"] / max(stats[f]["old"]["length_m"], 1)
                          for f in fids]) * 1000.0
        else:
            d = np.array([stats[f]["new"][key] - stats[f]["old"][key] for f in fids])
        return int((d > tol).sum()), int((d < -tol).sum())

    print(f"\n{len(fids)} tours, new surface against old\n")
    print(f"  lines differ (>= {min_sep:g} m apart somewhere): {len(differ)}")
    for cut in (50, 250, 1000):
        print(f"  moved more than {cut:4d} m:                  {int((seps >= cut).sum())}")
    print(f"\n  {'':22s} {'old':>12} {'new':>12} {'change':>8} {'tours up/down':>14}")
    for label, key, tol, unit in (("length", "length_m", 10, "km"),
                                  ("on >= 30 deg", "steep_m", 10, "m"),
                                  ("within 10 m of it", "near10_m", 10, "m"),
                                  ("within 20 m of it", "near20_m", 10, "m")):
        a, b = tot("old", key), tot("new", key)
        scale = 1000.0 if unit == "km" else 1.0
        up, down = updown(key, tol)
        print(f"  {label:22s} {a / scale:10.0f}{unit:2s} {b / scale:10.0f}{unit:2s} "
              f"{b / a - 1:+8.1%} {up:>7}/{down:<6}")
    up, down = updown("exp", 0.05)
    print(f"  {'exposure per km':22s} {exp_km('old'):12.2f} {exp_km('new'):12.2f} "
          f"{exp_km('new') / exp_km('old') - 1:+8.1%} {up:>7}/{down:<6}")

    # The two files: differing tours only, the same fields on both sides.
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = (("tour_fid", ogr.OFTInteger), ("name", ogr.OFTString),
              ("sep_max_m", ogr.OFTReal), ("sep_mean_m", ogr.OFTReal),
              ("length_m", ogr.OFTReal), ("len_diff_m", ogr.OFTReal),
              ("steep_m", ogr.OFTReal), ("near10_m", ogr.OFTReal), ("near20_m", ogr.OFTReal),
              ("exp_score", ogr.OFTReal), ("exp_per_km", ogr.OFTReal))
    # Held in a name: a dataset dropped mid-chain frees the layer under it.
    src = ogr.Open(str(new_dir / "routes.gpkg"))
    srs = src.GetLayerByName(routing.ROUTES_LAYER).GetSpatialRef().Clone()
    src = None
    written = []
    for side, routes, other in (("old", old, "new"), ("new", new, "old")):
        path = out_dir / f"routes_{side}_surface.gpkg"
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            import time
            path = out_dir / f"routes_{side}_surface_{time.strftime('%H%M')}.gpkg"
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
        layer = ds.CreateLayer("routes", srs, ogr.wkbLineString)
        for name, kind in fields:
            layer.CreateField(ogr.FieldDefn(name, kind))
        layer.StartTransaction()
        for fid in sorted(differ, key=lambda f: -stats[f]["sep_max_m"]):
            s, m = stats[fid], stats[fid][side]
            feat = ogr.Feature(layer.GetLayerDefn())
            values = {"tour_fid": fid, "name": routes[fid]["name"],
                      "sep_max_m": s["sep_max_m"], "sep_mean_m": s["sep_mean_m"],
                      "length_m": m["length_m"],
                      "len_diff_m": m["length_m"] - s[other]["length_m"],
                      "steep_m": m["steep_m"], "near10_m": m["near10_m"], "near20_m": m["near20_m"],
                      "exp_score": m["exp_score"],
                      "exp_per_km": m["exp_score"] / max(m["length_m"], 1) * 1000.0}
            for k, v in values.items():
                feat.SetField(k, round(v, 1) if isinstance(v, float) else v)
            feat.SetGeometry(routes[fid]["geom"])
            layer.CreateFeature(feat)
        layer.CommitTransaction()
        ds = None
        written.append(path)

    with (out_dir / "surface_compare.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tour_fid", "name", "differs", "sep_max_m", "old_length_m", "new_length_m",
                    "old_steep_m", "new_steep_m", "old_near10_m", "new_near10_m",
                    "old_exp_per_km", "new_exp_per_km"])
        for fid in fids:
            s = stats[fid]
            w.writerow([fid, new[fid]["name"], int(s["sep_max_m"] >= min_sep),
                        round(s["sep_max_m"], 1),
                        round(s["old"]["length_m"], 1), round(s["new"]["length_m"], 1),
                        round(s["old"]["steep_m"], 1), round(s["new"]["steep_m"], 1),
                        round(s["old"]["near10_m"], 1), round(s["new"]["near10_m"], 1),
                        round(s["old"]["exp_score"] / max(s["old"]["length_m"], 1) * 1000, 3),
                        round(s["new"]["exp_score"] / max(s["new"]["length_m"], 1) * 1000, 3)])
    print(f"\n  {len(differ)} differing tours -> " + ", ".join(p.name for p in written)
          + f", plus surface_compare.csv (all tours)\n  in {out_dir}")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m tests.steep_edge_report")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pick", help="rank production tours by metres along steep ground")
    s.add_argument("--count", type=int, default=15)
    s.add_argument("--exclude", type=int, action="append", default=[])
    s = sub.add_parser("compare", help="the scorecard, every variant against the control")
    s.add_argument("--variant", action="append", dest="variants")
    s.add_argument("--out", type=Path, default=LAB / "steep_edge_report.csv")
    s = sub.add_parser("arcgis", help="every surface, corridor and route as files ArcGIS reads")
    s.add_argument("--routes-only", action="store_true", help="just routes.gpkg")
    s.add_argument("--profile", action="append", dest="profiles",
                   help="rasters for this profile only (repeatable); routes.gpkg "
                        "still gets every profile")
    s.add_argument("--no-corridors", action="store_true", help="skip the corridor rasters")
    s = sub.add_parser("national", help="every tour, old national surface against new: "
                                        "the differing lines as two GeoPackages")
    s.add_argument("--old", type=Path, default=NATIONAL_OLD, help="folder with routes.gpkg")
    s.add_argument("--new", type=Path, default=NATIONAL_NEW, help="folder with routes.gpkg")
    s.add_argument("--out", type=Path, default=NATIONAL_OUT)
    s.add_argument("--min-sep", type=float, default=10.0,
                   help="metres apart for two lines to count as different (default one cell)")
    args = p.parse_args(argv)

    if args.cmd == "national":
        compare_national(args.old, args.new, args.out, min_sep=args.min_sep)
    elif args.cmd == "pick":
        print(pick(args.count, set(args.exclude)))
    elif args.cmd == "arcgis" and args.routes_only:
        export_routes((CONTROL,) + VARIANTS)
    elif args.cmd == "arcgis":
        export_arcgis(tuple(args.profiles or (CONTROL,) + VARIANTS),
                      corridors=not args.no_corridors)
    else:
        compare(tuple(args.variants or VARIANTS), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
