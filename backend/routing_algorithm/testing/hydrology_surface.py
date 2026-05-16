from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio

from backend import config
from backend.file_handler.area_context import PROJECT_ROOT, load_area
from backend.routing_algorithm.cost_surface.raster_helpers import debug_layer_save, read_mask


DEFAULT_AREA_ID = "isfjorden_01"
DEFAULT_EXPERIMENT = "hydrology_barriers"
OUTPUT_FILENAME = "cost_surface_with_river_lake_glacier.tif"


def _experiment_root(area_id: str, experiment: str) -> Path:
    return PROJECT_ROOT / "data" / "testing" / experiment / area_id


def _default_base_cost_surface(area_id: str) -> Path:
    area_paths, _ = load_area(area_id)
    return area_paths.cost_surface_output


def _write_summary(
    *,
    output_path: Path,
    base_cost_surface: Path,
    river_mask: np.ndarray,
    river_without_bridge_mask: np.ndarray,
    bridge_mask: np.ndarray,
    lake_mask: np.ndarray,
    glacier_mask: np.ndarray,
    combined_mask: np.ndarray,
) -> Path:
    summary_path = output_path.parent.parent / "hydrology_surface_summary.json"
    summary = {
        "base_cost_surface": str(base_cost_surface),
        "output_cost_surface": str(output_path),
        "barrier_cost": int(config.BARRIER_COST),
        "feature_pixel_counts": {
            "river_total": int(np.count_nonzero(river_mask)),
            "bridge_total": int(np.count_nonzero(bridge_mask)),
            "river_without_bridge": int(np.count_nonzero(river_without_bridge_mask)),
            "lake": int(np.count_nonzero(lake_mask)),
            "glacier": int(np.count_nonzero(glacier_mask)),
            "combined_hydrology_barrier": int(np.count_nonzero(combined_mask)),
        },
        "notes": [
            "River, lake, and glacier cells are set to the hard barrier cost.",
            "Bridge cells are excluded from the combined hydrology barrier so marked crossings remain passable.",
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary_path


def build_hydrology_cost_surface(
    area_id: str = DEFAULT_AREA_ID,
    *,
    experiment: str = DEFAULT_EXPERIMENT,
    base_cost_surface: Path | None = None,
    debug_mode: bool = True,
) -> Path:
    area_paths, inputs = load_area(area_id)
    base_cost_surface = base_cost_surface or area_paths.cost_surface_output
    if not base_cost_surface.exists():
        raise FileNotFoundError(
            f"Base cost surface not found: {base_cost_surface}. "
            "Build the normal area cost surface first, or pass --base-cost-surface."
        )

    with rasterio.open(base_cost_surface) as src:
        base_surface = src.read(1)
        profile = src.profile.copy()
        source_nodata = src.nodata

    river_mask = read_mask(inputs["river"])
    bridge_mask = read_mask(inputs["bridge"])
    lake_mask = read_mask(inputs["lake"])
    glacier_mask = read_mask(inputs["glacier"])

    expected_shape = base_surface.shape
    masks = {
        "river": river_mask,
        "bridge": bridge_mask,
        "lake": lake_mask,
        "glacier": glacier_mask,
    }
    for name, mask in masks.items():
        if mask.shape != expected_shape:
            raise ValueError(
                f"{name} mask shape {mask.shape} does not match base cost surface shape {expected_shape}"
            )

    river_without_bridge_mask = river_mask & ~bridge_mask
    combined_hydrology_mask = (river_mask | lake_mask | glacier_mask) & ~bridge_mask

    final_surface = base_surface.astype(np.uint16, copy=True)
    nodata_mask = (
        base_surface == source_nodata
        if source_nodata is not None
        else np.zeros(expected_shape, dtype=bool)
    )
    final_surface[combined_hydrology_mask & ~nodata_mask] = np.uint16(config.BARRIER_COST)
    final_surface[nodata_mask] = np.uint16(config.NODATA_VALUE)

    output_dir = _experiment_root(area_id, experiment) / "cost_surface"
    output_path = output_dir / OUTPUT_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profile.update(
        dtype=rasterio.uint16,
        count=1,
        compress="lzw",
        nodata=config.NODATA_VALUE,
    )
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(final_surface, 1)

    if debug_mode:
        debug_dir = output_dir / "debug_layers"
        debug_layer_save(river_without_bridge_mask.astype(np.uint8), "01_river_without_bridge_mask.tif", profile, debug_dir)
        debug_layer_save(lake_mask.astype(np.uint8), "02_lake_mask.tif", profile, debug_dir)
        debug_layer_save(glacier_mask.astype(np.uint8), "03_glacier_mask.tif", profile, debug_dir)
        debug_layer_save(combined_hydrology_mask.astype(np.uint8), "04_combined_hydrology_barrier_mask.tif", profile, debug_dir)

    summary_path = _write_summary(
        output_path=output_path,
        base_cost_surface=base_cost_surface,
        river_mask=river_mask,
        river_without_bridge_mask=river_without_bridge_mask,
        bridge_mask=bridge_mask,
        lake_mask=lake_mask,
        glacier_mask=glacier_mask,
        combined_mask=combined_hydrology_mask,
    )

    print(f"Hydrology cost surface written to {output_path}")
    print(f"Hydrology summary written to {summary_path}")
    return output_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a testing-only cost surface with river, lake, and glacier barriers."
    )
    parser.add_argument(
        "--area",
        default=DEFAULT_AREA_ID,
        help=f"Area ID. Default: {DEFAULT_AREA_ID}",
    )
    parser.add_argument(
        "--experiment",
        default=DEFAULT_EXPERIMENT,
        help=f"Folder name under data/testing/. Default: {DEFAULT_EXPERIMENT}",
    )
    parser.add_argument(
        "--base-cost-surface",
        type=Path,
        help="Optional base cost-surface GeoTIFF to refine. Defaults to the normal area output cost surface.",
    )
    parser.add_argument(
        "--no-debug-layers",
        action="store_true",
        help="Do not write the hydrology debug masks.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_hydrology_cost_surface(
        area_id=args.area,
        experiment=args.experiment,
        base_cost_surface=args.base_cost_surface,
        debug_mode=not bool(args.no_debug_layers),
    )


if __name__ == "__main__":
    main()
