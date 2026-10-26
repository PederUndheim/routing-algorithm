"""From the review's verdicts to the final, renumbered corridor set.

Per tour the review settled on one model's corridor at one width. This
takes exactly that file - nothing is re-routed or re-cut - merges the tours
that are pieces of one corridor (see chains.py), files each corridor under
its forecast region (regions.py) and numbers them 1..N: region by region in
NVE's order, north to south by summit within a region.

What lands in data/corridors_final/:

    corridors/0001.tif     every corridor, one file each in this one folder,
                           cropped to its band. The id, region and old tour
                           fids are in its GeoTIFF metadata too, so a file
                           copied out on its own still says what it is
    corridors_all.tif      all of them as one raster, overlaps taking the max
                           (routing.merge_corridors) - to see the country at once
    corridors_final.gpkg   corridors  footprint polygon per corridor, every
                                      attribute, `location` = its .tif,
                                      relative to this folder
                           routes     the route line(s) behind each corridor
                           id_map     new id <-> old tour fid, one row per
                                      piece, and a row with no id for every
                                      tour that did not make it in, and why
                           regions    the polygons, ranked, with id ranges
    id_map.csv             id_map for a spreadsheet
    build.json             what the build was made from, and what was left out

No names: a corridor is its id. The old names stay findable in id_map.

The tif stays a file per corridor rather than a raster table in the
GeoPackage. A GPKG can hold rasters, but one table per corridor is a
thousand layers, a Float32 tile table is an extension ArcGIS does not read,
and a tif per corridor is what everything downstream already reads. The
gpkg is the index over them instead. ArcGIS' own index of rasters, a mosaic
dataset, needs a Standard licence; this machine's is Basic (tested
2026-10-26: CreateMosaicDataset "not licensed"), so corridors_all.tif is
the view of all of them and the footprints are what you click.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
from osgeo import gdal, ogr, osr

from skimap import config, paths, routing, tours as tours_module
from skimap.corridor_review import models as models_module, sources
from skimap.corridor_review.store import LADDER, Store, made_in, verdict_width
from skimap.corridors_final import chains, regions as regions_module

gdal.UseExceptions()
ogr.UseExceptions()

NODATA = config.NODATA
GPKG = "corridors_final.gpkg"
ALL = "corridors_all.tif"
CSV = "id_map.csv"
SUMMARY = "build.json"
TIF_DIR = "corridors"
# Every name `write` owns. A rebuild deletes these and nothing else, so
# merges.json and anything you put beside it survive. corridors_final.gti
# was written by the first version; listed so a rebuild clears it.
OUTPUTS = (TIF_DIR, ALL, GPKG, CSV, SUMMARY, "corridors_final.gti")


@dataclass(frozen=True)
class Part:
    """One tour as the review settled it."""
    tour: tours_module.Tour
    verdict: dict[str, Any]
    width: str
    corridor: Path
    route_wkb: bytes

    @property
    def fid(self) -> int:
        return self.tour.fid

    @property
    def route(self) -> ogr.Geometry:
        return ogr.CreateGeometryFromWkb(self.route_wkb)


@dataclass
class Corridor:
    group: chains.Group
    parts: tuple[Part, ...]
    region: regions_module.Region
    id: int = 0
    seq: int = 0        # its place within the region, from 1

    @property
    def colour(self) -> str:
        """The most severe class among its pieces: a tour is as exposed as
        the worst stretch on it."""
        known = [p.verdict["colour"] for p in self.parts if p.verdict["colour"] in LADDER]
        return max(known, key=LADDER.index) if known else ""

    @property
    def summit(self) -> tuple[float, float]:
        return self.parts[-1].tour.end

    @property
    def fids(self) -> tuple[int, ...]:
        return tuple(p.fid for p in self.parts)


@dataclass
class Build:
    corridors: list[Corridor]
    regions: list[regions_module.Region]
    plan: chains.Plan
    tours: dict[int, tours_module.Tour]
    verdicts: dict[int, dict[str, Any]]
    problems: dict[int, str]            # fid -> why it has no corridor
    left_out: dict[int, str]            # fid -> why, incl. pieces of a broken group
    pending: list[int]                  # not yet reviewed this round
    review_round: int
    decisions: chains.Decisions
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (self.problems or self.pending or self.plan.unresolved)


def prepare(*, regions_path: Optional[Path] = None,
            merges_path: Optional[Path] = None) -> Build:
    """Everything `write` needs, decided and numbered, with nothing written."""
    review_config = models_module.load()
    store = Store()
    tour_list = tours_module.read_tours(paths.TOURS)
    tours = {t.fid: t for t in tour_list}

    decisions = chains.load_decisions(Path(merges_path or paths.CORRIDOR_MERGES))
    plan = chains.plan({t.fid: (t.start, t.end) for t in tour_list}, decisions)

    parts, problems = _gather(review_config, store, tours)
    live = set(tours)
    pending = sorted(live - set(store.reviewed_this_round(live)))

    all_regions = regions_module.load(Path(regions_path or paths.FORECAST_REGIONS))
    assign = regions_module.Assigner(all_regions)

    corridors: list[Corridor] = []
    left_out = dict(problems)
    for group in plan.groups:
        missing = [f for f in group.fids if f not in parts]
        if missing:
            for fid in group.fids:
                if fid not in missing:
                    left_out.setdefault(
                        fid, f"merged with {missing}, which has no corridor")
            continue
        members = tuple(parts[f] for f in group.fids)
        region = assign.by_length(p.route for p in members)
        corridors.append(Corridor(group, members, region))

    # Region order, then north to south by summit, then west to east; the
    # first tour's fid only breaks a tie between two corridors to one top.
    corridors.sort(key=lambda c: (c.region.rank, -c.summit[1], c.summit[0], c.fids))
    per_region: dict[int, int] = {}
    for number, corridor in enumerate(corridors, start=1):
        corridor.id = number
        corridor.seq = per_region[corridor.region.rank] = (
            per_region.get(corridor.region.rank, 0) + 1)

    return Build(corridors=corridors, regions=all_regions, plan=plan,
                 tours=tours, verdicts=store.current(live), problems=problems,
                 left_out=left_out, pending=pending, review_round=store.round,
                 decisions=decisions, warnings=list(plan.warnings))


def _gather(review_config, store: Store, tours: dict[int, tours_module.Tour]
            ) -> tuple[dict[int, Part], dict[int, str]]:
    """fid -> its Part, and fid -> why there is none."""
    corridor_files: dict[tuple[str, str], dict[int, Path]] = {}
    routes: dict[str, dict[int, bytes]] = {}
    parts: dict[int, Part] = {}
    problems: dict[int, str] = {}

    for fid, tour in sorted(tours.items()):
        verdict = store.get(fid)
        if verdict is None:
            problems[fid] = "no verdict"
            continue
        model = review_config.model(verdict["model"])
        if model is None:
            problems[fid] = f"model {verdict['model']!r} not in the review config"
            continue
        width = verdict_width(verdict)
        key = (model.name, width)
        if key not in corridor_files:
            corridor_files[key] = sources.corridor_paths(model, width)
        corridor = corridor_files[key].get(fid)
        if corridor is None:
            problems[fid] = f"no {width} corridor in {model.name}"
            continue
        if model.name not in routes:
            routes[model.name] = _read_routes(model.routes)
        route = routes[model.name].get(fid)
        if route is None:
            problems[fid] = f"no route in {model.name}"
            continue
        parts[fid] = Part(tour, verdict, width, corridor, route)
    return parts, problems


def _read_routes(path: Path) -> dict[int, bytes]:
    """tour_fid -> route line as WKB, for a whole routes.gpkg in one pass."""
    datasource = ogr.Open(str(path))
    layer = datasource.GetLayer(0)
    out: dict[int, bytes] = {}
    for feature in layer:
        fid = feature.GetField("tour_fid")
        geometry = feature.GetGeometryRef()
        if fid is None or geometry is None or geometry.GetPointCount() < 2:
            continue
        geometry = geometry.Clone()
        geometry.FlattenTo2D()
        out[int(fid)] = geometry.ExportToWkb()
    datasource = None
    return out


# --- rasters ----------------------------------------------------------------

def merge_rasters(files: Sequence[Path]) -> tuple[np.ndarray, tuple, str]:
    """The pieces' corridors on one grid, cropped to where any has data.

    Where pieces overlap - at the junction, and along a shared approach -
    the higher score wins, so the merged band is each piece's band and
    nothing in between is invented. Every input is on the national lattice
    (config.RASTER_ORIGIN), so pasting is whole cells, never resampling.
    """
    pieces = []
    pixel = projection = None
    for path in files:
        dataset = gdal.Open(str(path))
        band = dataset.GetRasterBand(1)
        values = band.ReadAsArray().astype(np.float32)
        nodata = band.GetNoDataValue()
        valid = np.isfinite(values)
        if nodata is not None:
            valid &= values != nodata
        transform = dataset.GetGeoTransform()
        if pixel is None:
            pixel, projection = (transform[1], transform[5]), dataset.GetProjection()
        elif (transform[1], transform[5]) != pixel:
            raise ValueError(f"{path.name}: pixel size {transform[1]} differs")
        dataset = None
        rows, cols = np.flatnonzero(valid.any(axis=1)), np.flatnonzero(valid.any(axis=0))
        if not rows.size:
            continue
        r0, r1, c0, c1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
        crop = np.where(valid[r0:r1, c0:c1], values[r0:r1, c0:c1], NODATA)
        if (crop[crop != NODATA] < NODATA).any():
            raise ValueError(f"{path.name}: values below nodata, max() would hide them")
        pieces.append((transform[0] + c0 * pixel[0], transform[3] + r0 * pixel[1], crop))
    if not pieces:
        raise ValueError(f"no data in {[p.name for p in files]}")

    width, height = pixel[0], -pixel[1]
    left = min(x for x, _, _ in pieces)
    top = max(y for _, y, _ in pieces)
    right = max(x + a.shape[1] * width for x, _, a in pieces)
    bottom = min(y - a.shape[0] * height for _, y, a in pieces)
    out = np.full((int(round((top - bottom) / height)), int(round((right - left) / width))),
                  NODATA, dtype=np.float32)
    for x, y, crop in pieces:
        col, row = (x - left) / width, (top - y) / height
        if abs(col - round(col)) > 1e-6 or abs(row - round(row)) > 1e-6:
            raise ValueError("corridors are not on one lattice")
        window = out[int(round(row)):int(round(row)) + crop.shape[0],
                     int(round(col)):int(round(col)) + crop.shape[1]]
        np.maximum(window, crop, out=window)
    return out, (left, width, 0.0, top, 0.0, -height), projection


def write_tif(path: Path, values: np.ndarray, transform: tuple, projection: str,
              tags: dict[str, str], description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset = gdal.GetDriverByName("GTiff").Create(
        str(path), values.shape[1], values.shape[0], 1, gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"])
    dataset.SetGeoTransform(transform)
    dataset.SetProjection(projection)
    dataset.SetMetadata(tags)
    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    band.SetDescription(description)
    band.WriteArray(values)
    dataset = None


def footprint(values: np.ndarray, transform: tuple, projection: str) -> ogr.Geometry:
    """Where the corridor has data, as one multipolygon in map units."""
    mask_ds = gdal.GetDriverByName("MEM").Create("", values.shape[1], values.shape[0],
                                                 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(transform)
    mask_ds.SetProjection(projection)
    band = mask_ds.GetRasterBand(1)
    band.WriteArray((values != NODATA).astype(np.uint8))

    vector = gdal.GetDriverByName("MEM").Create("", 0, 0, 0, gdal.GDT_Unknown)
    layer = vector.CreateLayer("footprint", geom_type=ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    gdal.Polygonize(band, band, layer, 0)   # band as its own mask: 0 is outside
    multi = ogr.Geometry(ogr.wkbMultiPolygon)
    for feature in layer:
        multi.AddGeometry(feature.GetGeometryRef())
    return multi


def join_routes(corridor: Corridor) -> ogr.Geometry:
    """One line through the pieces where they form a path, else all of them."""
    lines = [p.route for p in corridor.parts]
    if len(lines) == 1:
        return lines[0]
    if not corridor.group.path:
        multi = ogr.Geometry(ogr.wkbMultiLineString)
        for line in lines:
            multi.AddGeometry(line)
        return multi
    joined = ogr.Geometry(ogr.wkbLineString)
    for line in lines:
        points = line.GetPoints()
        if joined.GetPointCount() and points and points[0][:2] == joined.GetPoint_2D(
                joined.GetPointCount() - 1):
            points = points[1:]
        for x, y, *_ in points:
            joined.AddPoint_2D(x, y)
    return joined


# --- writing ------------------------------------------------------------------

def write(build: Build, out_dir: Optional[Path] = None, *,
          verbose: bool = True) -> Path:
    out_dir = Path(out_dir) if out_dir else paths.CORRIDORS_FINAL
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUTS:
        target = out_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    datasource = ogr.GetDriverByName("GPKG").CreateDataSource(str(out_dir / GPKG))
    corridor_layer = _layer(datasource, "corridors", srs, ogr.wkbMultiPolygon, CORRIDOR_FIELDS)
    all_paths = all(c.group.path for c in build.corridors)
    route_layer = _layer(datasource, "routes", srs,
                         ogr.wkbLineString if all_paths else ogr.wkbUnknown, ROUTE_FIELDS)

    # One transaction for the file: a GeoPackage allows no more, and a
    # thousand small commits are what makes writing one slow.
    datasource.StartTransaction()
    for done, corridor in enumerate(build.corridors, start=1):
        location = f"{TIF_DIR}/{corridor.id:04d}.tif"
        values, transform, projection = merge_rasters([p.corridor for p in corridor.parts])
        write_tif(out_dir / location, values, transform, projection,
                  _tags(corridor), f"corridor_{corridor.id:04d}")

        attributes = _corridor_attributes(corridor)
        feature = ogr.Feature(corridor_layer.GetLayerDefn())
        for name, value in {**attributes, "location": location}.items():
            if value is not None:
                feature.SetField(name, value)
        feature.SetGeometry(footprint(values, transform, projection))
        corridor_layer.CreateFeature(feature)

        feature = ogr.Feature(route_layer.GetLayerDefn())
        for name, _ in ROUTE_FIELDS:
            if attributes[name] is not None:
                feature.SetField(name, attributes[name])
        feature.SetGeometry(join_routes(corridor))
        route_layer.CreateFeature(feature)
        if verbose and done % 100 == 0:
            print(f"  {done} / {len(build.corridors)} corridors written")
    datasource.CommitTransaction()

    rows = id_map_rows(build)
    id_layer = _layer(datasource, "id_map", None, ogr.wkbNone, ID_MAP_FIELDS)
    datasource.StartTransaction()
    for row in rows:
        feature = ogr.Feature(id_layer.GetLayerDefn())
        for name, value in row.items():
            if value is not None:
                feature.SetField(name, value)
        id_layer.CreateFeature(feature)
    datasource.CommitTransaction()

    _write_regions(datasource, srs, build)
    datasource = None

    with open(out_dir / CSV, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=[n for n, _ in ID_MAP_FIELDS])
        writer.writeheader()
        writer.writerows(rows)

    tifs = sorted((out_dir / TIF_DIR).glob("*.tif"))
    if len(tifs) != len(build.corridors):
        raise RuntimeError(f"{len(tifs)} tifs in {TIF_DIR}/ for "
                           f"{len(build.corridors)} corridors")
    routing.merge_corridors(out_path=out_dir / ALL, files=tifs)

    (out_dir / SUMMARY).write_text(json.dumps(summary(build), indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    return out_dir

CORRIDOR_FIELDS = (
    ("corridor_id", ogr.OFTInteger),
    ("region_id", ogr.OFTInteger),      # NVE omrID; null for "other"
    ("region", ogr.OFTString),
    ("region_kind", ogr.OFTString),     # A forecast, B not
    ("region_seq", ogr.OFTInteger),     # 1.. within its region
    ("n_parts", ogr.OFTInteger),
    ("tour_fids", ogr.OFTString),       # the old ids, start piece first
    ("merge", ogr.OFTString),           # single, auto or merge (merges.json)
    ("colour", ogr.OFTString),          # most severe of its pieces
    ("colours", ogr.OFTString),         # per piece, as reviewed
    ("models", ogr.OFTString),
    ("widths", ogr.OFTString),
    ("length_m", ogr.OFTReal),          # of the route(s)
    ("location", ogr.OFTString),        # its .tif, relative to the gpkg
)
ROUTE_FIELDS = tuple(f for f in CORRIDOR_FIELDS
                     if f[0] in ("corridor_id", "region_id", "tour_fids", "colour",
                                 "length_m"))
ID_MAP_FIELDS = (
    ("corridor_id", ogr.OFTInteger),    # empty: the tour is in no corridor
    ("part", ogr.OFTInteger),           # its place in the corridor, from 1
    ("tour_fid", ogr.OFTInteger),       # fid in tours.gpkg
    ("old_name", ogr.OFTString),
    ("old_file", ogr.OFTString),        # the corridor file the review picked
    ("model", ogr.OFTString),
    ("width", ogr.OFTString),
    ("colour", ogr.OFTString),
    ("colour_computed", ogr.OFTString),
    ("shift", ogr.OFTInteger),
    ("review_round", ogr.OFTInteger),
    ("review_note", ogr.OFTString),
    ("merge", ogr.OFTString),
    ("status", ogr.OFTString),          # ok, or why it has no corridor
)


def _layer(datasource, name: str, srs, kind, fields) -> ogr.Layer:
    layer = datasource.CreateLayer(name, srs, kind)
    for field_name, field_type in fields:
        layer.CreateField(ogr.FieldDefn(field_name, field_type))
    return layer


def _corridor_attributes(corridor: Corridor) -> dict[str, Any]:
    region = corridor.region
    return {
        "corridor_id": corridor.id,
        "region_id": region.id,
        "region": region.name,
        "region_kind": region.kind,
        "region_seq": corridor.seq,
        "n_parts": len(corridor.parts),
        "tour_fids": ",".join(str(f) for f in corridor.fids),
        "merge": corridor.group.how,
        "colour": corridor.colour,
        "colours": ",".join(p.verdict["colour"] for p in corridor.parts),
        "models": ",".join(p.verdict["model"] for p in corridor.parts),
        "widths": ",".join(p.width for p in corridor.parts),
        "length_m": round(sum(p.route.Length() for p in corridor.parts), 1),
    }


def _tags(corridor: Corridor) -> dict[str, str]:
    attributes = _corridor_attributes(corridor)
    keep = ("corridor_id", "region_id", "region", "tour_fids", "colour", "models",
            "widths")
    return {k.upper(): "" if attributes[k] is None else str(attributes[k]) for k in keep}


def id_map_rows(build: Build) -> list[dict[str, Any]]:
    """One row per piece of every corridor, then one per tour left out."""
    rows = []
    for corridor in build.corridors:
        for number, part in enumerate(corridor.parts, start=1):
            rows.append(_id_row(build, part.fid, corridor.id, number,
                                corridor.group.how, "ok", part))
    for fid, why in sorted(build.left_out.items()):
        rows.append(_id_row(build, fid, None, None, None, why, None))
    return rows


def _id_row(build: Build, fid: int, corridor_id, part_no, how, status,
            part: Optional[Part]) -> dict[str, Any]:
    verdict = build.verdicts.get(fid) or {}
    tour = build.tours[fid]
    return {
        "corridor_id": corridor_id,
        "part": part_no,
        "tour_fid": fid,
        "old_name": tour.name,
        "old_file": part.corridor.name if part else None,
        "model": verdict.get("model"),
        "width": verdict_width(verdict) if verdict else None,
        "colour": verdict.get("colour"),
        "colour_computed": verdict.get("colour_computed"),
        "shift": verdict.get("shift"),
        "review_round": made_in(verdict) if verdict else None,
        "review_note": verdict.get("note") or None,
        "merge": how,
        "status": status,
    }


def _write_regions(datasource, srs, build: Build) -> None:
    layer = _layer(datasource, "regions", srs, ogr.wkbMultiPolygon, (
        ("region_rank", ogr.OFTInteger), ("region_id", ogr.OFTInteger),
        ("region", ogr.OFTString), ("region_kind", ogr.OFTString),
        ("n_corridors", ogr.OFTInteger), ("first_id", ogr.OFTInteger),
        ("last_id", ogr.OFTInteger)))
    datasource.StartTransaction()
    for region in build.regions:
        ids = [c.id for c in build.corridors if c.region.rank == region.rank]
        if region.id is None and not ids:
            continue
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("region_rank", region.rank)
        if region.id is not None:
            feature.SetField("region_id", region.id)
        feature.SetField("region", region.name)
        feature.SetField("region_kind", region.kind)
        feature.SetField("n_corridors", len(ids))
        if ids:
            feature.SetField("first_id", min(ids))
            feature.SetField("last_id", max(ids))
        geometry = region.geometry
        if geometry is not None:
            feature.SetGeometry(ogr.ForceToMultiPolygon(geometry))
        layer.CreateFeature(feature)
    datasource.CommitTransaction()


def region_table(build: Build) -> list[tuple[regions_module.Region, list[int]]]:
    """(region, its corridor ids) for every region holding any, in order."""
    out = []
    for region in build.regions:
        ids = [c.id for c in build.corridors if c.region.rank == region.rank]
        if ids:
            out.append((region, ids))
    return out


def summary(build: Build) -> dict[str, Any]:
    return {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": build.complete,
        "review_round": build.review_round,
        "tours": len(build.tours),
        "corridors": len(build.corridors),
        "merged": [{"tour_fids": list(c.fids), "corridor_id": c.id, "how": c.group.how}
                   for c in build.corridors if len(c.parts) > 1],
        "gap_m": build.decisions.gap_m,
        "keep_apart": sorted(build.decisions.keep_apart),
        "regions": [{"rank": r.rank, "region_id": r.id, "region": r.name,
                     "kind": r.kind, "first_id": ids[0], "last_id": ids[-1],
                     "n": len(ids)} for r, ids in region_table(build)],
        "left_out": {str(f): why for f, why in sorted(build.left_out.items())},
        "pending_review": build.pending,
        "unresolved_links": [list(g) for g in build.plan.unresolved],
        "near_misses": [{"end_of": l.head, "start_of": l.tail, "gap_m": round(l.gap_m, 1)}
                        for l in build.plan.near_misses],
        "warnings": build.warnings,
    }
