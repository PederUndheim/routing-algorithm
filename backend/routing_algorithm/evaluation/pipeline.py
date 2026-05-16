from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backend import config as app_config
from backend.file_handler.area_context import PROJECT_ROOT, load_area

from .config import DEFAULT_SETTINGS, EvaluationSettings
from .corridor import evaluate_corridors
from .geometry import load_line
from .metrics import compare_routes, comparison_to_dict
from .plotting import plot_route_comparison, write_comparison_geojson, write_deviation_samples_geojson
from .report import write_csv, write_json, write_markdown_summary, write_simplified_route_metrics_csv, write_standard_group_summaries
from .results_data import export_results_data_bundle
from .routes import EvaluationRoute, discover_areas_with_evaluation_routes, load_evaluation_routes, routing_area_ids_for_study_area
from .terrain import summarize_terrain_rasters


@dataclass(frozen=True)
class GeneratedRouteOutputs:
    route_path: Path
    corridor_paths: dict[str, Path]
    used_cache: bool
    source: str


def _expected_generated_outputs(paths, route_id: str, settings: EvaluationSettings) -> GeneratedRouteOutputs:
    root = paths.evaluation_results / "routing"
    base = root / "runs_output" / settings.evaluation_run_id
    route_path = base / "route" / f"path_{route_id}.geojson"
    corridor_paths = {
        mode: base / "corridor" / f"corridor_{mode}_{route_id}.tif"
        for mode in settings.corridor_modes
    }
    return GeneratedRouteOutputs(route_path=route_path, corridor_paths=corridor_paths, used_cache=True, source="evaluation_cache")


def _area_route_fallback(paths, route_id: str, settings: EvaluationSettings) -> GeneratedRouteOutputs | None:
    route_path = paths.route_dir / f"{route_id}_path.geojson"
    if not route_path.exists():
        return None
    corridor_paths = {
        mode: paths.corridor / f"{route_id}_{mode}_corridor.tif"
        for mode in settings.corridor_modes
    }
    return GeneratedRouteOutputs(route_path=route_path, corridor_paths=corridor_paths, used_cache=True, source="area_output_fallback")


def _has_complete_cache(outputs: GeneratedRouteOutputs) -> bool:
    return outputs.route_path.exists() and all(path.exists() for path in outputs.corridor_paths.values())


def _prepare_routing_context(
    area_id: str,
    *,
    routing_area_ids: list[str],
    track_influence_mode: str,
    avoid_lake: bool,
    avoid_glacier: bool,
    avoid_river: bool,
) -> tuple[Any, Any, str, str]:
    from backend.routing_algorithm.routing.cost_surface_request import compose_cost_surface_for_request
    from backend.routing_algorithm.routing.grass_mosaic import build_or_get_mosaic

    paths, inputs = load_area(area_id)
    if not paths.cost_surface.exists():
        raise FileNotFoundError(
            f"Runtime cost surface missing for area '{area_id}': {paths.cost_surface}. "
            "Build the cost surface before running evaluation."
        )

    for routing_area_id in routing_area_ids:
        routing_paths, _ = load_area(routing_area_id)
        if not routing_paths.cost_surface.exists():
            raise FileNotFoundError(
                f"Runtime cost surface missing for routing area '{routing_area_id}': "
                f"{routing_paths.cost_surface}. Build the cost surface before running evaluation."
            )

    dem_grass = build_or_get_mosaic(routing_area_ids, kind="dem", force_import=True)
    cost_grass = build_or_get_mosaic(routing_area_ids, kind="cost", force_import=True)
    cost_with_request_options = compose_cost_surface_for_request(
        area_ids=routing_area_ids,
        base_cost_name=cost_grass,
        avoid_lake=avoid_lake,
        avoid_glacier=avoid_glacier,
        avoid_river=avoid_river,
        track_influence_mode=track_influence_mode,
    )
    return paths, inputs, dem_grass, cost_with_request_options


def _run_or_get_generated_route(
    route: EvaluationRoute,
    *,
    paths,
    inputs,
    dem_grass: str | None,
    cost_grass: str | None,
    settings: EvaluationSettings,
    force_reroute: bool,
    reroute: bool,
    allow_area_route_fallback: bool,
) -> GeneratedRouteOutputs:
    expected = _expected_generated_outputs(paths, route.route_id, settings)
    if not force_reroute and _has_complete_cache(expected):
        return expected

    if not reroute:
        if allow_area_route_fallback:
            fallback = _area_route_fallback(paths, route.route_id, settings)
            if fallback is not None:
                return fallback
        raise FileNotFoundError(
            f"No cached generated route for {route.area_id}/{route.route_id}: {expected.route_path}. "
            "Run without --no-reroute to generate it."
        )

    if dem_grass is None or cost_grass is None:
        raise ValueError("Routing context is missing")

    from backend.routing_algorithm.routing.core import run_routing_for_tour
    from backend.routing_algorithm.routing.cost_surface_request import set_region_local

    set_region_local(
        cost_grass,
        start_xy=route.start_xy,
        end_xy=route.end_xy,
        buffer_m=float(app_config.ROUTING_SETTINGS["region_buffer_m"]),
    )

    run_routing_for_tour(
        paths=paths,
        inputs=inputs,
        tour_name=route.route_id,
        start_coords=route.start_xy,
        end_coords=route.end_xy,
        lambda_weight=float(app_config.ROUTING_SETTINGS["lambda_weight"]),
        smooth_threshold=float(app_config.ROUTING_SETTINGS["smooth_threshold"]),
        corridor_mode=str(app_config.RUN_DEBUG_ROUTING_PARAMS["corridor_mode"]),
        multi_routing=False,
        cost_surface_override=cost_grass,
        dem_override=dem_grass,
        preserve_region=True,
        output_mode="run",
        run_id=settings.evaluation_run_id,
        output_root=paths.evaluation_results / "routing",
        output_suffix=route.route_id,
    )

    generated = _expected_generated_outputs(paths, route.route_id, settings)
    return GeneratedRouteOutputs(
        route_path=generated.route_path,
        corridor_paths=generated.corridor_paths,
        used_cache=False,
        source="rerouted_from_evaluation_endpoints",
    )


def _route_metadata(route: EvaluationRoute) -> dict[str, Any]:
    props = {str(k).lower(): v for k, v in route.properties.items()}
    return {
        "reference_ates": props.get("ates", props.get("kast")),
        "reference_quality_level": props.get("kvalitetsnivå", props.get("kvalitetsniva")),
        "reference_source_crs": route.source_crs,
    }


def _evaluate_route(
    route: EvaluationRoute,
    *,
    generated: GeneratedRouteOutputs,
    paths,
    settings: EvaluationSettings,
    terrain_rasters: Mapping[str, str | Path] | None,
) -> dict[str, Any]:
    generated_line = load_line(generated.route_path, target_crs=settings.metric_crs)
    comparison = compare_routes(route.line, generated_line, settings=settings)

    row: dict[str, Any] = {
        "area_id": route.area_id,
        "study_area_id": route.area_id,
        "area_name": route.area_name,
        "route_id": route.route_id,
        "route_name": route.display_name,
        "status": "ok",
        "reference_path": str(route.source_path),
        "generated_path": str(generated.route_path),
        "generated_route_source": generated.source,
        "generated_route_used_cache": generated.used_cache,
    }
    row.update(_route_metadata(route))
    row.update(comparison_to_dict(comparison))
    row.update(evaluate_corridors(route.line, generated.corridor_paths, settings=settings))

    comparison_dir = paths.evaluation_results / "comparison_geojson" / settings.evaluation_run_id
    samples_dir = paths.evaluation_results / "deviation_samples" / settings.evaluation_run_id
    plots_dir = paths.evaluation_results / "plots" / settings.evaluation_run_id
    base_props = {"area_id": route.area_id, "route_id": route.route_id}

    comparison_path = write_comparison_geojson(
        comparison_dir / f"{route.route_id}_comparison.geojson",
        reference_line=route.line,
        generated_line=generated_line,
        crs=settings.metric_crs,
        properties=base_props,
    )
    gen_samples_path = write_deviation_samples_geojson(
        samples_dir / f"{route.route_id}_generated_to_reference.geojson",
        sampled_line=generated_line,
        target_line=route.line,
        crs=settings.metric_crs,
        sample_step_m=settings.sample_step_m,
        role="generated_to_reference",
        properties=base_props,
    )
    ref_samples_path = write_deviation_samples_geojson(
        samples_dir / f"{route.route_id}_reference_to_generated.geojson",
        sampled_line=route.line,
        target_line=generated_line,
        crs=settings.metric_crs,
        sample_step_m=settings.sample_step_m,
        role="reference_to_generated",
        properties=base_props,
    )
    row.update(
        {
            "comparison_geojson": str(comparison_path),
            "generated_to_reference_samples_geojson": str(gen_samples_path),
            "reference_to_generated_samples_geojson": str(ref_samples_path),
        }
    )

    if settings.make_plots:
        plot_path = plot_route_comparison(
            plots_dir / f"{route.route_id}.png",
            reference_line=route.line,
            generated_line=generated_line,
            sample_step_m=settings.sample_step_m,
            title=f"{route.area_id}/{route.route_id}",
        )
        if plot_path is not None:
            row["plot_path"] = str(plot_path)
        else:
            row["plot_status"] = "matplotlib_missing"

    if terrain_rasters:
        row.update(summarize_terrain_rasters(route.line, generated_line, terrain_rasters, settings=settings))

    return row


def _error_row(route: EvaluationRoute, error: Exception) -> dict[str, Any]:
    return {
        "area_id": route.area_id,
        "route_id": route.route_id,
        "route_name": route.display_name,
        "status": "error",
        "reference_path": str(route.source_path),
        "error": f"{type(error).__name__}: {error}",
    }


def _attach_run_metadata(
    row: dict[str, Any],
    *,
    settings: EvaluationSettings,
    track_influence_mode: str,
    avoid_lake: bool,
    avoid_glacier: bool,
    avoid_river: bool,
) -> dict[str, Any]:
    row.update(
        {
            "evaluation_run_id": settings.evaluation_run_id,
            "track_influence_mode": track_influence_mode,
            "routing_area_ids": ";".join(row.get("routing_area_ids", []))
            if isinstance(row.get("routing_area_ids"), list)
            else row.get("routing_area_ids", ""),
            "avoid_lake": avoid_lake,
            "avoid_glacier": avoid_glacier,
            "avoid_river": avoid_river,
        }
    )
    return row


def write_area_evaluation_outputs(
    area_id: str,
    rows: list[dict[str, Any]],
    *,
    settings: EvaluationSettings,
) -> None:
    paths, _ = load_area(area_id)
    results_dir = paths.evaluation_results
    write_csv(results_dir / "eval_metrics.csv", rows)
    write_simplified_route_metrics_csv(results_dir / "eval_metrics_simplified.csv", rows)
    write_json(
        results_dir / "eval_metrics.json",
        {
            "area_id": area_id,
            "settings": {
                "metric_crs": settings.metric_crs,
                "sample_step_m": settings.sample_step_m,
                "frechet_step_m": settings.frechet_step_m,
                "buffer_distances_m": list(settings.buffer_distances_m),
                "corridor_sample_step_m": settings.corridor_sample_step_m,
            },
            "rows": rows,
        },
    )
    write_markdown_summary(results_dir / "README.md", rows, title=f"Route Evaluation: {area_id}")
    write_csv(
        results_dir / "visual_review_candidates.csv",
        [
            row
            for row in rows
            if row.get("status") == "ok" and str(row.get("inspection_priority")) in {"high", "severe"}
        ],
    )
    write_standard_group_summaries(results_dir, rows)


def write_all_areas_evaluation_outputs(rows: list[dict[str, Any]], *, settings: EvaluationSettings) -> None:
    aggregate_dir = PROJECT_ROOT / "data" / "evaluation" / "evaluation_results"
    write_csv(aggregate_dir / "all_areas_eval_metrics.csv", rows)
    write_simplified_route_metrics_csv(aggregate_dir / "all_areas_eval_metrics_simplified.csv", rows)
    write_json(aggregate_dir / "all_areas_eval_metrics.json", {"rows": rows})
    write_markdown_summary(aggregate_dir / "README.md", rows, title="Route Evaluation: All Areas")
    write_csv(
        aggregate_dir / "visual_review_candidates.csv",
        [
            row
            for row in rows
            if row.get("status") == "ok" and str(row.get("inspection_priority")) in {"high", "severe"}
        ],
    )
    write_standard_group_summaries(aggregate_dir, rows)
    export_results_data_bundle(rows, project_root=PROJECT_ROOT)


def run_evaluation_for_area(
    area_id: str,
    *,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
    route_ids: set[str] | None = None,
    force_reroute: bool = False,
    reroute: bool = True,
    allow_area_route_fallback: bool = False,
    terrain_rasters: Mapping[str, str | Path] | None = None,
    track_influence_mode: str = str(app_config.RUN_DEBUG_ROUTING_PARAMS["track_influence_mode"]),
    avoid_lake: bool = bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_lake"]),
    avoid_glacier: bool = bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_glacier"]),
    avoid_river: bool = bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_river"]),
    write_outputs: bool = True,
) -> list[dict[str, Any]]:
    paths, inputs = load_area(area_id)
    routing_area_ids = routing_area_ids_for_study_area(area_id)
    routes = load_evaluation_routes(
        area_id,
        metric_crs=settings.metric_crs,
        route_ids=route_ids,
        provider_suffixes=settings.provider_suffixes,
    )
    if not routes:
        return []

    dem_grass = None
    cost_grass = None
    if reroute:
        paths, inputs, dem_grass, cost_grass = _prepare_routing_context(
            area_id,
            routing_area_ids=routing_area_ids,
            track_influence_mode=track_influence_mode,
            avoid_lake=avoid_lake,
            avoid_glacier=avoid_glacier,
            avoid_river=avoid_river,
        )

    rows: list[dict[str, Any]] = []
    for route in routes:
        try:
            generated = _run_or_get_generated_route(
                route,
                paths=paths,
                inputs=inputs,
                dem_grass=dem_grass,
                cost_grass=cost_grass,
                settings=settings,
                force_reroute=force_reroute,
                reroute=reroute,
                allow_area_route_fallback=allow_area_route_fallback,
            )
            row = _evaluate_route(
                route,
                generated=generated,
                paths=paths,
                settings=settings,
                terrain_rasters=terrain_rasters,
            )
        except Exception as exc:
            row = _error_row(route, exc)
        row["area_name"] = route.area_name
        row["study_area_id"] = route.area_id
        row["routing_area_ids"] = routing_area_ids
        row = _attach_run_metadata(
            row,
            settings=settings,
            track_influence_mode=track_influence_mode,
            avoid_lake=avoid_lake,
            avoid_glacier=avoid_glacier,
            avoid_river=avoid_river,
        )
        rows.append(row)

    if write_outputs:
        write_area_evaluation_outputs(area_id, rows, settings=settings)
    return rows


def run_evaluation_for_all_areas(
    area_ids: list[str] | None = None,
    *,
    settings: EvaluationSettings = DEFAULT_SETTINGS,
    route_ids: set[str] | None = None,
    force_reroute: bool = False,
    reroute: bool = True,
    allow_area_route_fallback: bool = False,
    terrain_rasters: Mapping[str, str | Path] | None = None,
    track_influence_mode: str = str(app_config.RUN_DEBUG_ROUTING_PARAMS["track_influence_mode"]),
    avoid_lake: bool = bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_lake"]),
    avoid_glacier: bool = bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_glacier"]),
    avoid_river: bool = bool(app_config.RUN_DEBUG_ROUTING_PARAMS["avoid_river"]),
    write_outputs: bool = True,
) -> list[dict[str, Any]]:
    if area_ids is None:
        area_ids = discover_areas_with_evaluation_routes(PROJECT_ROOT)

    all_rows: list[dict[str, Any]] = []
    for area_id in area_ids:
        rows = run_evaluation_for_area(
            area_id,
            settings=settings,
            route_ids=route_ids,
            force_reroute=force_reroute,
            reroute=reroute,
            allow_area_route_fallback=allow_area_route_fallback,
            terrain_rasters=terrain_rasters,
            track_influence_mode=track_influence_mode,
            avoid_lake=avoid_lake,
            avoid_glacier=avoid_glacier,
            avoid_river=avoid_river,
            write_outputs=write_outputs,
        )
        all_rows.extend(rows)

    if write_outputs:
        write_all_areas_evaluation_outputs(all_rows, settings=settings)
    return all_rows
