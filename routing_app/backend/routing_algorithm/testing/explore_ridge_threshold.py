from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.cost_surface.raster_helpers import read_raster
from backend.routing_algorithm.testing.paths import TestingAreaPaths

# Run: python -m backend.routing_algorithm.testing.explore_ridge_threshold

DEFAULT_AREA_IDS = ["isfjorden_01", "jotunheimen_01"]
DEFAULT_EXPERIMENT = "ridge_exposure_threshold"
DEFAULT_THRESHOLDS = [-0.15, -0.2, -0.25, -0.3, -0.4, -0.5, -0.6]

THRESHOLD_NODATA = 255


def _threshold_filename(threshold: float) -> str:
    return f"ridge_lt_{threshold:+.2f}.tif"


def explore_ridge_thresholds(
    area_id: str,
    *,
    thresholds: list[float] = DEFAULT_THRESHOLDS,
    experiment: str = DEFAULT_EXPERIMENT,
) -> dict:
    """
    For one area, write a binary mask per candidate threshold (1 = windshelter
    <= threshold, i.e. flagged as an exposed ridge; 0 = not flagged; 255 = nodata)
    so each can be dropped straight into ArcGIS and toggled to see which
    threshold traces the ridgelines you'd expect and which is too strict/loose.
    Also reports what fraction of the area each threshold flags, since the
    visual read alone doesn't tell you if a threshold is barely catching the
    sharpest crests or already eating whole slopes.
    """
    paths = TestingAreaPaths(area_id=area_id, experiment=experiment)
    _, inputs = load_area(area_id)

    windshelter, profile = read_raster(inputs["curvature"])
    valid = ~np.isnan(windshelter)
    valid_count = int(valid.sum())

    out_dir = paths.ridge_threshold_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    out_profile = profile.copy()
    out_profile.update(dtype=rasterio.uint8, count=1, compress="lzw", nodata=THRESHOLD_NODATA)

    results = []
    for threshold in thresholds:
        flagged = valid & (windshelter <= threshold)
        mask = np.full(windshelter.shape, THRESHOLD_NODATA, dtype=np.uint8)
        mask[valid] = flagged[valid].astype(np.uint8)

        out_path = out_dir / _threshold_filename(threshold)
        with rasterio.open(out_path, "w", **out_profile) as dst:
            dst.write(mask, 1)

        flagged_count = int(flagged.sum())
        pct = 100.0 * flagged_count / valid_count if valid_count else 0.0
        results.append(
            {
                "threshold": threshold,
                "output": str(out_path),
                "flagged_pixels": flagged_count,
                "valid_pixels": valid_count,
                "flagged_pct_of_valid_area": round(pct, 3),
            }
        )
        print(f"  {area_id}  threshold <= {threshold:+.2f}  ->  {pct:6.2f}% of valid area flagged  ({out_path.name})")

    summary_path = out_dir.parent / "threshold_summary.json"
    summary = {"area_id": area_id, "thresholds": results}
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"  summary written to {summary_path}")

    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract binary exposed-ridge masks (windshelter <= threshold) for one or more "
            "test areas, one GeoTIFF per threshold, for visual calibration in ArcGIS."
        )
    )
    parser.add_argument(
        "--areas",
        nargs="+",
        default=DEFAULT_AREA_IDS,
        help=f"Area IDs to process. Default: {DEFAULT_AREA_IDS}",
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help=f"Candidate windshelter thresholds. Default: {DEFAULT_THRESHOLDS}",
    )
    parser.add_argument(
        "--experiment",
        default=DEFAULT_EXPERIMENT,
        help=f"Folder name under data/testing/. Default: {DEFAULT_EXPERIMENT}",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    for area_id in args.areas:
        print(f"=== {area_id} ===")
        explore_ridge_thresholds(area_id, thresholds=args.thresholds, experiment=args.experiment)


if __name__ == "__main__":
    main()
