from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Sequence

import geopandas as gpd
import numpy as np
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point


def _coord_xy(coord: Sequence[float]) -> tuple[float, float]:
    return float(coord[0]), float(coord[1])


def _line_2d(line: LineString) -> LineString:
    return LineString([_coord_xy(coord) for coord in line.coords])


def _extract_lines(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [_line_2d(geom)]
    if isinstance(geom, MultiLineString):
        return [_line_2d(line) for line in geom.geoms if not line.is_empty]
    if isinstance(geom, GeometryCollection):
        lines: list[LineString] = []
        for part in geom.geoms:
            lines.extend(_extract_lines(part))
        return lines
    return []


def ensure_metric_crs(gdf: gpd.GeoDataFrame, fallback_crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    if gdf.crs is None:
        return gdf.set_crs(fallback_crs, allow_override=True)
    return gdf


def ensure_single_line(gdf: gpd.GeoDataFrame) -> LineString:
    lines: list[LineString] = []
    for geom in gdf.geometry:
        lines.extend(_extract_lines(geom))

    if not lines:
        raise ValueError("No LineString or MultiLineString geometry found")

    coords: list[tuple[float, float]] = []
    for line in lines:
        line_coords = list(line.coords)
        if not line_coords:
            continue
        if coords and coords[-1] == line_coords[0]:
            coords.extend(_coord_xy(coord) for coord in line_coords[1:])
        else:
            coords.extend(_coord_xy(coord) for coord in line_coords)

    if len(coords) < 2:
        raise ValueError("Line geometry has fewer than two coordinates")
    return LineString(coords)


def load_line(path: str | Path, target_crs: str | None = None) -> LineString:
    gdf = ensure_metric_crs(gpd.read_file(path))
    if target_crs is not None:
        gdf = gdf.to_crs(target_crs)
    return ensure_single_line(gdf)


def load_geodataframe(path: str | Path, target_crs: str | None = None) -> gpd.GeoDataFrame:
    gdf = ensure_metric_crs(gpd.read_file(path))
    if target_crs is not None:
        gdf = gdf.to_crs(target_crs)
    return gdf


def endpoints(line: LineString) -> tuple[tuple[float, float], tuple[float, float]]:
    coords = list(line.coords)
    if len(coords) < 2:
        raise ValueError("Line geometry has fewer than two coordinates")
    return _coord_xy(coords[0]), _coord_xy(coords[-1])


def densify(line: LineString, step_m: float) -> LineString:
    if step_m <= 0 or line.length <= 0:
        return line
    distances = np.linspace(0.0, line.length, max(2, int(math.ceil(line.length / step_m)) + 1))
    return LineString([line.interpolate(float(distance)).coords[0] for distance in distances])


def sample_points(line: LineString, step_m: float) -> list[Point]:
    if step_m <= 0:
        raise ValueError("sample step must be > 0")
    if line.length <= 0:
        return [Point(line.coords[0])] if line.coords else []
    distances = np.linspace(0.0, line.length, max(2, int(math.ceil(line.length / step_m)) + 1))
    return [line.interpolate(float(distance)) for distance in distances]


def sample_points_with_fraction(line: LineString, step_m: float) -> list[tuple[Point, float]]:
    points = sample_points(line, step_m)
    if not points:
        return []
    if line.length <= 0:
        return [(points[0], 0.0)]
    return [(point, float(line.project(point) / line.length)) for point in points]


def coarsened_step_for_pair(
    line_a: LineString,
    line_b: LineString,
    initial_step_m: float,
    max_cells: int,
) -> float:
    if initial_step_m <= 0:
        raise ValueError("initial step must be > 0")
    n = max(2, int(math.ceil(line_a.length / initial_step_m)) + 1)
    m = max(2, int(math.ceil(line_b.length / initial_step_m)) + 1)
    cells = n * m
    if cells <= max_cells:
        return initial_step_m
    return initial_step_m * math.sqrt(cells / max_cells)


def coordinate_pairs(line: LineString) -> list[tuple[float, float]]:
    return [_coord_xy(coord) for coord in line.coords]


def bounds_with_padding(lines: Iterable[LineString], padding_m: float) -> tuple[float, float, float, float]:
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for line in lines:
        b = line.bounds
        minx = min(minx, b[0])
        miny = min(miny, b[1])
        maxx = max(maxx, b[2])
        maxy = max(maxy, b[3])
    if not math.isfinite(minx):
        raise ValueError("No bounds could be computed")
    return minx - padding_m, miny - padding_m, maxx + padding_m, maxy + padding_m

