import shutil

import rasterio
import numpy as np

from typing import Dict
from pathlib import Path
from backend import config  
from backend.file_handler.area_paths import AreaPaths
from backend.routing_algorithm.cost_surface.raster_helpers import read_raster, read_mask, debug_layer_save                        
from backend.routing_algorithm.cost_surface.transforms import slope_cost, windshelter_cost
from backend.routing_algorithm.cost_surface.layers import (
    barrier_layer_from_mask,
    reduction_layer_from_mask_soft,
    smooth_gate_below,
    steep_slope_barrier,
)
from backend.routing_algorithm.cost_surface.combine import weighted_sum, min_combine, max_combine, clip_round

np.seterr(all='ignore')  # ignore warnings for NaNs


def _normalize_tracks_like_request(tracks_arr: np.ndarray) -> np.ndarray:
    """Normalize tracks to [0, 1], mirroring request-time track shaping."""
    tracks = tracks_arr.astype(np.float32, copy=False)
    tracks = np.where(np.isnan(tracks), 0.0, tracks)
    tracks = np.maximum(tracks, 0.0)

    norm_cfg = getattr(config, "TRACK_NORMALIZATION", {}) or {}
    transform = str(norm_cfg.get("transform", "linear")).lower()
    if transform == "log1p":
        tracks_transformed = np.log1p(tracks).astype(np.float32, copy=False)
    elif transform == "linear":
        tracks_transformed = tracks
    else:
        raise ValueError(f"Unsupported TRACK_NORMALIZATION transform: {transform}")

    finite = tracks_transformed[np.isfinite(tracks_transformed)]
    positive = tracks_transformed[np.isfinite(tracks_transformed) & (tracks > 0)]
    if finite.size == 0 or positive.size == 0:
        return np.zeros_like(tracks, dtype=np.float32)

    method = str(norm_cfg.get("method", "max")).lower()
    if method == "positive_percentile_range":
        lower_pct = float(norm_cfg.get("lower_percentile", 60.0))
        upper_pct = float(norm_cfg.get("upper_percentile", 98.0))
        lower_pct = max(0.0, min(100.0, lower_pct))
        upper_pct = max(0.0, min(100.0, upper_pct))
        if upper_pct <= lower_pct:
            raise ValueError("TRACK_NORMALIZATION upper_percentile must be greater than lower_percentile")

        tracks_low = float(np.nanpercentile(positive, lower_pct))
        tracks_high = float(np.nanpercentile(positive, upper_pct))
        if tracks_high <= tracks_low:
            return np.zeros_like(tracks, dtype=np.float32)

        return np.clip(
            (tracks_transformed - tracks_low) / (tracks_high - tracks_low),
            0.0,
            1.0,
        ).astype(np.float32, copy=False)

    if method == "percentile":
        pct = float(norm_cfg.get("percentile", 95.0))
        pct = max(0.0, min(100.0, pct))
        tracks_scale = float(np.nanpercentile(finite, pct))
    else:
        tracks_scale = float(np.nanmax(finite))

    if tracks_scale <= 0.0:
        return np.zeros_like(tracks, dtype=np.float32)

    return np.clip(tracks_transformed / tracks_scale, 0.0, 1.0).astype(np.float32, copy=False)


def _apply_track_influence_like_request(
    base_cost_arr: np.ndarray,
    tracks_norm_arr: np.ndarray,
    forest_mask: np.ndarray,
    mode_params: dict[str, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    max_reduction_outside = float(mode_params["max_reduction_outside"])
    max_reduction_forest = float(mode_params["max_reduction_forest"])
    track_power = float(mode_params.get("track_power", 1.0))
    if track_power <= 0.0:
        raise ValueError("track_power must be > 0")

    forest_arr = forest_mask.astype(np.float32, copy=False)
    max_reduction_arr = (
        max_reduction_outside
        + (max_reduction_forest - max_reduction_outside) * forest_arr
    ).astype(np.float32, copy=False)
    tracks_shaped_arr = np.power(tracks_norm_arr, track_power).astype(np.float32, copy=False)
    cost_reduction_arr = (max_reduction_arr * tracks_shaped_arr).astype(np.float32, copy=False)
    cost_with_tracks = np.maximum(float(config.MIN_COST), base_cost_arr - cost_reduction_arr).astype(np.float32, copy=False)

    return max_reduction_arr, cost_reduction_arr, cost_with_tracks


def _save_track_debug_layers(
    *,
    inputs: Dict[str, Path],
    base_cost_arr: np.ndarray,
    nodata_mask: np.ndarray,
    profile: dict,
    output_dir: Path,
) -> None:
    tracks_arr, _ = read_raster(inputs["tracks"])
    forest_mask = read_mask(inputs["forest"])

    tracks_debug_arr = np.where(nodata_mask, np.nan, tracks_arr).astype(np.float32, copy=False)
    tracks_norm_arr = _normalize_tracks_like_request(tracks_arr)
    tracks_norm_arr = np.where(nodata_mask, np.nan, tracks_norm_arr).astype(np.float32, copy=False)

    debug_layer_save(tracks_debug_arr, "09a_tracks.tif", profile, output_dir)
    debug_layer_save(tracks_norm_arr, "09b_tracks_normalized.tif", profile, output_dir)

    debug_modes = [
        ("forest_only", "1"),
        ("balanced", "2"),
        ("strong", "3"),
    ]
    for mode_name, mode_number in debug_modes:
        mode_params = config.TRACK_INFLUENCE_PARAMS[mode_name]
        max_reduction_arr, _, cost_with_tracks = _apply_track_influence_like_request(
            base_cost_arr=base_cost_arr,
            tracks_norm_arr=tracks_norm_arr,
            forest_mask=forest_mask,
            mode_params=mode_params,
        )

        delta_arr = (base_cost_arr - cost_with_tracks).astype(np.float32, copy=False)

        max_reduction_arr = np.where(nodata_mask, np.nan, max_reduction_arr).astype(np.float32, copy=False)
        delta_arr = np.where(nodata_mask, np.nan, delta_arr).astype(np.float32, copy=False)
        cost_with_tracks = np.where(nodata_mask, np.nan, cost_with_tracks).astype(np.float32, copy=False)

        debug_layer_save(delta_arr, f"10b{mode_number}_tracks_delta_{mode_name}.tif", profile, output_dir)
        debug_layer_save(cost_with_tracks, f"10c{mode_number}_cost_with_tracks_{mode_name}.tif", profile, output_dir)



def create_cost_surface(paths: AreaPaths, inputs: Dict[str, Path], debug_mode: bool) -> Path:
    """
    Creates and saves a cost surface from input rasters and masks.  
    In debug mode, it saves intermediate layers for tuning.
    """
    output_path = paths.cost_surface_output
    runtime_output_path = paths.cost_surface
    paths.cost_surface_dir.mkdir(parents=True, exist_ok=True)
    paths.debug_cost_layer_dir.mkdir(parents=True, exist_ok=True)

    # Reference profile
    with rasterio.open(inputs["slope"]) as ref:
        ref_profile = ref.profile

    # Load input rasters
    slope_arr, _ = read_raster(inputs["slope"])
    windshelter_arr, _ = read_raster(inputs["curvature"])
    windshelter_arr = np.nan_to_num(windshelter_arr, nan=0.0)
    pra_runout_combined_arr, _ = read_raster(inputs["pra_runout_combined"])

    # Verify shapes
    for arr in [windshelter_arr, pra_runout_combined_arr]:
        if arr.shape != slope_arr.shape:
            raise ValueError("Input rasters must have the same shape")

    # NODATA-policies
    pra_runout_combined_arr = np.where(
    np.isnan(pra_runout_combined_arr), 1, pra_runout_combined_arr).astype(np.float32, copy=False) # treat NoData (neither release nor runout) as low cost (1)
    

    # Terrain transforms
    slope_cost_arr = slope_cost(config.SLOPE_TRANSFORM, slope_arr, **config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"])
    windshelter_cost_arr = windshelter_cost(windshelter_arr, **config.TRANSFORM_PARAMS["windshelter"])
    pra_runout_combined_cost_arr = pra_runout_combined_arr  # direct use, already in configured cost range

    if debug_mode:
        debug_layer_save(slope_cost_arr, "01_slope_cost.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(windshelter_cost_arr, "02_windshelter_cost.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(pra_runout_combined_cost_arr, "03_pra_runout_combined_cost.tif", ref_profile, paths.debug_cost_layer_dir)

    # Combine layers: weighted sum
    layers = {"slope": slope_cost_arr, "windshelter": windshelter_cost_arr, "pra_runout_combined": pra_runout_combined_cost_arr}
    surface_sum = weighted_sum(layers, config.WEIGHTS_TERRAIN)

    if debug_mode:
        debug_layer_save(surface_sum, "04_weighted_sum.tif", ref_profile, paths.debug_cost_layer_dir)





    # --- Barriers and reductions ---

    # Validity weights (kind of safe mask): where reductions are allowed
    slope_w = smooth_gate_below(slope_arr, threshold=config.SAFE_MASK_SOFT_PARAMS["slope_threshold"], width=config.SAFE_MASK_SOFT_PARAMS["slope_width"])
    pra_runout_w = smooth_gate_below(pra_runout_combined_cost_arr, threshold=config.SAFE_MASK_SOFT_PARAMS["pra_runout_combined_threshold"], width=config.SAFE_MASK_SOFT_PARAMS["pra_runout_combined_width"])
    validity_w = slope_w * pra_runout_w
 
    # Barrier / reduction layers
    ocean_mask = read_mask(inputs["ocean"])
    roads_mask = read_mask(inputs["road"])
    tractorroads_trails_forest_mask = read_mask(inputs["tractorroad_trail_forest"])
    bridges_mask = read_mask(inputs["bridge"])

    ocean_barrier = barrier_layer_from_mask(ocean_mask, barrier_value=config.BARRIER_COST, min_cost=config.MIN_COST)
    steep_barrier = None
    steep_barrier_params = config.STEEP_SLOPE_BARRIER_PARAMS
    if bool(steep_barrier_params["enabled"]):
        steep_barrier = steep_slope_barrier(
            slope_arr=slope_arr,
            start_deg=float(steep_barrier_params["start_deg"]),
            full_deg=float(steep_barrier_params["full_deg"]),
            start_value=float(steep_barrier_params["start_value"]),
            barrier_value=float(steep_barrier_params["barrier_value"]),
            power=float(steep_barrier_params["power"]),
        )

    roads_reduction = reduction_layer_from_mask_soft(roads_mask, validity_w, low_value=config.ROAD_TRAIL_COST, elsewhere_value=config.BASE_MAX_COST)
    tractorroads_trails_forest_reduction = reduction_layer_from_mask_soft(tractorroads_trails_forest_mask, validity_w, low_value=config.ROAD_TRAIL_COST, elsewhere_value=config.BASE_MAX_COST)
    bridge_validity_w = np.where(bridges_mask.astype(bool), 1.0, validity_w).astype(np.float32, copy=False)
    bridges_reduction = reduction_layer_from_mask_soft(bridges_mask, bridge_validity_w, low_value=config.MIN_COST, elsewhere_value=config.BASE_MAX_COST)

    # MAX for barriers, MIN for reductions
    with_barriers = surface_sum
    with_barriers = max_combine(with_barriers, ocean_barrier)
    if steep_barrier is not None:
        with_barriers = max_combine(with_barriers, steep_barrier)
    
    if debug_mode:
        debug_layer_save(ocean_barrier, "05a_ocean_barriers.tif", ref_profile, paths.debug_cost_layer_dir)
        if steep_barrier is not None:
            debug_layer_save(steep_barrier, "05b_steep_slope_barrier.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(with_barriers, "05c_with_barriers.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(validity_w, "06_safe_mask_for_reductions.tif", ref_profile, paths.debug_cost_layer_dir)

    reduction_layers = [arr for arr in [roads_reduction, tractorroads_trails_forest_reduction, bridges_reduction] if arr is not None]
    with_reductions = with_barriers
    with_reductions = min_combine(with_barriers, *reduction_layers)

    if debug_mode:
        debug_layer_save(roads_reduction, "07a_road_reduction.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(tractorroads_trails_forest_reduction, "07b_tractorroads_trails_reduction.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(bridges_reduction, "07c_bridge_reduction.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(with_reductions, "07d_with_reductions.tif", ref_profile, paths.debug_cost_layer_dir)

    final_surface = with_reductions
    if steep_barrier is not None:
        final_surface = max_combine(final_surface, steep_barrier)

    if debug_mode:
        debug_layer_save(final_surface, "08_final_cost_surface.tif", ref_profile, paths.debug_cost_layer_dir)

    nodata_mask = np.isnan(slope_arr)

    if debug_mode:
        _save_track_debug_layers(
            inputs=inputs,
            base_cost_arr=final_surface,
            nodata_mask=nodata_mask,
            profile=ref_profile,
            output_dir=paths.debug_cost_layer_dir,
        )

    # Propagate nodata
    surface_u16 = clip_round(final_surface, min_cost=1.0, max_cost=float(config.MAX_COST))
    surface_u16[nodata_mask] = config.NODATA_VALUE


    # Ensure output directories exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write final output raster
    prof = ref_profile.copy()
    prof.update(dtype=rasterio.uint16, count=1, compress='lzw', nodata=config.NODATA_VALUE)
    with rasterio.open(output_path, 'w', **prof) as dst:
        dst.write(surface_u16, 1)

    print(f"Cost surface written to {output_path}")

    shutil.copy2(output_path, runtime_output_path)
    print(f"Runtime cost surface synced to {runtime_output_path}")

    return output_path
