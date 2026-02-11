from __future__ import annotations
import math
import numpy as np
import geopandas as gpd
from typing import List, Optional
from shapely.geometry import LineString, Point

def ensure_single_line(gdf: gpd.GeoDataFrame) -> LineString:
    lines = []
    for geom in gdf.geometry:
        if geom is None:
            continue
        gt = geom.geom_type
        if gt == "LineString":
            lines.append(geom)
        elif gt == "MultiLineString":
            lines.extend(list(geom.geoms))
        else:
            if hasattr(geom, "geoms"):
                for g in getattr(geom, "geoms", []):
                    if g.geom_type == "LineString":
                        lines.append(g)
    if not lines:
        raise ValueError("No (Multi)LineString geometry found.")
    return LineString([pt for ln in lines for pt in ln.coords])

def load_line_geojson(path: str, target_crs: str | None = None) -> LineString:
    gdf = gpd.read_file(path)
    if target_crs:
        gdf = gdf.to_crs(target_crs)
    return ensure_single_line(gdf)

def densify(line: LineString, step_m: float) -> LineString:
    if step_m <= 0: return line
    L = line.length
    if L == 0: return line
    n = max(2, int(math.ceil(L / step_m)) + 1)
    coords = [line.interpolate(dist).coords[0] for dist in np.linspace(0.0, L, n)]
    return LineString(coords)

def sample_points(line: LineString, step_m: float) -> List[Point]:
    L = line.length
    n = max(2, int(math.ceil(L / step_m)) + 1)
    return [line.interpolate(dist) for dist in np.linspace(0.0, L, n)]