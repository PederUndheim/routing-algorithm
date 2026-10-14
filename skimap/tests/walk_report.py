r"""r.walk against r.cost on the steep_edge_control tours: what it costs to
compute, where the lines go, and whether the corridor survives the switch.

Not a unit test - the lab experiment's scorecard, beside steep_edge_report.
The three profiles route over steep_edge_control's own surface (lab
"surface_from"), so the only thing that differs is the engine
(config.ROUTING["engine"], config.WALK):

  walk_ref    r.cost, as production. Re-run only to be timed beside the
              others on the same machine and day; its lines are the control's
  walk_line   r.walk draws the line, r.cost the corridor - the old router
  walk        r.walk for both; the end-side spread over the negated DEM

Run from the project directory - skimap/, the one holding skimap/ and tests/:

    $py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
    & $py -m skimap.lab route walk_ref
    & $py -m skimap.lab run walk_line --against steep_edge_control
    & $py -m skimap.lab run walk --against steep_edge_control
    & $py -m tests.walk_report compare       # time, lines, corridors
    & $py -m tests.walk_report calibrate     # what max_gap_scale matches r.cost's band
    & $py -m tests.walk_report recut --scale 18   # re-cut walk's bands at it
    & $py -m tests.walk_report arcgis        # both engines into walk_arcgis/

Line measures are steep_edge_report's - steep_m, near10_m, exposure per km,
ctl_cost (the line priced on the control surface, in r.cost's terms, so a
rise is what the r.walk line costs by today's measure) - plus two r.walk is
meant to move, from the national DEM in the tour's own direction:

  climb_m     total ascent, start to end
  reclimb_m   ascent beyond the net gain: height given up and climbed again.
              The thing no r.cost layer prices, and the case for r.walk.

Corridor measures, standard band, against the control's:

  area        live cells, walk / control
  iou         cells in both over cells in either
  line_in     share of the line inside its own corridor. walk_line's line
              is r.walk's and its corridor r.cost's, so it can leave it
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal

from skimap import config, exposure, paths, routing
from tests.steep_edge_report import (LAB, STEP_M, _scored, _window, steep_metres,
                                     surface_cost)

gdal.UseExceptions()

CONTROL = "steep_edge_control"
REF = "walk_ref"
VARIANTS = ("walk_line", "walk")
CLIMB_STEP_M = config.PIXEL_SIZE   # one sample per cell: DEM noise below that is not climbing


# --- per line ----------------------------------------------------------------


def _tours() -> dict:
    from skimap import tours as tours_mod

    return {t.fid: t for t in tours_mod.read_tours()}


def climb(geom, tour) -> dict:
    """Ascent along the line in the tour's direction, and the part of it
    beyond the net gain. r.path writes lines summit-first, so orient by the
    tour's start rather than trusting the vertex order."""
    xy = exposure.sample_points(geom, CLIMB_STEP_M)
    if np.hypot(*(xy[0] - tour.start)) > np.hypot(*(xy[-1] - tour.start)):
        xy = xy[::-1]
    z, r, c = _window(paths.layer("dem"), xy, pad_px=0)
    z = z[r, c]
    z = z[np.isfinite(z)]
    if len(z) < 2:
        return {"climb_m": np.nan, "reclimb_m": np.nan}
    dz = np.diff(z)
    up = float(dz[dz > 0].sum())
    return {"climb_m": up, "reclimb_m": up - max(0.0, float(z[-1] - z[0]))}


def _corridor(profile: str, fid: int, width: Optional[str] = None) -> Optional[Path]:
    folder = LAB / profile / "corridors"
    if width:
        folder = routing.width_dir(folder, width)
    hits = sorted(folder.glob(f"{fid:03d}_*.tif"))
    return hits[0] if hits else None


def _live(path: Path):
    """(mask of live cells, geotransform)."""
    ds = gdal.Open(str(path))
    a = ds.GetRasterBand(1).ReadAsArray()
    return np.isfinite(a) & (a != np.float32(config.NODATA)), ds.GetGeoTransform()


def _on_union(a, ga, b, gb):
    """Two masks on one lattice, pasted onto the grid covering both."""
    px = ga[1]
    x0, y1 = min(ga[0], gb[0]), max(ga[3], gb[3])
    x1 = max(ga[0] + a.shape[1] * px, gb[0] + b.shape[1] * px)
    y0 = min(ga[3] - a.shape[0] * px, gb[3] - b.shape[0] * px)
    shape = (int(round((y1 - y0) / px)), int(round((x1 - x0) / px)))
    out = []
    for m, g in ((a, ga), (b, gb)):
        full = np.zeros(shape, bool)
        r, c = int(round((y1 - g[3]) / px)), int(round((g[0] - x0) / px))
        full[r:r + m.shape[0], c:c + m.shape[1]] = m
        out.append(full)
    return out


def line_inside(geom, corridor: Path) -> float:
    xy = exposure.sample_points(geom, CLIMB_STEP_M)
    v, r, c = _window(corridor, xy, pad_px=0)
    return float(np.isfinite(v[r, c]).mean())


WIDTHS = (None, *config.CORRIDOR_WIDTHS)   # None is the standard band


def _wkey(width: Optional[str]) -> str:
    return width or "standard"


def corridor_stats(fid: int, geom, profile: str, width: Optional[str] = None) -> dict:
    """The band `width` of `profile`'s corridor against the control's."""
    ctl, own = _corridor(CONTROL, fid, width), _corridor(profile, fid, width)
    if ctl is None or own is None:
        return {}
    a, ga = _live(own)
    b, gb = _live(ctl)
    a, b = _on_union(a, ga, b, gb)
    cell_km2 = (config.PIXEL_SIZE / 1000.0) ** 2
    return {"area_ratio": a.sum() / max(b.sum(), 1),
            "iou": (a & b).sum() / max((a | b).sum(), 1),
            "area_km2": a.sum() * cell_km2,
            "only_own_km2": (a & ~b).sum() * cell_km2,
            "only_ctl_km2": (b & ~a).sum() * cell_km2,
            "line_in": line_inside(geom, own)}


def all_widths(fid: int, geom, profile: str) -> dict:
    """corridor_stats for every width, keyed `iou_standard`, `iou_narrow`..."""
    out = {}
    for width in WIDTHS:
        stats = corridor_stats(fid, geom, profile, width)
        out.update({f"{k}_{_wkey(width)}": v for k, v in stats.items()})
    return out


# --- timing ------------------------------------------------------------------


def _timings(profile: str) -> dict[int, dict]:
    path = LAB / profile / routing.TIMINGS
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        # Last row wins: a resumed or re-run batch appends.
        return {int(r["tour_fid"]): {k: float(v) if v not in ("", None) else np.nan
                                     for k, v in r.items() if k not in ("tour_fid", "engine")}
                for r in csv.DictReader(fh)}


def timing_table() -> None:
    ref = _timings(REF)
    if not ref:
        print(f"  no {REF} timings yet")
        return
    print(f"\nCompute, {len(ref)} tours. Seconds per route; spread = the GRASS "
          f"spreads alone (r.walk's includes negating the DEM).\n")
    print(f"  {'':12s} {'total':>8} {'mean':>6} {'median':>7} {'spread':>7} "
          f"{'line':>6} {'corr':>6} {'other':>6} {'s/Mcell':>8} {'x ref':>6} {'paired':>7}")
    for name in (REF,) + VARIANTS:
        t = _timings(name)
        if not t:
            print(f"  {name:12s} not routed yet")
            continue
        fids = sorted(set(t) & set(ref))
        sec = np.array([t[f]["seconds"] for f in fids])
        col = lambda k: np.nansum([t[f].get(k, np.nan) for f in fids]) / len(fids)
        cells = np.nansum([t[f]["cells"] for f in fids]) / 1e6
        paired = np.median([t[f]["seconds"] / ref[f]["seconds"] for f in fids])
        ref_total = sum(ref[f]["seconds"] for f in fids)
        print(f"  {name:12s} {sec.sum() / 60:6.1f}m {sec.mean():6.1f} {np.median(sec):7.1f} "
              f"{col('spread'):7.2f} {col('line'):6.2f} {col('corridor'):6.2f} "
              f"{col('other'):6.2f} {sec.sum() / cells:8.2f} {sec.sum() / ref_total:6.2f} "
              f"{paired:7.2f}")
    print("  x ref = total over walk_ref's; paired = median of per-tour ratios")


# --- compare -----------------------------------------------------------------


def compare(out_csv: Path) -> None:
    tours = _tours()
    control = _scored(LAB / CONTROL / "routes.gpkg")
    vrt = LAB / CONTROL / "cost_surface.vrt"

    def measure(r, fid):
        return {**steep_metres(r["geom"]), **climb(r["geom"], tours[fid]),
                "ctl_cost": surface_cost(r["geom"], vrt),
                "length_m": r["length_m"], "exp_score": r["exp_score"]}

    base = {fid: measure(r, fid) for fid, r in control.items()}
    rows = [{"profile": CONTROL, "fid": fid, "name": r["name"], "sep_max_m": 0.0,
             **base[fid], **all_widths(fid, r["geom"], CONTROL)}
            for fid, r in control.items()]

    total = lambda key, src: float(np.nansum([v[key] for v in src.values()]))
    exp_km = lambda src: total("exp_score", src) / (total("length_m", src) / 1000.0)
    keys = ("length_m", "climb_m", "reclimb_m", "steep_m", "near10_m", "exp", "ctl_cost")
    heads = ("length", "climb", "re-climb", "on >=30", "<10 m", "exp/km", "ctl cost")

    print(f"\n{len(control)} tours, each engine against {CONTROL} (r.cost, production)\n")
    print(f"  {'':12s} {'moved':>6} {'moved':>6} {'sep':>6}" + "".join(f"{h:>10}" for h in heads))
    print(f"  {'':12s} {'>50 m':>6} {'>250 m':>6} {'median':>6}")
    print(f"  {CONTROL[:12]:12s} {'':>6} {'':>6} {'':>6}"
          f"{total('length_m', base) / 1000:8.1f}km{total('climb_m', base):9.0f}m"
          f"{total('reclimb_m', base):9.0f}m{total('steep_m', base):9.0f}m"
          f"{total('near10_m', base):9.0f}m{exp_km(base):10.2f}{total('ctl_cost', base):10.0f}")

    for name in (REF,) + VARIANTS:
        path = LAB / name / "routes.gpkg"
        if not path.exists():
            print(f"  {name:12s} not routed yet")
            continue
        routes = {k: v for k, v in _scored(path).items() if k in control}
        stats = {}
        for fid, r in routes.items():
            _, max_a = routing.separation(r["geom"], control[fid]["geom"])
            _, max_b = routing.separation(control[fid]["geom"], r["geom"])
            stats[fid] = {**measure(r, fid), "sep_max_m": max(max_a, max_b),
                          **all_widths(fid, r["geom"], name)}
            rows.append({"profile": name, "fid": fid, "name": r["name"], **stats[fid]})
        seps = np.array([v["sep_max_m"] for v in stats.values()])
        ref = {f: base[f] for f in routes}
        change = {k: total(k, stats) / total(k, ref) - 1 for k in keys if k != "exp"}
        change["exp"] = exp_km(stats) / exp_km(ref) - 1
        print(f"  {name:12s} {int((seps >= 50).sum()):>6} {int((seps >= 250).sum()):>6} "
              f"{np.median(seps):5.0f}m" + "".join(f"{change[k]:+10.1%}" for k in keys))

        def updown(key, tol):
            if key == "exp":
                d = np.array([stats[f]["exp_score"] / max(stats[f]["length_m"], 1)
                              - ref[f]["exp_score"] / max(ref[f]["length_m"], 1)
                              for f in stats]) * 1000.0
            else:
                d = np.array([stats[f][key] - ref[f][key] for f in stats])
            return f"{int((d > tol).sum())}/{int((d < -tol).sum())}"
        tols = {"length_m": 10, "climb_m": 10, "reclimb_m": 10, "steep_m": 10,
                "near10_m": 10, "exp": 0.05, "ctl_cost": 10}
        print(f"  {'  up/down':12s} {'':>6} {'':>6} {'':>6}"
              + "".join(f"{updown(k, tols[k]):>10}" for k in keys))

    print("\nCorridors against the control's, per width. area and iou are medians over "
          "tours;\nkm2 are totals - ground only this engine's band holds, and only r.cost's.\n")
    print(f"  {'':12s} {'width':9s} {'area':>6} {'iou':>6} {'total km2':>10} "
          f"{'only own':>9} {'only ctl':>9} {'line in':>8} {'<99%':>5}")
    for name in (CONTROL,) + (REF,) + VARIANTS:
        for width in WIDTHS:
            w = _wkey(width)
            sub = [r for r in rows if r["profile"] == name and f"iou_{w}" in r]
            if not sub:
                continue
            get = lambda k: np.array([r[f"{k}_{w}"] for r in sub])
            print(f"  {name:12s} {w:9s} {np.median(get('area_ratio')):6.2f} "
                  f"{np.median(get('iou')):6.2f} {get('area_km2').sum():10.1f} "
                  f"{get('only_own_km2').sum():9.1f} {get('only_ctl_km2').sum():9.1f} "
                  f"{np.median(get('line_in')):8.1%} {int((get('line_in') < 0.99).sum()):>5}")

    timing_table()

    cols = ["profile", "fid", "name", "length_m", "sep_max_m", "climb_m", "reclimb_m",
            "steep_m", "near10_m", "near20_m", "exp_score", "ctl_cost"] + [
            f"{k}_{_wkey(w)}" for w in WIDTHS
            for k in ("area_km2", "area_ratio", "iou", "only_own_km2", "only_ctl_km2",
                      "line_in")]
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(float(row[k]), 3) if isinstance(row.get(k), (float, np.floating))
                            else row.get(k)) for k in cols})
    print(f"\n  % is the change in the total over the tour set against the control.\n"
          f"  -> {out_csv}")


# --- the r.walk corridor's budget -------------------------------------------


def _walk_costs() -> dict[int, float]:
    return {f: v["cost_opt"] for f, v in _timings("walk").items()}


def _band_mask(gap: np.ndarray, cost_opt: float, params: dict, scale: float) -> np.ndarray:
    max_gap = min(cost_opt * float(params["slack"]), float(params["max_gap"]) * scale)
    return np.isfinite(gap) & (gap <= max_gap)


def _gap(fid: int):
    hits = sorted((LAB / "walk" / "gaps").glob(f"{fid:03d}_*.tif"))
    if not hits:
        return None, None, None
    ds = gdal.Open(str(hits[0]))
    g = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    g[g == np.float32(config.NODATA)] = np.nan
    return g, ds.GetGeoTransform(), hits[0].name


def calibrate(scales: list[float]) -> None:
    """For each max_gap_scale, how the r.walk band compares with r.cost's.

    Two ways to pick one. By units: the median of cost_opt(walk) /
    cost_opt(cost), so the cap buys the same share of a typical trip. By
    result: the scale whose band covers as much ground as r.cost's, tour for
    tour. They need not agree - r.walk spends its budget on climbing too."""
    walk_cost = _walk_costs()
    ctl = {f: r for f, r in _timings(REF).items()}
    ratios = [walk_cost[f] / ctl[f]["cost_opt"] for f in walk_cost if f in ctl]
    print(f"\ncost_opt walk / cost: median {np.median(ratios):.1f}, "
          f"IQR {np.percentile(ratios, 25):.1f}-{np.percentile(ratios, 75):.1f}  "
          f"({len(ratios)} tours)")
    capped = 0
    for f in walk_cost:
        if walk_cost[f] * config.CORRIDOR["slack"] > config.CORRIDOR["max_gap"] * np.median(ratios):
            capped += 1
    print(f"  at that scale the cap, not slack, sets the band on {capped} of {len(walk_cost)}")

    # The control's own: how many tours its cap decides.
    ctl_capped = sum(1 for f in ctl if ctl[f]["cost_opt"] * config.CORRIDOR["slack"]
                     > config.CORRIDOR["max_gap"])
    print(f"  r.cost's cap decides {ctl_capped} of {len(ctl)}")

    print(f"\n  {'scale':>6} {'area walk/ctl':>14} {'iou':>6} {'capped':>7}")
    for s in scales:
        area, iou, cap = [], [], 0
        for fid in walk_cost:
            g, gg, _ = _gap(fid)
            c = _corridor(CONTROL, fid)
            if g is None or c is None:
                continue
            a = _band_mask(g, walk_cost[fid], config.CORRIDOR, s)
            b, gb = _live(c)
            a2, b2 = _on_union(a, gg, b, gb)
            area.append(a2.sum() / max(b2.sum(), 1))
            iou.append((a2 & b2).sum() / max((a2 | b2).sum(), 1))
            cap += walk_cost[fid] * config.CORRIDOR["slack"] > config.CORRIDOR["max_gap"] * s
        print(f"  {s:6.1f} {np.median(area):14.2f} {np.median(iou):6.2f} {cap:7d}")


def recut(scale: float) -> None:
    """Rewrite walk's corridors, every width, from its kept gaps at `scale` -
    what routing would have written with that max_gap_scale."""
    walk_cost = _walk_costs()
    folder = LAB / "walk" / "corridors"
    for fid, cost_opt in sorted(walk_cost.items()):
        g, gt, name = _gap(fid)
        if g is None:
            continue
        for width in (None, *config.CORRIDOR_WIDTHS):
            params = routing._band(config.CORRIDOR, width)
            max_gap = min(cost_opt * float(params["slack"]), float(params["max_gap"]) * scale)
            score = np.where(np.isfinite(g) & (g <= max_gap),
                             np.power(1 - np.nan_to_num(g) / max_gap, float(params["gamma"])),
                             config.NODATA).astype(np.float32)
            out = folder if width is None else routing.width_dir(folder, width)
            src = gdal.Open(str(LAB / "walk" / "gaps" / name))
            dst = gdal.GetDriverByName("GTiff").Create(
                str(out / name), src.RasterXSize, src.RasterYSize, 1, gdal.GDT_Float32,
                options=["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"])
            dst.SetGeoTransform(gt)
            dst.SetProjection(src.GetProjection())
            dst.GetRasterBand(1).SetNoDataValue(config.NODATA)
            dst.GetRasterBand(1).WriteArray(score)
            dst = None
    print(f"re-cut {len(walk_cost)} walk corridors at max_gap_scale {scale}")


# --- arcgis --------------------------------------------------------------------

ARCGIS = LAB / "walk_arcgis"
# (label in ArcGIS, lab profile, style). r.cost's corridors are the control's
# own: walk_ref re-routed them only to time them, and they are the same files.
ENGINES = (("rcost", CONTROL, "green.lyrx"), ("rwalk", "walk", "blue.lyrx"))
DIFF_CLASSES = {1: ("r.cost only", (230, 130, 30, 255)),
                2: ("r.walk only", (40, 120, 220, 255)),
                3: ("both", (150, 150, 150, 255))}


def _tifs(profile: str, width: Optional[str]) -> list[Path]:
    folder = LAB / profile / "corridors"
    if width:
        folder = routing.width_dir(folder, width)
    return sorted(folder.glob("*.tif"))


def _merge_max(out: Path, tifs: list[Path], like) -> None:
    from tests.steep_edge_report import _blank, _finish, _offset

    ds = _blank(out, like, gdal.GDT_Float32, config.NODATA)
    band = ds.GetRasterBand(1)
    for tif in tifs:
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


def _write_diff(out: Path, width: Optional[str], like) -> None:
    """1 where only r.cost's band reaches, 2 only r.walk's, 3 both - over
    every tour, so a cell either engine gives to any tour counts. A colour
    table and a raster attribute table go with it, so ArcGIS opens it styled
    and named."""
    from tests.steep_edge_report import _blank, _finish, _offset

    ds = _blank(out, like, gdal.GDT_Byte, 0)
    band = ds.GetRasterBand(1)
    by_fid = {}
    for bit, (_, profile, _) in zip((1, 2), ENGINES):
        for tif in _tifs(profile, width):
            by_fid.setdefault(tif.name.split("_", 1)[0], {})[bit] = tif
    for pair in by_fid.values():
        for bit, tif in pair.items():
            mask, gt = _live(tif)
            x, y = _offset(ds, gt)
            old = band.ReadAsArray(x, y, mask.shape[1], mask.shape[0])
            band.WriteArray(old | (mask.astype(np.uint8) * bit), x, y)

    table = gdal.ColorTable()
    table.SetColorEntry(0, (0, 0, 0, 0))
    for value, (_, rgba) in DIFF_CLASSES.items():
        table.SetColorEntry(value, rgba)
    band.SetRasterColorTable(table)
    band.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
    rat = gdal.RasterAttributeTable()
    rat.CreateColumn("Value", gdal.GFT_Integer, gdal.GFU_MinMax)
    rat.CreateColumn("Class", gdal.GFT_String, gdal.GFU_Name)
    for i, (value, (name, _)) in enumerate(DIFF_CLASSES.items()):
        rat.SetValueAsInt(i, 0, value)
        rat.SetValueAsString(i, 1, name)
    band.SetDefaultRAT(rat)
    _finish(ds, out)


def _outlines(layer, profile: str, engine: str, width: Optional[str],
              names: dict[int, str], stats: dict) -> None:
    """One (multi)polygon per tour: the band's outer extent, for comparing
    a single tour's two corridors with a definition query."""
    from osgeo import ogr, osr

    mem = ogr.GetDriverByName("MEM").CreateDataSource("")
    for tif in _tifs(profile, width):
        fid = int(tif.name.split("_", 1)[0])
        mask, gt = _live(tif)
        src = gdal.GetDriverByName("MEM").Create("", mask.shape[1], mask.shape[0], 1, gdal.GDT_Byte)
        src.SetGeoTransform(gt)
        src.GetRasterBand(1).WriteArray(mask.astype(np.uint8))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(config.CRS_EPSG)
        tmp = mem.CreateLayer(f"p{fid}", srs, ogr.wkbPolygon)
        tmp.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
        gdal.Polygonize(src.GetRasterBand(1), src.GetRasterBand(1), tmp, 0)
        union = ogr.Geometry(ogr.wkbMultiPolygon)
        for f in tmp:
            union.AddGeometry(f.GetGeometryRef())
        union = union.UnionCascaded()
        # The pair's overlap on both rows: r.cost against itself is always 1.
        s = stats.get(("rwalk", fid), {})
        f = ogr.Feature(layer.GetLayerDefn())
        f.SetField("tour_fid", fid)
        f.SetField("name", names.get(fid, ""))
        f.SetField("engine", engine)
        f.SetField("width", _wkey(width))
        f.SetField("area_km2", round(float(mask.sum()) * (config.PIXEL_SIZE / 1000) ** 2, 3))
        if f"iou_{_wkey(width)}" in s:
            f.SetField("iou", round(float(s[f"iou_{_wkey(width)}"]), 3))
        f.SetGeometry(ogr.ForceToMultiPolygon(union))
        layer.CreateFeature(f)
        mem.DeleteLayer(f"p{fid}")


def _report_rows() -> dict:
    """walk_report.csv by (engine, fid) - run `compare` first."""
    path = LAB / "walk_report.csv"
    if not path.exists():
        raise SystemExit(f"No {path}. Run 'compare' first.")
    label = {CONTROL: "rcost", "walk": "rwalk"}
    out = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["profile"] in label:
                out[(label[r["profile"]], int(r["fid"]))] = r
    return out


def export_arcgis(*, rasters: bool = True) -> None:
    """Everything ArcGIS needs to lay r.cost's corridors against r.walk's, in
    data/test/lab/walk_arcgis/:

      cost_surface.tif          the surface both engines routed on, + .lyrx
      corridors_<engine>_<width>.tif   every tour's band, overlaps MAXed, + .lyrx
                                (r.cost green, r.walk blue)
      corridor_diff_<width>.tif 1 r.cost only, 2 r.walk only, 3 both;
                                opens coloured, classes named
      compare.gpkg
        routes                  both engines' lines, field `engine`, with the
                                scorecard and seconds per route
        corridor_outlines       one polygon per tour, engine and width -
                                filter on tour_fid to compare one tour
    """
    import os
    import shutil

    from osgeo import ogr, osr

    from tests.steep_edge_report import _lyrx

    ARCGIS.mkdir(parents=True, exist_ok=True)
    print(f"-> {ARCGIS}")
    stats = _report_rows()

    if rasters:
        # A hard link: 180 MB that is already on disk, and the same file.
        src = LAB / "steep_edge_arcgis" / "cost_steep_edge_control.tif"
        dst = ARCGIS / "cost_surface.tif"
        if src.exists() and not dst.exists():
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        if dst.exists():
            _lyrx("cost_surface.tif.lyrx", dst)
            print(f"  {dst.name}")
        else:
            print(f"  no {src} - run 'tests.steep_edge_report arcgis' for the surface")

        like = gdal.Open(str(LAB / CONTROL / "cost_surface.vrt"))
        for width in WIDTHS:
            for engine, profile, style in ENGINES:
                out = ARCGIS / f"corridors_{engine}_{_wkey(width)}.tif"
                _merge_max(out, _tifs(profile, width), like)
                _lyrx(style, out)
            _write_diff(ARCGIS / f"corridor_diff_{_wkey(width)}.tif", width, like)

    out = ARCGIS / "compare.gpkg"
    try:
        out.unlink(missing_ok=True)
    except PermissionError:
        import time
        out = ARCGIS / f"compare_{time.strftime('%H%M')}.gpkg"
        print(f"  compare.gpkg is open elsewhere - writing {out.name} instead")
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(out))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)

    seconds = {"rcost": _timings(REF), "rwalk": _timings("walk")}
    fields = ["length_m", "sep_max_m", "climb_m", "reclimb_m", "steep_m", "near10_m",
              "exp_score", "ctl_cost"] + [f"{k}_{_wkey(w)}" for w in WIDTHS
                                          for k in ("area_km2", "iou", "line_in")]
    layer = ds.CreateLayer("routes", srs, ogr.wkbLineString)
    for name, kind in (("tour_fid", ogr.OFTInteger), ("name", ogr.OFTString),
                       ("engine", ogr.OFTString), ("seconds", ogr.OFTReal),
                       ("cost_opt", ogr.OFTReal)):
        layer.CreateField(ogr.FieldDefn(name, kind))
    for name in fields:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTReal))
    names = {}
    layer.StartTransaction()
    for engine, profile, _ in ENGINES:
        src = ogr.Open(str(LAB / profile / "routes.gpkg"))
        for feat in src.GetLayerByName(routing.ROUTES_LAYER):
            fid = feat.GetField("tour_fid")
            names[fid] = feat.GetField("name") or ""
            f = ogr.Feature(layer.GetLayerDefn())
            f.SetField("tour_fid", fid)
            f.SetField("name", names[fid])
            f.SetField("engine", engine)
            f.SetField("cost_opt", feat.GetField("cost_opt"))
            t = seconds[engine].get(fid)
            if t:
                f.SetField("seconds", round(t["seconds"], 2))
            row = stats.get((engine, fid), {})
            for name in fields:
                if row.get(name) not in (None, ""):
                    f.SetField(name, float(row[name]))
            f.SetGeometry(feat.GetGeometryRef())
            layer.CreateFeature(f)
    layer.CommitTransaction()
    print(f"  {out.name}: routes")

    outlines = ds.CreateLayer("corridor_outlines", srs, ogr.wkbMultiPolygon)
    for name, kind in (("tour_fid", ogr.OFTInteger), ("name", ogr.OFTString),
                       ("engine", ogr.OFTString), ("width", ogr.OFTString),
                       ("area_km2", ogr.OFTReal), ("iou", ogr.OFTReal)):
        outlines.CreateField(ogr.FieldDefn(name, kind))
    outlines.StartTransaction()
    for width in WIDTHS:
        for engine, profile, _ in ENGINES:
            _outlines(outlines, profile, engine, width, names, stats)
    outlines.CommitTransaction()
    ds = None
    print(f"  {out.name}: corridor_outlines")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m tests.walk_report")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("compare", help="time, lines and corridors against the control")
    s.add_argument("--out", type=Path, default=LAB / "walk_report.csv")
    s = sub.add_parser("calibrate", help="what max_gap_scale matches r.cost's band")
    s.add_argument("--scale", type=float, action="append", dest="scales")
    s = sub.add_parser("recut", help="rewrite walk's corridors at another max_gap_scale")
    s.add_argument("--scale", type=float, required=True)
    s = sub.add_parser("arcgis", help="both engines' corridors and routes as files ArcGIS reads")
    s.add_argument("--vectors-only", action="store_true", help="just compare.gpkg")
    args = p.parse_args(argv)
    if args.cmd == "compare":
        compare(args.out)
    elif args.cmd == "arcgis":
        export_arcgis(rasters=not args.vectors_only)
    elif args.cmd == "calibrate":
        calibrate(args.scales or [5, 10, 15, 20, 25, 30, 40])
    else:
        recut(args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
