from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import geopandas as gpd
from shapely.geometry import box, Point

import grass.script as gs

Coord = Tuple[float, float]

@dataclass(frozen=True)
class AreaIndex:
    gpkg_path: Path
    layer: str = "study_areas"

def areas_in_route_bbox(
    start_latlon: Coord,
    end_latlon: Coord,
    index: AreaIndex,
    buffer_m: float,
    target_crs: str,
) -> List[str]:
    
    gdf = gpd.read_file(index.gpkg_path, layer=index.layer)

    if gdf.crs is None:
        raise ValueError("Area index layer has no CRS")

    start_pt = gpd.GeoSeries([Point(start_latlon[1], start_latlon[0])], crs="EPSG:4326")
    end_pt = gpd.GeoSeries([Point(end_latlon[1], end_latlon[0])], crs="EPSG:4326")

    start_xy = start_pt.to_crs(target_crs).iloc[0]
    end_xy = end_pt.to_crs(target_crs).iloc[0]

    minx = min(start_xy.x, end_xy.x)
    maxx = max(start_xy.x, end_xy.x)
    miny = min(start_xy.y, end_xy.y)
    maxy = max(start_xy.y, end_xy.y)

    bbox_geom = box(minx, miny, maxx, maxy).buffer(buffer_m)

    bbox_gs = gpd.GeoSeries([bbox_geom], crs=target_crs).to_crs(gdf.crs)
    bbox_poly = bbox_gs.iloc[0]

    hits = gdf[gdf.intersects(bbox_poly)]
    if "area_id" not in hits.columns:
        raise ValueError("Area index layer must contain 'area_id' column")

    return sorted({str(x) for x in hits["area_id"].tolist()})



def grass_import_cost_surface(area_id: str, tif_path: Path, map_name: str) -> None:
    if not tif_path.exists():
        raise FileNotFoundError(f"Missing cost surface tif for {area_id}: {tif_path}")

    gs.run_command(
        "r.in.gdal",
        input=str(tif_path),
        output=map_name,
        overwrite=True,
        quiet=True,
    )

def grass_patch_cost_surfaces(input_maps: List[str], out_map: str) -> None:
    if not input_maps:
        raise ValueError("No input maps to patch")

    gs.run_command(
        "r.patch",
        input=",".join(input_maps),
        output=out_map,
        overwrite=True,
        quiet=True,
    )


def set_region_bbox(start_xy: Coord, end_xy: Coord, buffer_m: float) -> None:
    minx = min(start_xy[0], end_xy[0]) - buffer_m
    maxx = max(start_xy[0], end_xy[0]) + buffer_m
    miny = min(start_xy[1], end_xy[1]) - buffer_m
    maxy = max(start_xy[1], end_xy[1]) + buffer_m

    gs.run_command(
        "g.region",
        n=maxy,
        s=miny,
        e=maxx,
        w=minx,
        align=None,
        quiet=True,
    )
