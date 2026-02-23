from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

import geopandas as gpd
from shapely.geometry import Point

import grass.script as gs

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import run_routing_for_tour
from backend.routing_algorithm.routing.routing_across_areas.helpers import (
    AreaIndex,
    areas_in_route_bbox,
    grass_import_cost_surface,
    grass_patch_cost_surfaces,
    set_region_bbox,
)

Coord = Tuple[float, float]

def latlon_to_xy(latlon: Coord, target_crs: str) -> Coord:
    lat, lon = latlon
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(target_crs).iloc[0]
    return (float(pt.x), float(pt.y))

def run_routing_across_areas(
    *,
    tour_name: str,
    start_latlon: Coord,
    end_latlon: Coord,
    buffer_m: float,
    target_crs: str,
    index_gpkg: Path,
    index_layer: str,
    lambda_weight: float,
    smooth_threshold: float,
    multi_routing: bool,
    multi_routing_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # 1) determine which tile areas to include
    index = AreaIndex(gpkg_path=index_gpkg, layer=index_layer)
    area_ids = areas_in_route_bbox(
        start_latlon=start_latlon,
        end_latlon=end_latlon,
        index=index,
        buffer_m=buffer_m,
        target_crs=target_crs,
    )
    if not area_ids:
        raise ValueError("No areas found for this route bbox")

    # 2) Convert start and end to routing CRS
    start_xy = latlon_to_xy(start_latlon, target_crs)
    end_xy = latlon_to_xy(end_latlon, target_crs)

    # 3) Import cost surfaces for those tiles
    imported_cost_maps: List[str] = []
    dem_name: Optional[str] = None
    any_paths = None
    any_inputs = None

    for area_id in area_ids:
        paths, inputs = load_area(area_id)
        any_paths, any_inputs = paths, inputs

        # pick one DEM to use (assumes all tiles share same DEM grid)
        if dem_name is None:
            dem_map = f"dem__mosaic"
            if dem_map not in set(gs.list_strings(type="raster")):
                gs.run_command("r.in.gdal", input=str(inputs["dem"]), output=dem_map, overwrite=True, quiet=True)
            dem_name = dem_map

        cost_map = f"cost__{area_id}"
        existing = set(gs.list_strings(type="raster"))
        if cost_map not in existing:
            grass_import_cost_surface(area_id, paths.cost_surface, cost_map)
        imported_cost_maps.append(cost_map)

    if any_paths is None or any_inputs is None or dem_name is None:
        raise RuntimeError("Failed to load any areas for routing")

    # 4) Patch into one mosaic cost raster
    mosaic_cost = "cost__mosaic_tmp"
    grass_patch_cost_surfaces(imported_cost_maps, mosaic_cost)

    # 5) Set region aligned to mosaic raster, then clip to bbox plus buffer
    gs.run_command("g.region", raster=mosaic_cost, quiet=True)
    set_region_bbox(start_xy, end_xy, buffer_m)

    # 6) Run existing routing code, using overrides
    return run_routing_for_tour(
        paths=any_paths,
        inputs=any_inputs,
        tour_name=tour_name,
        start_coords=start_xy,
        end_coords=end_xy,
        lambda_weight=lambda_weight,
        smooth_threshold=smooth_threshold,
        multi_routing=multi_routing,
        multi_routing_params=multi_routing_params,
        dem_override=dem_name,
        cost_surface_override=mosaic_cost,
    )
