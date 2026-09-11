"""Start/end pairs to route through the cost surface.

A tour is digitized as a two-vertex line: click the start, double-click the
summit. The pairing is the geometry, so there are no ids to keep in step and
no way to orphan half a pair - which matters at several hundred routes.
Extra vertices are allowed and ignored; only the first and last are used, so
a line dragged out to show intent still routes start to end.

Everything is EPSG:25833, the same grid as the cost surface. Digitizing in
another CRS means reprojecting every endpoint, and the rounding lands
exactly where it decides which 10 m pixel a trailhead snaps to.

Any OGR-readable source works - GeoPackage, File Geodatabase, shapefile -
so the choice of editor does not lock anything in.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, ogr, osr

from skimap import config, paths

gdal.UseExceptions()
ogr.UseExceptions()

LAYER = "tours"

# One field, on purpose: at several hundred routes every extra column is
# several hundred more things to type, and anything derivable - length, cost,
# which tile it falls in - is derived rather than typed. Extra fields added
# later in ArcGIS are simply ignored here, so adding one breaks nothing.
FIELDS = (
    ("name", ogr.OFTString, 120),   # what you are climbing
)


@dataclass(frozen=True)
class Tour:
    fid: int
    name: str
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def straight_km(self) -> float:
        return float(np.hypot(self.end[0] - self.start[0],
                              self.end[1] - self.start[1]) / 1000.0)

    @property
    def label(self) -> str:
        return self.name or f"tour_{self.fid}"


def create_template(out_path: Optional[Path] = None, *, overwrite: bool = False) -> Path:
    """An empty line layer to digitize into.

    Refuses to overwrite by default: this file is hand-made work and there is
    nothing to rebuild it from.
    """
    out_path = Path(out_path) if out_path else paths.TOURS
    if out_path.exists() and not overwrite:
        raise FileExistsError(
            f"{out_path} already exists and holds digitized work. "
            "Pass overwrite=True only if you are certain."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        ogr.GetDriverByName("GPKG").DeleteDataSource(str(out_path))

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)

    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(out_path))
    layer = ds.CreateLayer(LAYER, srs, ogr.wkbLineString)
    for name, kind, width in FIELDS:
        defn = ogr.FieldDefn(name, kind)
        if kind == ogr.OFTString:
            defn.SetWidth(width)
        layer.CreateField(defn)
    ds = None

    print(f"Wrote empty tour layer -> {out_path}")
    print(f"  EPSG:{config.CRS_EPSG}, LineString, "
          f"fields: {', '.join(f[0] for f in FIELDS)}")
    return out_path


def import_json(src: Path, out_path: Optional[Path] = None, *, overwrite: bool = False) -> Path:
    """Bring the older `{"crs": ..., "areas": {area: [{name, start, end}]}}`
    format into a tour layer.

    The pre-skimap tours lived one JSON per project, grouped by study area,
    with `start`/`end` as [x, y] pairs already in the file's own `crs`. This
    flattens that into the same LineString-plus-name layer everything else
    here reads, so tours drawn before this schema existed do not have to be
    re-digitized. The area grouping is dropped on the way in: nothing
    downstream needs it, since a tour is routed from its own geometry.
    """
    import json

    out_path = Path(out_path) if out_path else paths.TOURS
    if out_path.exists() and not overwrite:
        raise FileExistsError(
            f"{out_path} already exists and may hold digitized work. "
            "Pass overwrite=True only if you are certain."
        )

    data = json.loads(Path(src).read_text(encoding="utf-8"))
    src_epsg = int(str(data["crs"]).split(":")[-1])
    if src_epsg != config.CRS_EPSG:
        raise ValueError(
            f"{src} is EPSG:{src_epsg}, this project is EPSG:{config.CRS_EPSG}. "
            "Reproject the source before importing rather than silently here - "
            "a bulk import is exactly where a quiet CRS mismatch would be missed."
        )

    create_template(out_path, overwrite=overwrite)
    ds = ogr.Open(str(out_path), 1)
    lyr = ds.GetLayerByName(LAYER)

    n = 0
    for area, entries in data["areas"].items():
        for entry in entries:
            feat = ogr.Feature(lyr.GetLayerDefn())
            feat.SetField("name", str(entry["name"]))
            line = ogr.Geometry(ogr.wkbLineString)
            line.AddPoint_2D(*entry["start"])
            line.AddPoint_2D(*entry["end"])
            feat.SetGeometry(line)
            lyr.CreateFeature(feat)
            n += 1
    ds = None

    print(f"Imported {n} tours from {len(data['areas'])} areas -> {out_path}")
    return out_path


def read_tours(path: Optional[Path] = None, *, layer: Optional[str] = None) -> list[Tour]:
    """Read digitized lines as start/end pairs.

    Reprojects a source in another CRS rather than refusing it - better to
    take the small hit than to lose an afternoon of digitizing to a feature
    class that was created with the wrong spatial reference.
    """
    path = Path(path) if path else paths.TOURS
    ds = ogr.Open(str(path))
    if ds is None:
        raise FileNotFoundError(f"Could not open {path}")
    lyr = ds.GetLayerByName(layer) if layer else ds.GetLayerByIndex(0)
    if lyr is None:
        raise KeyError(f"No layer {layer!r} in {path}")

    target = osr.SpatialReference()
    target.ImportFromEPSG(config.CRS_EPSG)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    source = lyr.GetSpatialRef()
    transform = None
    if source is not None and not source.IsSame(target):
        source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        print(f"NOTE: reprojecting from {source.GetName()} to EPSG:{config.CRS_EPSG}")
        transform = osr.CoordinateTransformation(source, target)

    defn = lyr.GetLayerDefn()
    have = {defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())}

    out: list[Tour] = []
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        # A single-part multiline is still one line; ArcGIS sometimes writes
        # them that way depending on how the feature class was created.
        if geom.GetGeometryName().startswith("MULTILINE"):
            if geom.GetGeometryCount() == 0:
                continue
            geom = geom.GetGeometryRef(0)
        if transform is not None:
            geom = geom.Clone()
            geom.Transform(transform)

        n = geom.GetPointCount()
        if n < 2:
            print(f"  skipping fid {feat.GetFID()}: {n} vertices, need at least 2")
            continue

        name = ""
        if "name" in have:
            value = feat.GetField("name")
            name = "" if value is None else str(value)

        out.append(Tour(
            fid=feat.GetFID(),
            name=name,
            start=(geom.GetX(0), geom.GetY(0)),
            end=(geom.GetX(n - 1), geom.GetY(n - 1)),
        ))
    ds = None
    return out


def sample_cost(points: list[tuple[float, float]]) -> np.ndarray:
    """Cost surface value under each point; COST_NODATA where off the map."""
    ds = gdal.Open(str(paths.national_surface()))
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)

    out = np.full(len(points), float(config.COST_NODATA))
    for i, (x, y) in enumerate(points):
        px = int((x - gt[0]) / gt[1])
        py = int((y - gt[3]) / gt[5])
        if 0 <= px < ds.RasterXSize and 0 <= py < ds.RasterYSize:
            out[i] = float(band.ReadAsArray(px, py, 1, 1)[0, 0])
    ds = None
    return out


def nearest_walkable(x: float, y: float, *, radius_m: float = 200.0
                     ) -> Optional[tuple[float, float, float]]:
    """Closest cell below BARRIER_COST within `radius_m`, as (x, y, cost).

    A trailhead clicked a few metres into a fjord, or onto the cliff pixel
    beside a road, sits on a barrier and has no route out of it. This reports
    where the nearest usable cell is rather than moving the point silently -
    which of the two is correct is a judgement about the terrain.
    """
    ds = gdal.Open(str(paths.national_surface()))
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)

    r = int(radius_m / config.PIXEL_SIZE)
    px = int((x - gt[0]) / gt[1])
    py = int((y - gt[3]) / gt[5])
    x0, y0 = max(px - r, 0), max(py - r, 0)
    x1, y1 = min(px + r + 1, ds.RasterXSize), min(py + r + 1, ds.RasterYSize)
    if x1 <= x0 or y1 <= y0:
        ds = None
        return None

    win = band.ReadAsArray(x0, y0, x1 - x0, y1 - y0).astype(np.float64)
    ds = None

    ok = (win < config.BARRIER_COST) & (win != config.COST_NODATA)
    if not ok.any():
        return None
    ys, xs = np.nonzero(ok)
    d = np.hypot((x0 + xs) - px, (y0 + ys) - py)
    i = int(np.argmin(d))
    if d[i] * config.PIXEL_SIZE > radius_m:
        return None
    return (float(gt[0] + (x0 + xs[i] + 0.5) * gt[1]),
            float(gt[3] + (y0 + ys[i] + 0.5) * gt[5]),
            float(win[ys[i], xs[i]]))


def check(tours: list[Tour], *, min_km: float = 0.1) -> list[str]:
    """Report tours that cannot route, before a batch spends hours finding out.

    Returns the problems; an empty list means every tour is usable.
    """
    if not tours:
        print("No tours found.")
        return ["no tours"]

    starts = sample_cost([t.start for t in tours])
    ends = sample_cost([t.end for t in tours])
    problems: list[str] = []

    for t, c_start, c_end in zip(tours, starts, ends):
        for role, cost, xy in (("start", c_start, t.start), ("end", c_end, t.end)):
            if cost == config.COST_NODATA:
                problems.append(f"fid {t.fid} ({t.label}): {role} is outside the cost surface")
            elif cost >= config.BARRIER_COST:
                fix = nearest_walkable(*xy)
                where = (f", nearest walkable ground is "
                         f"{np.hypot(fix[0] - xy[0], fix[1] - xy[1]):.0f} m away"
                         if fix else ", nothing walkable within 200 m")
                problems.append(f"fid {t.fid} ({t.label}): {role} is on a barrier{where}")
        if t.straight_km < min_km:
            problems.append(
                f"fid {t.fid} ({t.label}): start and end are only "
                f"{t.straight_km * 1000:.0f} m apart"
            )

    lengths = np.array([t.straight_km for t in tours])
    on_map = starts != config.COST_NODATA
    print(f"{len(tours)} tours")
    print(f"  straight-line km: median {np.median(lengths):.1f}, "
          f"min {lengths.min():.1f}, max {lengths.max():.1f}")
    print(f"  unnamed: {sum(1 for t in tours if not t.name)}")
    if on_map.any():
        print(f"  cost at start: median {np.median(starts[on_map]):.0f}")
        print(f"  cost at end:   median {np.median(ends[on_map]):.0f}")
    print(f"  distinct trailheads: {len({t.start for t in tours})}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for line in problems:
            print(f"  {line}")
    else:
        print("\nEvery tour starts and ends on walkable ground.")
    return problems
