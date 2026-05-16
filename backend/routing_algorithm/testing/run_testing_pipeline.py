from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict, List

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import init_grass, run_routing_for_tour
from backend.routing_algorithm.routing.cost_surface_request import set_region_local
from backend.routing_algorithm.routing.grass_env import GRASS_DB, setup_grass_python_path
from backend.routing_algorithm.routing.grass_mosaic import build_or_get_mosaic, safe_grass_name
from backend.routing_algorithm.tours.load_tours import Tour, load_tours_json
from backend.scripts.run_routing import export_wgs84_geojson
from backend.routing_algorithm.testing import config
from backend.routing_algorithm.testing.build import create_testing_cost_surface
from backend.routing_algorithm.testing.paths import TestingAreaPaths

setup_grass_python_path()
import grass.script as gs


TOURS_JSON = Path("backend/routing_algorithm/tours/tours.json")


def _safe_slug(name: str) -> str:
    s = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name.lower())
    if s and s[0].isdigit():
        s = "_" + s
    return s


def _testing_cost_raster_name(area_id: str, experiment: str) -> str:
    return f"testing_cost__{safe_grass_name(experiment)}__{safe_grass_name(area_id)}"


def _import_testing_cost_surface(cost_surface_path: Path, area_id: str, experiment: str) -> str:
    if not cost_surface_path.exists():
        raise FileNotFoundError(f"Testing cost surface not found: {cost_surface_path}")

    raster_name = _testing_cost_raster_name(area_id, experiment)
    gs.run_command(
        "r.in.gdal",
        input=str(cost_surface_path),
        output=raster_name,
        overwrite=True,
        quiet=True,
    )
    return raster_name


def _filter_tours(
    tours: List[Tour],
    *,
    allowed_names: set[str],
    tour_name: str | None,
) -> List[Tour]:
    if tour_name is not None:
        filtered = [tour for tour in tours if tour.name == tour_name]
        if not filtered:
            available = ", ".join(tour.name for tour in tours)
            raise ValueError(f"Tour '{tour_name}' not found. Available tours: {available}")
        return filtered

    selected = [tour for tour in tours if tour.name in allowed_names]
    if not selected:
        available = ", ".join(tour.name for tour in tours)
        print("No selected testing tours found in this area.")
        print(f"Available tours: {available}")
    return selected


def run_testing_pipeline_for_area(
    *,
    area_id: str,
    experiment: str,
    skip_build: bool,
    debug_mode: bool,
    tour_name: str | None,
    multi_routing: bool,
) -> None:
    print("\n====================================")
    print(f"=== Testing experiment: {experiment} | area: {area_id} ===")

    testing_paths = TestingAreaPaths(area_id=area_id, experiment=experiment)
    if skip_build:
        cost_surface_path = testing_paths.cost_surface
        print(f"=== Skipping cost build; using {cost_surface_path} ===")
    else:
        print("=== Step 1: Building testing cost surface ===")
        testing_paths, cost_surface_path = create_testing_cost_surface(
            area_id,
            experiment=experiment,
            debug_mode=debug_mode,
        )

    print("=== Step 2: Routing with testing cost surface ===")
    _, inputs = load_area(area_id)
    tours_by_area = load_tours_json(TOURS_JSON)
    tours = _filter_tours(
        tours_by_area.get(area_id, []),
        allowed_names=config.DEFAULT_TEST_TOURS,
        tour_name=tour_name,
    )
    if not tours:
        print(f"No tours found for area '{area_id}' in {TOURS_JSON}, skipping routing.")
        return

    dem_grass = build_or_get_mosaic([area_id], kind="dem", force_import=True)
    testing_cost_grass = _import_testing_cost_surface(cost_surface_path, area_id, experiment)
    gs.run_command("g.region", raster=dem_grass, flags="a", quiet=True)

    final_outputs: Dict[str, Dict] = {}
    for tour in tours:
        print(f"\n--- Tour: {tour.name} ---")
        set_region_local(
            testing_cost_grass,
            start_xy=tour.start,
            end_xy=tour.end,
            buffer_m=float(config.ROUTING_SETTINGS["region_buffer_m"]),
        )

        res = run_routing_for_tour(
            paths=testing_paths,
            inputs=inputs,
            tour_name=tour.name,
            start_coords=tour.start,
            end_coords=tour.end,
            lambda_weight=float(config.ROUTING_SETTINGS["lambda_weight"]),
            smooth_threshold=float(config.ROUTING_SETTINGS["smooth_threshold"]),
            multi_routing=multi_routing,
            cost_surface_override=testing_cost_grass,
            dem_override=dem_grass,
            preserve_region=True,
            output_mode="area",
        )

        slug = _safe_slug(tour.name)
        if "path_geojson_native" in res:
            wgs84_geojson = export_wgs84_geojson(
                native_geojson_path=res["path_geojson_native"],
                out_basename=f"{slug}_wgs84",
                out_dir=testing_paths.route_wgs84,
            )
            res["path_geojson_wgs84"] = str(wgs84_geojson)

        final_outputs[tour.name] = res

    print("\n=== Testing outputs ===")
    print(f"Testing root: {testing_paths.root}")
    print(f"Cost surface: {cost_surface_path}")
    for tour, outputs in final_outputs.items():
        print(f"\n[{tour}]")
        for key, value in outputs.items():
            print(f"  {key}: {value}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local-only pipeline for the testing cost-surface experiment."
    )
    parser.add_argument(
        "--area",
        required=False,
        help=(
            "Area ID, e.g. isfjorden_01. If omitted, the default testing areas "
            "from backend/routing_algorithm/testing/config.py are processed."
        ),
    )
    parser.add_argument(
        "--experiment",
        default=config.DEFAULT_EXPERIMENT,
        help=f"Name under data/testing/. Default: {config.DEFAULT_EXPERIMENT}",
    )
    parser.add_argument(
        "--tour",
        required=False,
        help="Optional exact tour name from backend/routing_algorithm/tours/tours.json.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Use an existing testing cost surface instead of rebuilding it.",
    )
    parser.add_argument(
        "--no-debug-layers",
        action="store_true",
        help="Do not write intermediate debug rasters.",
    )
    parser.add_argument(
        "--multi-routing",
        action="store_true",
        help="Run the multi-route experiment instead of the single best route.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    os.makedirs(GRASS_DB, exist_ok=True)
    init_grass()

    area_ids = [args.area] if args.area else config.DEFAULT_TEST_AREAS
    for area_id in area_ids:
        run_testing_pipeline_for_area(
            area_id=area_id,
            experiment=args.experiment,
            skip_build=bool(args.skip_build),
            debug_mode=not bool(args.no_debug_layers),
            tour_name=args.tour,
            multi_routing=bool(args.multi_routing),
        )


if __name__ == "__main__":
    main()
