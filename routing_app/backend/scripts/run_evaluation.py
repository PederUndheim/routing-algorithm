from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import config as app_config
from backend.routing_algorithm.evaluation.config import DEFAULT_SETTINGS, EvaluationSettings, parse_buffer_distances
from backend.routing_algorithm.evaluation.pipeline import (
    run_evaluation_for_all_areas,
    run_evaluation_for_area,
    write_all_areas_evaluation_outputs,
    write_area_evaluation_outputs,
)
from backend.routing_algorithm.evaluation.routes import discover_areas_with_evaluation_routes, route_id_from_path


THESIS_TRACK_MODES = ("off", "forest_only", "balanced", "strong")


def _parse_terrain_rasters(values: list[str] | None) -> Dict[str, Path]:
    rasters: Dict[str, Path] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"Terrain raster must be on the form label=/path/to/raster.tif, got: {value}")
        label, path = value.split("=", 1)
        label = label.strip()
        if not label:
            raise ValueError(f"Terrain raster label is empty: {value}")
        rasters[label] = Path(path).expanduser()
    return rasters


def _settings_for_track_mode(settings: EvaluationSettings, track_mode: str, *, multi_mode: bool) -> EvaluationSettings:
    if not multi_mode:
        return settings
    return replace(settings, evaluation_run_id=f"{settings.evaluation_run_id}_tracks_{track_mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate generated routes against reference GeoJSON routes.")
    parser.add_argument("--area", required=False, help="Area ID, e.g. isfjorden_01. If omitted, all areas are processed.")
    parser.add_argument("--route", action="append", dest="routes", help="Evaluation route id to run, e.g. kyrkjetaket. Can be repeated.")
    parser.add_argument("--force-reroute", action="store_true", help="Ignore the route cache and reroute everything.")
    parser.add_argument("--no-reroute", action="store_true", help="Only evaluate cached/generated routes. Does not initialize GRASS.")
    parser.add_argument(
        "--use-area-route-fallback",
        action="store_true",
        help="When --no-reroute is used, fall back to data/areas/<area>/output/route/<route>_path.geojson if the evaluation cache is missing.",
    )
    parser.add_argument("--no-plots", action="store_true", help="Skip PNG diagnostic plots.")
    parser.add_argument("--metric-crs", default=DEFAULT_SETTINGS.metric_crs)
    parser.add_argument("--sample-step-m", type=float, default=DEFAULT_SETTINGS.sample_step_m)
    parser.add_argument("--frechet-step-m", type=float, default=DEFAULT_SETTINGS.frechet_step_m)
    parser.add_argument("--buffers", default=",".join(str(v) for v in DEFAULT_SETTINGS.buffer_distances_m))
    parser.add_argument("--corridor-sample-step-m", type=float, default=DEFAULT_SETTINGS.corridor_sample_step_m)
    parser.add_argument("--evaluation-run-id", default=DEFAULT_SETTINGS.evaluation_run_id)
    parser.add_argument(
        "--terrain-raster",
        action="append",
        help="Optional categorical raster for terrain summaries, on the form label=/path/to/raster.tif. Can be repeated.",
    )
    parser.add_argument(
        "--track-influence-mode",
        action="append",
        choices=sorted(app_config.TRACK_INFLUENCE_PARAMS.keys()),
        help="Track influence mode to evaluate. Can be repeated, e.g. --track-influence-mode off --track-influence-mode balanced.",
    )
    parser.add_argument(
        "--all-track-modes",
        action="store_true",
        help="Evaluate the thesis track modes: off, forest_only, balanced, and strong.",
    )
    parser.add_argument("--avoid-lake", action="store_true", default=bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_lake"]))
    parser.add_argument("--avoid-glacier", action="store_true", default=bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_glacier"]))
    parser.add_argument("--avoid-river", action="store_true", default=bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_river"]))
    args = parser.parse_args()

    settings = EvaluationSettings(
        metric_crs=args.metric_crs,
        sample_step_m=args.sample_step_m,
        frechet_step_m=args.frechet_step_m,
        buffer_distances_m=parse_buffer_distances(args.buffers),
        corridor_sample_step_m=args.corridor_sample_step_m,
        evaluation_run_id=args.evaluation_run_id,
        make_plots=not args.no_plots,
        thresholds=DEFAULT_SETTINGS.thresholds,
    )
    route_ids = {route_id_from_path(route) for route in args.routes} if args.routes else None
    terrain_rasters = _parse_terrain_rasters(args.terrain_raster)
    if args.all_track_modes and args.track_influence_mode:
        parser.error("Use either --all-track-modes or repeated --track-influence-mode, not both.")

    track_modes = list(THESIS_TRACK_MODES) if args.all_track_modes else (
        args.track_influence_mode or [str(app_config.RUN_DEBUG_ROUTING_PARAMS["track_influence_mode"])]
    )
    multi_mode = len(track_modes) > 1

    reroute = not args.no_reroute
    if reroute:
        from backend.routing_algorithm.routing.core import init_grass

        print("=== Initializing GRASS ===")
        init_grass()

    rows = []
    if args.area:
        for track_mode in track_modes:
            mode_settings = _settings_for_track_mode(settings, track_mode, multi_mode=multi_mode)
            rows.extend(
                run_evaluation_for_area(
                    args.area,
                    settings=mode_settings,
                    route_ids=route_ids,
                    force_reroute=args.force_reroute,
                    reroute=reroute,
                    allow_area_route_fallback=args.use_area_route_fallback,
                    terrain_rasters=terrain_rasters,
                    track_influence_mode=track_mode,
                    avoid_lake=args.avoid_lake,
                    avoid_glacier=args.avoid_glacier,
                    avoid_river=args.avoid_river,
                    write_outputs=False,
                )
            )
        write_area_evaluation_outputs(args.area, rows, settings=settings)
    else:
        area_ids = discover_areas_with_evaluation_routes()
        for track_mode in track_modes:
            mode_settings = _settings_for_track_mode(settings, track_mode, multi_mode=multi_mode)
            rows.extend(
                run_evaluation_for_all_areas(
                    area_ids,
                    settings=mode_settings,
                    route_ids=route_ids,
                    force_reroute=args.force_reroute,
                    reroute=reroute,
                    allow_area_route_fallback=args.use_area_route_fallback,
                    terrain_rasters=terrain_rasters,
                    track_influence_mode=track_mode,
                    avoid_lake=args.avoid_lake,
                    avoid_glacier=args.avoid_glacier,
                    avoid_river=args.avoid_river,
                    write_outputs=False,
                )
            )
        for area_id in area_ids:
            area_rows = [row for row in rows if row.get("area_id") == area_id]
            write_area_evaluation_outputs(area_id, area_rows, settings=settings)
        write_all_areas_evaluation_outputs(rows, settings=settings)

    ok = sum(1 for row in rows if row.get("status") == "ok")
    print(f"Evaluation finished: {ok}/{len(rows)} routes evaluated successfully.")


if __name__ == "__main__":
    main()
