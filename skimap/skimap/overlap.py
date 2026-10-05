"""Overlapping corridors, drawn in the easiest colour that goes there.

This is how exposure.split_corridors writes data/colored_corridors. Merging
each colour on its own - what it did before, and still does with --stacked -
draws two bands on top of each other wherever a red tour and a green one
share their first kilometre: the red one's fade and its (often wider) width
poke out from under the green, and the colour of that ground depends on draw
order.

This fades a tour out wherever the LINE of an easier tour runs along its own.
At every sample along a route, the distance to the nearest line of any
gentler class sets a weight

    closer than near_m    0    same trail - the easier tour already draws it
    near_m .. far_m       smoothstep
    beyond far_m          1    its own ground

and every corridor cell takes the weight of the nearest sample on its own
route. Nothing is cut: the weight comes from how far apart the two lines
really are, so a slow bend away hands over across a long stretch, a sharp
turn across a short one, and a tour that rejoins an easier one fades out
again by itself.

No gap opens where the lines split, because the harder tour is back at full
weight once its line is far_m from the easier one - still inside the easier
corridor, as long as far_m stays under that corridor's half-width.

Crossings are not sharing. Two lines that cross come within near_m of each
other for a few tens of metres, and counting that would punch a short fade
into the harder tour exactly where the two are least alike. A faded stretch
therefore has to add up to min_shared_m of suppression, or it is dropped.

Each cell then goes to whichever tour's WEIGHTED membership is highest, so
the class rasters are disjoint and draw order stops mattering. Past the
split, the harder tour's core would otherwise take cells close to the easier
line from the easier corridor's fringe; easier_priority tips contested cells
towards the gentler class to keep the easier band whole. Only where that band
is solid (priority_floor): boosting its faint outer fringe as well holds the
harder band back to the easier corridor's outline, and it then starts there
at full strength along a hard edge.

Two things soften where one colour meets another, both off at 0:

    fade_in_m   past a shared stretch the harder tour comes in over this
                much more route, so wherever the colour does change the
                harder band is still pale
    seam_m      the class map is blurred into shares, so across roughly this
                width a cell is part one colour and part the other. The
                rasters then overlap inside the seam - and nowhere else.

Nationally this runs in tiles (write_classes). Weights belong to a route and
are computed once for all of them; what a cell becomes depends only on the
corridors covering it, plus the seam's blur radius around it. So a tile
padded by that radius and cropped back gives exactly what one country-sized
window would, in memory that does not grow with the country.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Optional

import numpy as np
from osgeo import gdal, ogr, osr
from scipy.ndimage import gaussian_filter, label
from scipy.spatial import cKDTree

from skimap import config, exposure, routing

gdal.UseExceptions()
ogr.UseExceptions()

CLASS_NAMES = tuple(name for _, name in config.EXPOSURE_CLASSES)
SEVERITY = {name: index for index, name in enumerate(CLASS_NAMES)}

# As routing.merge_corridors writes corridors_all.tif, and for its reason: the
# union of the corridors spans most of the country and covers very little of it.
RASTER_OPTIONS = ["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3", "SPARSE_OK=TRUE",
                  "BIGTIFF=YES", "NUM_THREADS=ALL_CPUS"]
OVERVIEWS = [2, 4, 8, 16, 32, 64]

# A multiple of the GTiff's 256 px blocks, so every block is written once.
# Rewriting a compressed block appends a new copy and leaves the old one as
# dead space in the file.
TILE_CELLS = 2048


@dataclass
class Line:
    """One routed line, sampled evenly, with the class it scored."""

    fid: int
    colour: str
    station: np.ndarray    # arc length of each sample, m
    points: np.ndarray     # (n, 2) sample coordinates

    @property
    def severity(self) -> int:
        return SEVERITY[self.colour]

    @cached_property
    def tree(self) -> cKDTree:
        """Nearest-sample lookup, built once - every tile a corridor touches asks."""
        return cKDTree(self.points)


def make_line(fid: int, colour: str, xy, step_m: Optional[float] = None) -> Line:
    step = float(config.OVERLAP["step_m"] if step_m is None else step_m)
    station, points = exposure.sample_stations(np.asarray(xy, dtype=np.float64)[:, :2], step)
    return Line(fid, colour, station, points)


def load_lines(routes_path: Path, colours: Optional[dict[int, str]] = None) -> dict[int, Line]:
    """tour_fid -> Line, for every scored route in routes.gpkg.

    `colours` (tour_fid -> class) is used instead of the colour field when
    given, which is how exposure hands over the classes it has just computed.
    """
    ds = ogr.Open(str(routes_path))
    if ds is None:
        raise FileNotFoundError(f"Could not open {routes_path}")
    layer = ds.GetLayerByName(routing.ROUTES_LAYER)
    if layer is None:
        raise KeyError(f"No layer {routing.ROUTES_LAYER!r} in {routes_path}")
    if colours is None and layer.GetLayerDefn().GetFieldIndex("colour") < 0:
        raise KeyError(f"{Path(routes_path).name} has no colour field - score it with exposure first")

    lines: dict[int, Line] = {}
    for feat in layer:
        fid = feat.GetField("tour_fid")
        colour = colours.get(fid) if colours is not None else feat.GetField("colour")
        geom = feat.GetGeometryRef()
        if geom is None or geom.GetPointCount() < 2 or colour not in SEVERITY:
            continue
        lines[fid] = make_line(fid, colour, geom.GetPoints())
    ds = None
    return lines


def smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# --- weights, per route ---------------------------------------------------


def weights(lines: dict[int, Line], *, near_m: Optional[float] = None,
            far_m: Optional[float] = None,
            min_shared_m: Optional[float] = None,
            fade_in_m: Optional[float] = None) -> dict[int, np.ndarray]:
    """tour_fid -> weight per sample, 0 where an easier tour runs along it."""
    settings = config.OVERLAP
    near = float(settings["near_m"] if near_m is None else near_m)
    far = float(settings["far_m"] if far_m is None else far_m)
    min_shared = float(settings["min_shared_m"] if min_shared_m is None else min_shared_m)
    fade_in = float(settings["fade_in_m"] if fade_in_m is None else fade_in_m)
    if far <= near:
        raise ValueError(f"far_m ({far:g}) must be greater than near_m ({near:g})")

    # One tree per class, over the samples of every gentler class, shared by
    # all the routes of that class. Built per route, it would be most of the
    # country's samples again for every red and black line.
    trees: dict[int, Optional[cKDTree]] = {}
    out: dict[int, np.ndarray] = {}
    for fid, line in lines.items():
        if line.severity not in trees:
            gentler = [other.points for other in lines.values() if other.severity < line.severity]
            trees[line.severity] = cKDTree(np.vstack(gentler)) if gentler else None
        tree = trees[line.severity]
        if tree is None:
            out[fid] = np.ones(len(line.station))
            continue

        distance, _ = tree.query(line.points)
        suppression = 1.0 - smoothstep((distance - near) / (far - near))

        # Metres of route each sample stands for, so a run is measured in
        # suppressed length and a crossing's short dip can be told apart
        # from a shared trail.
        spacing = np.gradient(line.station) if len(line.station) > 1 else np.zeros(1)
        runs, count = label(suppression > 0.0)
        for k in range(1, count + 1):
            run = runs == k
            if float((suppression[run] * spacing[run]).sum()) < min_shared:
                suppression[run] = 0.0
        weight = 1.0 - suppression

        shared = line.station[weight < 1.0]
        if fade_in > 0.0 and len(shared):
            # Metres along the route to the nearest faded sample, either way:
            # a tour can leave a shared trunk or arrive onto one.
            index = np.searchsorted(shared, line.station)
            before = shared[np.clip(index - 1, 0, len(shared) - 1)]
            after = shared[np.clip(index, 0, len(shared) - 1)]
            along = np.minimum(np.abs(line.station - before), np.abs(after - line.station))
            weight = weight * smoothstep(along / fade_in)
        out[fid] = weight
    return out


# --- cells, per window ----------------------------------------------------


def blend(corridors: dict[int, np.ndarray], lines: dict[int, Line],
          line_weights: dict[int, np.ndarray],
          centres: tuple[np.ndarray, np.ndarray], *,
          easier_priority: Optional[float] = None,
          priority_floor: Optional[float] = None,
          top_severity: Optional[int] = None) -> tuple[np.ndarray, np.ndarray]:
    """(severity per cell, membership per cell). Severity is -1 off every corridor.

    `corridors` are memberships on one window, `centres` that window's cell
    centre coordinates as two full-size arrays.

    Where a tour's weighted membership is at least `priority_floor` it is
    multiplied by `easier_priority` once for every class it is below
    `top_severity`, and the strongest tour takes the cell - so against a
    solid easier band, a tour one class harder has to be that many times
    stronger. The cell keeps the winner's own membership, so each band's ramp
    stays its own.

    `top_severity` defaults to the hardest class among these corridors. Tiles
    of one larger area must pass the same value, or their boosts disagree.
    """
    priority = float(config.OVERLAP["easier_priority"]
                     if easier_priority is None else easier_priority)
    floor = float(config.OVERLAP["priority_floor"] if priority_floor is None else priority_floor)
    if priority <= 0.0:
        raise ValueError(f"easier_priority must be positive, not {priority:g}")

    cx, cy = centres
    shape = cx.shape
    severity = np.full(shape, -1, dtype=np.int8)
    value = np.zeros(shape, dtype=np.float32)
    if not corridors:
        return severity, value
    top = (max(lines[fid].severity for fid in corridors)
           if top_severity is None else int(top_severity))

    # One corridor at a time rather than a stack of them: a busy tile can
    # hold dozens. Gentlest first, and only a strictly stronger claim takes
    # a cell over, so a tie stays with the gentler class.
    best = np.zeros(shape, dtype=np.float32)
    for fid in sorted(corridors, key=lambda f: (lines[f].severity, f)):
        rows, cols = np.nonzero(corridors[fid] > 0.0)
        if len(rows) == 0:
            continue
        line = lines[fid]
        _, index = line.tree.query(np.column_stack([cx[rows, cols], cy[rows, cols]]))
        weighted = (corridors[fid][rows, cols] * line_weights[fid][index]).astype(np.float32)
        boost = np.float32(priority ** (top - line.severity))
        rank = np.where(weighted >= floor, weighted * boost, weighted)

        wins = rank > best[rows, cols]
        r, c = rows[wins], cols[wins]
        best[r, c] = rank[wins]
        value[r, c] = weighted[wins]
        severity[r, c] = line.severity
    return severity, value


def soft_classes(severity: np.ndarray, value: np.ndarray, *, pixel_m: float,
                 seam_m: Optional[float] = None) -> dict[str, np.ndarray]:
    """One membership raster per class, cross-faded across seam_m where classes meet.

    Each class's cells are blurred and normalized into a share, and the
    class gets the cell's membership times that share. Away from a seam the
    share is 1 and this is the disjoint split; on the old boundary it is
    half and half, going from about 85/15 to 15/85 across seam_m. The blur
    is normalized over classes only, so a corridor's outer edge is not faded
    towards nothing.
    """
    seam = float(config.OVERLAP["seam_m"] if seam_m is None else seam_m)
    masks = {c: severity == SEVERITY[c] for c in CLASS_NAMES}
    if seam <= 0.0:
        return {c: np.where(mask, value, 0.0).astype(np.float32) for c, mask in masks.items()}

    sigma = seam / 2.0 / float(pixel_m)
    blurred = {c: gaussian_filter(mask.astype(np.float32), sigma, mode="constant")
               for c, mask in masks.items() if mask.any()}
    total = sum(blurred.values())
    out = {}
    for c in CLASS_NAMES:
        if c not in blurred:
            out[c] = np.zeros(value.shape, dtype=np.float32)
            continue
        share = np.divide(blurred[c], total, out=np.zeros_like(total), where=total > 0.0)
        out[c] = (value * share).astype(np.float32)
    return out


def seam_pad_cells(seam_m: float, pixel_m: float) -> int:
    """How far the seam's blur reaches, in cells - gaussian_filter's own radius."""
    if seam_m <= 0.0:
        return 0
    return int(4.0 * (seam_m / 2.0 / pixel_m) + 0.5) + 1


def stacked(corridors: dict[int, np.ndarray], lines: dict[int, Line]) -> dict[str, np.ndarray]:
    """Each class merged on its own, overlaps and all - what --stacked writes."""
    out: dict[str, np.ndarray] = {}
    for fid, membership in corridors.items():
        colour = lines[fid].colour
        out[colour] = membership if colour not in out else np.maximum(out[colour], membership)
    return out


# --- rasters --------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    """A lattice-aligned rectangle: north-west corner, size in cells, cell size."""

    x0: float
    y1: float
    width: int
    height: int
    pixel: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y1 - self.height * self.pixel,
                self.x0 + self.width * self.pixel, self.y1)

    @property
    def geotransform(self) -> tuple[float, float, float, float, float, float]:
        return (self.x0, self.pixel, 0.0, self.y1, 0.0, -self.pixel)

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        return np.meshgrid(self.x0 + (np.arange(self.width) + 0.5) * self.pixel,
                           self.y1 - (np.arange(self.height) + 0.5) * self.pixel)


def extent(path: Path) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) of a raster, without reading it."""
    ds = gdal.Open(str(path))
    g = ds.GetGeoTransform()
    box = (g[0], g[3] + g[5] * ds.RasterYSize, g[0] + g[1] * ds.RasterXSize, g[3])
    ds = None
    return box


def read(window: Window, path: Path) -> np.ndarray:
    """A corridor on the window as float32; nodata, negatives and outside all 0.

    Everything here shares one lattice, so this is a crop and a pad.
    """
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    g = ds.GetGeoTransform()
    px = int(round((window.x0 - g[0]) / window.pixel))
    py = int(round((g[3] - window.y1) / window.pixel))

    out = np.zeros(window.shape, dtype=np.float32)
    sx0, sy0 = max(px, 0), max(py, 0)
    sx1, sy1 = min(px + window.width, ds.RasterXSize), min(py + window.height, ds.RasterYSize)
    if sx1 > sx0 and sy1 > sy0:
        arr = band.ReadAsArray(sx0, sy0, sx1 - sx0, sy1 - sy0).astype(np.float32)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            arr[arr == np.float32(nodata)] = 0.0
        out[sy0 - py:sy1 - py, sx0 - px:sx1 - px] = np.nan_to_num(np.clip(arr, 0.0, None))
    ds = None
    return out


def write_classes(lines: dict[int, Line], corridors: dict[int, Path], out_dir: Path, *,
                  near_m: Optional[float] = None, far_m: Optional[float] = None,
                  min_shared_m: Optional[float] = None, fade_in_m: Optional[float] = None,
                  easier_priority: Optional[float] = None,
                  priority_floor: Optional[float] = None, seam_m: Optional[float] = None,
                  tile_cells: int = TILE_CELLS, report: bool = True) -> dict[str, Path]:
    """corridors_<class>.tif in out_dir, overlaps faded. Returns class -> file.

    Every class raster covers the union of all the corridors, written sparse
    like corridors_all.tif. A class with no cells is not written, and a stale
    file of that name from an earlier run is removed.
    """
    out_dir = Path(out_dir)
    fids = sorted(set(lines) & set(corridors))
    if report and len(fids) < len(corridors):
        print(f"  {len(corridors) - len(fids)} corridors have no scored line - left out")
    if not fids:
        print("No corridors to colour.")
        return {}
    lines = {fid: lines[fid] for fid in fids}

    line_weights = weights(lines, near_m=near_m, far_m=far_m,
                           min_shared_m=min_shared_m, fade_in_m=fade_in_m)
    seam = float(config.OVERLAP["seam_m"] if seam_m is None else seam_m)
    top = max(line.severity for line in lines.values())
    p = float(config.PIXEL_SIZE)

    boxes = {fid: extent(corridors[fid]) for fid in fids}
    minx = min(b[0] for b in boxes.values())
    miny = min(b[1] for b in boxes.values())
    maxx = max(b[2] for b in boxes.values())
    maxy = max(b[3] for b in boxes.values())
    for fid, b in boxes.items():
        fx, fy = (b[0] - minx) / p, (maxy - b[3]) / p
        if abs(fx - round(fx)) > 1e-3 or abs(fy - round(fy)) > 1e-3:
            raise RuntimeError(f"Corridor {corridors[fid].name} is off the other corridors' lattice")
    width = int(round((maxx - minx) / p))
    height = int(round((maxy - miny) / p))

    # Which tiles each corridor can change: its extent, grown by the seam's
    # reach, because the blur carries a class that far into a neighbour.
    pad = seam_pad_cells(seam, p)
    size = int(tile_cells)
    tiles: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fid, (x0, y0, x1, y1) in boxes.items():
        c0 = max(int(round((x0 - minx) / p)) - pad, 0)
        c1 = min(int(round((x1 - minx) / p)) + pad, width)
        r0 = max(int(round((maxy - y1) / p)) - pad, 0)
        r1 = min(int(round((maxy - y0) / p)) + pad, height)
        for ty in range(r0 // size, (r1 - 1) // size + 1):
            for tx in range(c0 // size, (c1 - 1) // size + 1):
                tiles[(ty, tx)].append(fid)

    if report:
        faded = [float(np.gradient(lines[f].station)[w < 0.5].sum())
                 for f, w in line_weights.items() if len(w) > 1 and (w < 0.5).any()]
        print(f"Colouring {len(fids)} corridors, {width} x {height} px sparse, "
              f"{len(tiles)} tiles of {size} px")
        print(f"  {len(faded)} routes run along an easier one, "
              f"{sum(faded) / 1000:.1f} km faded in total")

    out_dir.mkdir(parents=True, exist_ok=True)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(config.CRS_EPSG)
    outputs: dict[str, tuple[Path, gdal.Dataset]] = {}
    for colour in CLASS_NAMES:
        tmp = out_dir / f"corridors_{colour}.tmp.tif"
        ds = gdal.GetDriverByName("GTiff").Create(str(tmp), width, height, 1,
                                                  gdal.GDT_Float32, options=RASTER_OPTIONS)
        ds.SetGeoTransform((minx, p, 0.0, maxy, 0.0, -p))
        ds.SetProjection(srs.ExportToWkt())
        ds.GetRasterBand(1).SetNoDataValue(0.0)
        outputs[colour] = (tmp, ds)
    cells = {colour: 0 for colour in CLASS_NAMES}

    for n, ((ty, tx), members) in enumerate(sorted(tiles.items()), 1):
        ir0, ic0 = ty * size, tx * size
        ir1, ic1 = min(ir0 + size, height), min(ic0 + size, width)
        pr0, pc0 = max(ir0 - pad, 0), max(ic0 - pad, 0)
        pr1, pc1 = min(ir1 + pad, height), min(ic1 + pad, width)
        window = Window(minx + pc0 * p, maxy - pr0 * p, pc1 - pc0, pr1 - pr0, p)

        arrays = {}
        for fid in members:
            array = read(window, corridors[fid])
            if (array > 0.0).any():
                arrays[fid] = array
        if arrays:
            severity, value = blend(arrays, lines, line_weights, window.centres(),
                                    easier_priority=easier_priority,
                                    priority_floor=priority_floor, top_severity=top)
            classes = soft_classes(severity, value, pixel_m=p, seam_m=seam)
            crop = (slice(ir0 - pr0, ir1 - pr0), slice(ic0 - pc0, ic1 - pc0))
            for colour, array in classes.items():
                part = array[crop]
                if (part > 0.0).any():
                    outputs[colour][1].GetRasterBand(1).WriteArray(part, ic0, ir0)
                    cells[colour] += int((part > 0.0).sum())
        if report and (n % 50 == 0 or n == len(tiles)):
            print(f"  {n}/{len(tiles)} tiles", flush=True)

    written: dict[str, Path] = {}
    for colour in CLASS_NAMES:
        tmp, ds = outputs.pop(colour)
        if cells[colour]:
            ds.GetRasterBand(1).FlushCache()
            ds.BuildOverviews("AVERAGE", OVERVIEWS)
        ds = None
        final = out_dir / f"corridors_{colour}.tif"
        if not cells[colour]:
            tmp.unlink()
            _remove(final, report)
            if report:
                print(f"  {colour:<6} no cells - not written")
            continue
        written[colour] = _replace(tmp, final, report)
        if report:
            print(f"  {colour:<6} {cells[colour]:>10d} cells -> {written[colour].name} "
                  f"({written[colour].stat().st_size / 1e6:.0f} MB)")
    return written


def _sidecars(path: Path) -> list[Path]:
    """Overviews and statistics a GIS builds beside a raster. Left behind by a
    replaced file, they are drawn over the new one when zoomed out."""
    return [path.with_name(path.name + ".ovr"), path.with_name(path.name + ".aux.xml")]


def _replace(tmp: Path, final: Path, report: bool) -> Path:
    """Move tmp over final. A raster open in ArcGIS is locked: then tmp stays."""
    try:
        os.replace(tmp, final)
    except OSError:
        if report:
            print(f"  {final.name} is locked (open in a GIS?) - new raster left as {tmp.name}")
        return tmp
    for sidecar in _sidecars(final):
        _remove(sidecar, report)
    return final


def _remove(path: Path, report: bool) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        if report:
            print(f"  could not remove {path.name} - it is locked and now stale")
