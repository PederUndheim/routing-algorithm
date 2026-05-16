from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.testing import config
from backend.routing_algorithm.testing.paths import TestingAreaPaths


def _linear_rescale_on_mask(
    src: np.ndarray,
    mask: np.ndarray,
    in_min: float,
    in_max: float,
    out_min: float,
    out_max: float,
) -> np.ndarray:
    out = src.astype(np.float32, copy=True)
    if not np.any(mask):
        return out

    rng = float(in_max - in_min)
    if rng <= 0:
        out[mask] = np.float32(0.5 * (out_min + out_max))
        return out

    v = np.clip(src, in_min, in_max)
    scaled = (v - in_min) / rng
    out_vals = out_min + scaled * (out_max - out_min)
    out[mask] = out_vals[mask].astype(np.float32)
    return out


def build_testing_pra_runout_layer(paths: TestingAreaPaths, inputs: dict[str, Path]) -> Path:
    params = config.PRA_RUNOUT_PARAMS
    output_path = paths.pra_runout_combined

    with rasterio.open(inputs["travel_distance"]) as td_src, rasterio.open(inputs["pra_raw"]) as pra_src:
        distance = td_src.read(1).astype(np.float32)
        pra_raw = pra_src.read(1).astype(np.float32)

        if distance.shape != pra_raw.shape:
            raise ValueError("travel_distance and pra_raw must have the same shape")

        out = np.full(
            distance.shape,
            float(params["output_nodata"]),
            dtype=np.float32,
        )

        release_threshold = float(params["release_threshold"])
        is_release = pra_raw >= release_threshold
        is_runout = (
            (~is_release)
            & (distance > float(params["runout_distance_min"]))
            & (distance < float(params["runout_distance_max"]))
        )

        release_scaled = _linear_rescale_on_mask(
            pra_raw,
            is_release,
            release_threshold,
            float(params["release_input_max"]),
            float(params["release_min"]),
            float(params["release_max"]),
        )
        out[is_release] = release_scaled[is_release]

        distance_lambda = float(params["distance_lambda"])
        distance_alpha = float(params["distance_alpha"])
        runout_unit = np.exp(
            -np.power(distance_lambda * distance.astype(np.float64), distance_alpha)
        ).astype(np.float32)
        runout_scaled = _linear_rescale_on_mask(
            runout_unit,
            is_runout,
            0.0,
            0.99,
            float(params["runout_min"]),
            float(params["runout_max"]),
        )
        out[is_runout] = runout_scaled[is_runout]

        profile = pra_src.profile.copy()
        profile.update(
            dtype=rasterio.float32,
            count=1,
            compress="lzw",
            nodata=float(params["output_nodata"]),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(out, 1)

    print(f"Testing PRA/runout layer written to {output_path}")
    return output_path


def build_for_area(area_id: str, *, experiment: str = config.DEFAULT_EXPERIMENT) -> Path:
    paths = TestingAreaPaths(area_id=area_id, experiment=experiment)
    _, inputs = load_area(area_id)
    return build_testing_pra_runout_layer(paths, inputs)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the testing-only PRA/runout input layer for one area."
    )
    parser.add_argument("area", help="Area ID, e.g. isfjorden_01")
    parser.add_argument(
        "--experiment",
        default=config.DEFAULT_EXPERIMENT,
        help=f"Name under data/testing/. Default: {config.DEFAULT_EXPERIMENT}",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_for_area(args.area, experiment=args.experiment)


if __name__ == "__main__":
    main()
