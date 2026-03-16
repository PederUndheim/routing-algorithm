from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union

import geopandas as gpd

from backend import config
from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import init_grass, run_routing_for_tour
from backend.routing_algorithm.tours.load_tours import load_tours_json, Tour
from backend.routing_algorithm.routing.grass_mosaic import build_or_get_mosaic
from backend.routing_algorithm.routing.cost_surface_request import compose_cost_surface_for_request, set_region_local

from backend.routing_algorithm.routing.grass_env import setup_grass_python_path
setup_grass_python_path()
import grass.script as gs


Coord = Tuple[float, float]
PathLike = Union[str, Path]

TOURS_JSON = Path("backend/routing_algorithm/tours/tours.json")


def _safe_slug(name: str) -> str:
    s = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name.lower())
    if s and s[0].isdigit():
        s = "_" + s
    return s


def export_wgs84_geojson(native_geojson_path: Union[str, Path], out_basename: str, out_dir: Path) -> Path:
    native_geojson_path = Path(native_geojson_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_basename}.geojson"

    gdf = gpd.read_file(native_geojson_path)
    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    gdf_wgs84.to_file(out_path, driver="GeoJSON")
    return out_path


def run(
    area_id: str,
    tours: Optional[List[Tour]] = None,
    track_influence_mode: str = config.RUN_DEBUG_ROUTING_PARAMS["track_influence_mode"],
    avoid_lake: bool =config.RUN_DEBUG_ROUTING_PARAMS["avoid_lake"],
    avoid_glacier: bool = config.RUN_DEBUG_ROUTING_PARAMS["avoid_glacier"],
    avoid_river: bool = config.RUN_DEBUG_ROUTING_PARAMS["avoid_river"],
) -> None:
    tours_by_area = load_tours_json(TOURS_JSON)
    if tours is None:
        if area_id not in tours_by_area:
            print(f"No tours found for area '{area_id}' in {TOURS_JSON}, skipping routing.")
            return
        tours = tours_by_area[area_id]

    # Load area context
    paths, inputs = load_area(area_id)

    if not paths.cost_surface.exists():
        raise FileNotFoundError(
            f"Cost surface not found at {paths.cost_surface}. "
            f"Build it first for area '{area_id}'."
        )

    # Import rasters into GRASS and compose request-cost exactly like frontend API.
    # Force import so updated cost_surface.tif is always picked up in script runs.
    print(f"\n[{area_id}] Importing rasters into GRASS and applying track influence ({track_influence_mode})...")
    dem_grass = build_or_get_mosaic([area_id], kind="dem", force_import=True)
    cost_grass = build_or_get_mosaic([area_id], kind="cost", force_import=True)
    gs.run_command("g.region", raster=dem_grass, flags="a", quiet=True)
    cost_with_tracks = compose_cost_surface_for_request(
        area_ids=[area_id],
        base_cost_name=cost_grass,
        avoid_lake=avoid_lake,
        avoid_glacier=avoid_glacier,
        avoid_river=avoid_river,
        track_influence_mode=track_influence_mode,
    )

    if not paths.cost_surface.exists():
        raise FileNotFoundError(
            f"Cost surface not found at {paths.cost_surface}. "
            f"Build it first for area '{area_id}'."
        )

    print(f"\n=== Area: {area_id} ===")
    final_outputs: Dict[str, Dict] = {}

    for tour in tours:
        print(f"\n--- Tour: {tour.name} ---")

        set_region_local(
            cost_with_tracks,
            start_xy=tour.start,
            end_xy=tour.end,
            buffer_m=float(config.ROUTING_SETTINGS["region_buffer_m"]),
        )

        res = run_routing_for_tour(
            paths=paths,
            inputs=inputs,
            tour_name=tour.name,
            start_coords=tour.start,
            end_coords=tour.end,
            lambda_weight=config.ROUTING_SETTINGS["lambda_weight"],
            smooth_threshold=config.ROUTING_SETTINGS["smooth_threshold"],
            multi_routing=config.MULTIROUTING,
            cost_surface_override=cost_with_tracks,
            dem_override=dem_grass,
            preserve_region=True,
            output_mode="area"
        )

        slug = _safe_slug(tour.name)

        # Single-route WGS84 export
        if "path_geojson_native" in res:
            wgs84_geojson = export_wgs84_geojson(
                native_geojson_path=res["path_geojson_native"],
                out_basename=f"{slug}_wgs84",
                out_dir=paths.route_wgs84,
            )
            res["path_geojson_wgs84"] = str(wgs84_geojson)

        # Multi-route WGS84 export
        if "multi_routing_routes_geojson" in res:
            out_dir = paths.multirouting_wgs84 / slug
            out_dir.mkdir(parents=True, exist_ok=True)

            wgs84_multi: List[str] = []
            for i, p in enumerate(res["multi_routing_routes_geojson"], start=1):
                out_p = export_wgs84_geojson(
                    native_geojson_path=p,
                    out_basename=f"{slug}_{i:02d}_wgs84",
                    out_dir=out_dir,
                )
                wgs84_multi.append(str(out_p))

            res["multi_routing_routes_geojson_wgs84"] = wgs84_multi

        final_outputs[tour.name] = res

    print("\n=== Done. Outputs ===")
    for tour_name, out in final_outputs.items():
        print(f"\n[{tour_name}]")
        for k, v in out.items():
            print(f"  {k}: {v}")


def main():
    from backend.scripts._cli import parse_area_arg

    tours_by_area = load_tours_json(TOURS_JSON)

    # One GRASS init for the whole script
    print("\n=== Initializing GRASS ===")
    init_grass()

    area_id = parse_area_arg()

    if area_id:
        if area_id not in tours_by_area:
            raise ValueError(f"Area '{area_id}' not found in {TOURS_JSON}")
        run(area_id, tours_by_area[area_id])
    else:
        for aid, tours in tours_by_area.items():
            run(aid, tours)


if __name__ == "__main__":
    main()
