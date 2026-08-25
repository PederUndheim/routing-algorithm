from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from backend import config
from backend.file_handler.area_context import PROJECT_ROOT, load_area
from backend.routing_algorithm.routing.core import init_grass, run_routing_for_tour
from backend.routing_algorithm.routing.cost_surface_request import (
    compose_cost_surface_for_request,
    set_region_local,
)
from backend.routing_algorithm.routing.grass_mosaic import build_or_get_mosaic
from backend.routing_algorithm.testing import config as testing_config
from backend.routing_algorithm.tours.load_tours import Tour, load_tours_json
from backend.scripts.run_routing import export_wgs84_geojson

from backend.routing_algorithm.routing.grass_env import setup_grass_python_path

setup_grass_python_path()
import grass.script as gs


TOURS_JSON = Path("backend/routing_algorithm/tours/tours.json")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "testing" / "routing_track_inspection"

MODE_TO_TRACK_INFLUENCE = {
    "normal": "off",
    "forest_only": "forest_only",
    "balanced": "balanced",
    "strong": "strong",
}


@dataclass(frozen=True)
class TrackInspectionPaths:
    area_id: str
    mode_label: str
    output_root: Path = DEFAULT_OUTPUT_ROOT
    project_root: Path = PROJECT_ROOT

    @property
    def root(self) -> Path:
        return self.output_root / self.area_id / self.mode_label

    @property
    def runtime_area_root(self) -> Path:
        return self.project_root / "data" / "runtime" / "areas" / self.area_id

    @property
    def dem(self) -> Path:
        return self.runtime_area_root / "dem.tif"

    @property
    def cost_surface(self) -> Path:
        return self.runtime_area_root / "cost_surface.tif"

    @property
    def corridor(self) -> Path:
        return self.root / "corridor"

    @property
    def route_dir(self) -> Path:
        return self.root / "route" / "native"

    @property
    def route_wgs84(self) -> Path:
        return self.root / "route" / "wgs84"

    @property
    def multirouting_dir(self) -> Path:
        return self.root / "multirouting"

    @property
    def multirouting_native(self) -> Path:
        return self.multirouting_dir / "native"

    @property
    def multirouting_wgs84(self) -> Path:
        return self.multirouting_dir / "wgs84"

    @property
    def multirouting_heatmap(self) -> Path:
        return self.multirouting_dir / "heatmap"


def _safe_slug(name: str) -> str:
    s = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name.lower())
    if s and s[0].isdigit():
        s = "_" + s
    return s


def _print_cost_difference_stats(base_cost_name: str, cost_name: str, label: str) -> None:
    if cost_name == base_cost_name:
        print(f"Cost raster: {cost_name} (same as normal base cost)")
        return

    diff_name = f"track_inspection_delta_{_safe_slug(label)}"
    gs.mapcalc(f"{diff_name} = {base_cost_name} - {cost_name}", overwrite=True)
    txt = gs.read_command("r.univar", map=diff_name, flags="g").strip().splitlines()
    stats = dict(line.split("=", 1) for line in txt if "=" in line)
    print(
        "Cost raster: "
        f"{cost_name} | reduction min={stats.get('min', '?')} "
        f"mean={stats.get('mean', '?')} max={stats.get('max', '?')}"
    )


def _filter_tours(
    tours: List[Tour],
    *,
    allowed_names: set[str],
    tour_name: str | None,
) -> List[Tour]:
    if tour_name is not None:
        selected = [tour for tour in tours if tour.name == tour_name]
        if not selected:
            available = ", ".join(tour.name for tour in tours)
            raise ValueError(f"Tour '{tour_name}' not found. Available tours: {available}")
        return selected

    return [tour for tour in tours if tour.name in allowed_names]


def _export_cost_surface(cost_name: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gs.run_command(
        "r.out.gdal",
        input=cost_name,
        output=str(out_path),
        format="GTiff",
        flags="c",
        type="Float32",
        nodata=-9999,
        overwrite=True,
        quiet=True,
    )


def _run_mode_for_area(
    *,
    area_id: str,
    mode_label: str,
    track_influence_mode: str,
    tours: List[Tour],
    dem_grass: str,
    base_cost_grass: str,
    inputs: dict,
    output_root: Path,
    multi_routing: bool,
    export_cost_surfaces: bool,
) -> Dict[str, Dict]:
    paths = TrackInspectionPaths(
        area_id=area_id,
        mode_label=mode_label,
        output_root=output_root,
    )

    print("\n------------------------------------")
    print(f"[{area_id}] Mode: {mode_label} | track_influence_mode={track_influence_mode}")

    gs.run_command("g.region", raster=dem_grass, flags="a", quiet=True)
    cost_for_mode = compose_cost_surface_for_request(
        area_ids=[area_id],
        base_cost_name=base_cost_grass,
        avoid_lake=bool(config.RUN_DEBUG_ROUTING_PARAMS["avoid_lake"]),
        avoid_glacier=bool(config.RUN_DEBUG_ROUTING_PARAMS["avoid_glacier"]),
        avoid_river=bool(config.RUN_DEBUG_ROUTING_PARAMS["avoid_river"]),
        track_influence_mode=track_influence_mode,
    )
    if track_influence_mode != "off" and cost_for_mode == base_cost_grass:
        print(
            "WARNING: Track influence returned the normal base cost raster. "
            "Check track normalization and track/forest rasters."
        )
    _print_cost_difference_stats(base_cost_grass, cost_for_mode, f"{area_id}_{mode_label}")

    if export_cost_surfaces:
        _export_cost_surface(
            cost_for_mode,
            paths.root / "cost_surface" / f"{mode_label}_request_cost_surface.tif",
        )

    mode_outputs: Dict[str, Dict] = {}
    for tour in tours:
        print(f"\n--- {area_id} | {mode_label} | {tour.name} ---")
        set_region_local(
            cost_for_mode,
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
            lambda_weight=float(config.ROUTING_SETTINGS["lambda_weight"]),
            smooth_threshold=float(config.ROUTING_SETTINGS["smooth_threshold"]),
            multi_routing=multi_routing,
            cost_surface_override=cost_for_mode,
            dem_override=dem_grass,
            preserve_region=True,
            output_mode="area",
            output_suffix=mode_label,
        )

        slug = _safe_slug(tour.name)
        if "path_geojson_native" in res:
            wgs84_geojson = export_wgs84_geojson(
                native_geojson_path=res["path_geojson_native"],
                out_basename=f"{slug}_{mode_label}_wgs84",
                out_dir=paths.route_wgs84,
            )
            res["path_geojson_wgs84"] = str(wgs84_geojson)

        if "multi_routing_routes_geojson" in res:
            out_dir = paths.multirouting_wgs84 / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            wgs84_multi: List[str] = []
            for i, route_path in enumerate(res["multi_routing_routes_geojson"], start=1):
                out_path = export_wgs84_geojson(
                    native_geojson_path=route_path,
                    out_basename=f"{slug}_{mode_label}_{i:02d}_wgs84",
                    out_dir=out_dir,
                )
                wgs84_multi.append(str(out_path))
            res["multi_routing_routes_geojson_wgs84"] = wgs84_multi

        mode_outputs[tour.name] = res

    return mode_outputs


def run_track_inspection(
    *,
    area_ids: List[str],
    mode_labels: List[str],
    tour_name: str | None,
    output_root: Path,
    multi_routing: bool,
    export_cost_surfaces: bool,
) -> Dict[str, Dict[str, Dict[str, Dict]]]:
    tours_by_area = load_tours_json(TOURS_JSON)
    summary: Dict[str, Dict[str, Dict[str, Dict]]] = {}

    for area_id in area_ids:
        if area_id not in tours_by_area:
            raise ValueError(f"Area '{area_id}' not found in {TOURS_JSON}")

        tours = _filter_tours(
            tours_by_area[area_id],
            allowed_names=testing_config.DEFAULT_TEST_TOURS,
            tour_name=tour_name,
        )
        if not tours:
            print(f"No selected tours found for {area_id}; skipping.")
            continue

        paths, inputs = load_area(area_id)
        if not paths.cost_surface.exists():
            raise FileNotFoundError(
                f"Normal runtime cost surface missing for {area_id}: {paths.cost_surface}. "
                "Build/export the normal cost surface first."
            )

        print("\n====================================")
        print(f"=== Track inspection area: {area_id} ===")
        print(f"Tours: {', '.join(tour.name for tour in tours)}")

        dem_grass = build_or_get_mosaic([area_id], kind="dem", force_import=True)
        base_cost_grass = build_or_get_mosaic([area_id], kind="cost", force_import=True)

        if any(MODE_TO_TRACK_INFLUENCE[mode] != "off" for mode in mode_labels):
            build_or_get_mosaic([area_id], kind="tracks", force_import=True)
            build_or_get_mosaic([area_id], kind="forest", force_import=True)

        summary[area_id] = {}
        for mode_label in mode_labels:
            summary[area_id][mode_label] = _run_mode_for_area(
                area_id=area_id,
                mode_label=mode_label,
                track_influence_mode=MODE_TO_TRACK_INFLUENCE[mode_label],
                tours=tours,
                dem_grass=dem_grass,
                base_cost_grass=base_cost_grass,
                inputs=inputs,
                output_root=output_root,
                multi_routing=multi_routing,
                export_cost_surfaces=export_cost_surfaces,
            )

    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "routing_track_inspection_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n=== Track inspection complete ===")
    print(f"Output root: {output_root}")
    print(f"Summary: {summary_path}")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Route the default testing tours with normal routing and each track "
            "influence mode, writing outputs under data/testing/routing_track_inspection."
        )
    )
    parser.add_argument(
        "--area",
        help=(
            "Area ID, e.g. isfjorden_01. If omitted, the default testing areas "
            "are processed."
        ),
    )
    parser.add_argument(
        "--tour",
        help="Optional exact tour name from backend/routing_algorithm/tours/tours.json.",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=list(MODE_TO_TRACK_INFLUENCE),
        default=list(MODE_TO_TRACK_INFLUENCE),
        help="Modes to run. Default: normal forest_only balanced strong.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Output root. Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--multi-routing",
        action="store_true",
        help="Run multi-routing instead of the single best route.",
    )
    parser.add_argument(
        "--export-cost-surfaces",
        action="store_true",
        help="Also export the request cost surface for each mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    init_grass()

    area_ids = [args.area] if args.area else list(testing_config.DEFAULT_TEST_AREAS)
    run_track_inspection(
        area_ids=area_ids,
        mode_labels=list(args.modes),
        tour_name=args.tour,
        output_root=args.output_root,
        multi_routing=bool(args.multi_routing),
        export_cost_surfaces=bool(args.export_cost_surfaces),
    )


if __name__ == "__main__":
    main()
