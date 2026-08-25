from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import rasterio

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.cost_surface.raster_helpers import debug_layer_save, read_mask, read_raster
from backend.routing_algorithm.testing import config
from backend.routing_algorithm.testing.paths import TestingAreaPaths
from backend.routing_algorithm.testing.pra_runout import build_testing_pra_runout_layer
from backend.routing_algorithm.testing.transforms import curvature_cost, slope_cost


def _layer_from_mask(
    mask: np.ndarray,
    *,
    expected_shape: tuple[int, ...],
    feature_value: float,
    elsewhere_value: float,
    name: str,
) -> np.ndarray:
    if mask.shape != expected_shape:
        raise ValueError(f"{name} mask must have the same shape as the terrain rasters")
    return np.where(mask, feature_value, elsewhere_value).astype(np.float32, copy=False)


def _smooth_gate_below(x: np.ndarray, *, threshold: float, width: float) -> np.ndarray:
    x = x.astype(np.float32, copy=False)
    k = 6.0 / float(width)
    gate_exp = np.clip(k * (x - threshold), -60.0, 60.0)
    return (1.0 / (1.0 + np.exp(gate_exp))).astype(np.float32, copy=False)


def _soft_reduction_from_mask(
    mask: np.ndarray,
    validity_weight: np.ndarray,
    *,
    expected_shape: tuple[int, ...],
    low_value: float,
    elsewhere_value: float,
    name: str,
) -> np.ndarray:
    if mask.shape != expected_shape:
        raise ValueError(f"{name} mask must have the same shape as the terrain rasters")
    validity_weight = np.clip(validity_weight, 0.0, 1.0).astype(np.float32, copy=False)
    out = np.full(expected_shape, elsewhere_value, dtype=np.float32)
    blended = elsewhere_value - validity_weight * (elsewhere_value - low_value)
    out[mask.astype(bool)] = blended[mask.astype(bool)]
    return out


def _steep_slope_barrier(
    slope: np.ndarray,
    *,
    start_deg: float,
    full_deg: float,
    start_value: float,
    barrier_value: float,
    power: float,
) -> np.ndarray:
    if full_deg <= start_deg:
        raise ValueError("Steep slope barrier full_deg must be greater than start_deg")
    if power <= 0:
        raise ValueError("Steep slope barrier power must be > 0")

    slope_filled = np.where(np.isnan(slope), start_deg - 1.0, slope).astype(np.float32, copy=False)
    t = np.clip((slope_filled - start_deg) / (full_deg - start_deg), 0.0, 1.0)
    ramp = np.power(t, power).astype(np.float32, copy=False)
    barrier = start_value + ramp * (barrier_value - start_value)
    barrier = np.where(slope_filled < start_deg, config.MIN_COST, barrier)
    return barrier.astype(np.float32, copy=False)


def create_cost_surface(paths: TestingAreaPaths, inputs: dict[str, Path], debug_mode: bool) -> Path:
    output_path = paths.cost_surface_output
    runtime_path = paths.cost_surface

    with rasterio.open(inputs["slope"]) as ref:
        profile = ref.profile.copy()

    slope, _ = read_raster(inputs["slope"])
    windshelter, _ = read_raster(inputs["curvature"])
    pra_runout, _ = read_raster(inputs["pra_runout_combined"])

    windshelter = np.nan_to_num(windshelter, nan=0.0).astype(np.float32, copy=False)
    pra_runout = np.where(np.isnan(pra_runout), 1.0, pra_runout).astype(np.float32, copy=False)

    if windshelter.shape != slope.shape or pra_runout.shape != slope.shape:
        raise ValueError("slope, windshelter, and pra_runout_combined must have the same shape")

    slope_layer = slope_cost(
        config.SLOPE_TRANSFORM,
        slope,
        **config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"],
    )
    windshelter_layer = curvature_cost(windshelter, **config.TRANSFORM_PARAMS["windshelter"])
    pra_runout_layer = pra_runout

    weights = config.WEIGHTS_TERRAIN
    weight_sum = (
        float(weights["slope"])
        + float(weights["windshelter"])
        + float(weights["pra_runout_combined"])
    )
    if not np.isclose(weight_sum, 1.0):
        raise ValueError(f"Testing terrain weights must sum to 1.0, got {weight_sum:.6f}")

    surface = (
        slope_layer * float(weights["slope"])
        + windshelter_layer * float(weights["windshelter"])
        + pra_runout_layer * float(weights["pra_runout_combined"])
    )

    if debug_mode:
        paths.debug_cost_layer_dir.mkdir(parents=True, exist_ok=True)
        debug_layer_save(slope_layer, "01_slope_cost.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(windshelter_layer, "02_windshelter_cost.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(pra_runout_layer, "03_pra_runout_combined_cost.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(surface, "04_weighted_sum.tif", profile, paths.debug_cost_layer_dir)

    # river_barrier = _layer_from_mask(
    #     read_mask(inputs["river"]),
    #     expected_shape=slope.shape,
    #     feature_value=config.RIVER_BARRIER_VALUE,
    #     elsewhere_value=config.MIN_COST,
    #     name="river",
    # )
    # with_barriers = np.maximum(surface, river_barrier)

    safe_params = config.SAFE_MASK_SOFT_PARAMS
    slope_w = _smooth_gate_below(
        slope,
        threshold=float(safe_params["slope_threshold"]),
        width=float(safe_params["slope_width"]),
    )
    pra_runout_w = _smooth_gate_below(
        pra_runout_layer,
        threshold=float(safe_params["pra_runout_combined_threshold"]),
        width=float(safe_params["pra_runout_combined_width"]),
    )
    validity_w = slope_w * pra_runout_w

    road_reduction = _soft_reduction_from_mask(
        read_mask(inputs["road"]),
        validity_w,
        expected_shape=slope.shape,
        low_value=config.ROAD_REDUCTION_VALUE,
        elsewhere_value=config.MAX_COST,
        name="road",
    )
    trail_reduction = _soft_reduction_from_mask(
        read_mask(inputs[config.TRAIL_INPUT_KEY]),
        validity_w,
        expected_shape=slope.shape,
        low_value=config.TRAIL_REDUCTION_VALUE,
        elsewhere_value=config.MAX_COST,
        name=config.TRAIL_INPUT_KEY,
    )
    bridge_mask = read_mask(inputs["bridge"])
    bridge_validity_w = np.where(bridge_mask.astype(bool), 1.0, validity_w).astype(np.float32, copy=False)
    bridge_reduction = _soft_reduction_from_mask(
        bridge_mask,
        bridge_validity_w,
        expected_shape=slope.shape,
        low_value=config.BRIDGE_REDUCTION_VALUE,
        elsewhere_value=config.MAX_COST,
        name="bridge",
    )
    # with_reductions = np.minimum(with_barriers, road_reduction)
    with_reductions = np.minimum(surface, road_reduction)
    with_reductions = np.minimum(with_reductions, trail_reduction)
    with_reductions = np.minimum(with_reductions, bridge_reduction)

    final_surface = with_reductions
    steep_barrier = None
    barrier_params = config.STEEP_SLOPE_BARRIER_PARAMS
    if bool(barrier_params["enabled"]):
        slope_params = config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"]
        start_value = float(
            barrier_params.get("start_value", slope_params.get("tail_end_cost", config.MIN_COST))
        )
        steep_barrier = _steep_slope_barrier(
            slope,
            start_deg=float(barrier_params["start_deg"]),
            full_deg=float(barrier_params["full_deg"]),
            start_value=start_value,
            barrier_value=float(barrier_params["barrier_value"]),
            power=float(barrier_params["power"]),
        )
        final_surface = np.maximum(final_surface, steep_barrier)

    if debug_mode:
        # debug_layer_save(river_barrier, "05a_river_barrier.tif", profile, paths.debug_cost_layer_dir)
        # debug_layer_save(with_barriers, "05b_with_river_barrier.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(slope_w, "06a_safe_slope_weight.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(pra_runout_w, "06b_safe_pra_runout_weight.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(validity_w, "06c_safe_reduction_weight.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(road_reduction, "06d_road_reduction_safe.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(trail_reduction, "06e_trail_forest_reduction_safe.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(bridge_reduction, "06f_bridge_reduction.tif", profile, paths.debug_cost_layer_dir)
        debug_layer_save(with_reductions, "07_with_reductions.tif", profile, paths.debug_cost_layer_dir)
        if steep_barrier is not None:
            debug_layer_save(steep_barrier, "08a_steep_slope_barrier.tif", profile, paths.debug_cost_layer_dir)
            debug_layer_save(final_surface, "08b_final_with_steep_slope_barrier.tif", profile, paths.debug_cost_layer_dir)

    nodata_mask = np.isnan(slope)
    surface_u16 = np.round(np.clip(final_surface, config.MIN_COST, config.MAX_COST)).astype(
        np.uint16,
        copy=False,
    )
    surface_u16[nodata_mask] = config.NODATA_VALUE

    profile.update(dtype=rasterio.uint16, count=1, compress="lzw", nodata=config.NODATA_VALUE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(surface_u16, 1)

    shutil.copy2(output_path, runtime_path)
    print(f"Testing cost surface written to {output_path}")
    print(f"Testing runtime cost surface synced to {runtime_path}")
    return runtime_path


def create_testing_cost_surface(
    area_id: str,
    *,
    experiment: str = config.DEFAULT_EXPERIMENT,
    debug_mode: bool = True,
) -> tuple[TestingAreaPaths, Path]:
    paths = TestingAreaPaths(area_id=area_id, experiment=experiment)
    _, inputs = load_area(area_id)
    inputs = dict(inputs)
    inputs["pra_runout_combined"] = build_testing_pra_runout_layer(paths, inputs)
    return paths, create_cost_surface(paths, inputs, debug_mode=debug_mode)
