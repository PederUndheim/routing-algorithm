import shutil

import rasterio
import numpy as np

from typing import Dict
from pathlib import Path
from backend import config  
from backend.file_handler.area_paths import AreaPaths
from backend.routing_algorithm.cost_surface.raster_helpers import read_raster, read_mask, debug_layer_save                        
from backend.routing_algorithm.cost_surface.transforms import (                       
    slope_cost,
    curvature_cost,
    barrier_layer_from_mask,
    reduction_layer_from_mask_soft,
    smooth_gate_below
)
from backend.routing_algorithm.cost_surface.combine import weighted_sum, min_combine, max_combine, clip_round
from backend.routing_algorithm.cost_surface.refinements import release_area_buffer_penalty, steep_area_penalty, extreme_steep_barrier

np.seterr(all='ignore')  # ignore warnings for NaNs


def _normalize_tracks_like_request(tracks_arr: np.ndarray) -> np.ndarray:
    """Normalize tracks to [0, 1] with log1p compression.
    
    Used for debug layers to mirror request-time track influence shaping.
    This does not overwrite input tracks.tif; routing applies normalization
    dynamically on the request mosaic.
    """
    tracks = tracks_arr.astype(np.float32, copy=False)
    tracks = np.where(np.isnan(tracks), 0.0, tracks)
    tracks = np.maximum(tracks, 0.0)
    
    # Log transform to compress skew
    tracks = np.log1p(tracks)
    
    finite = tracks[np.isfinite(tracks)]
    if finite.size == 0:
        return np.zeros_like(tracks, dtype=np.float32)

    norm_cfg = getattr(config, "TRACK_NORMALIZATION", {}) or {}
    method = str(norm_cfg.get("method", "max")).lower()

    if method == "percentile":
        pct = float(norm_cfg.get("percentile", 95.0))
        pct = max(0.0, min(100.0, pct))
        tracks_scale = float(np.nanpercentile(finite, pct))
    else:
        tracks_scale = float(np.nanmax(finite))

    if tracks_scale <= 0.0:
        return np.zeros_like(tracks, dtype=np.float32)

    return np.clip(tracks / tracks_scale, 0.0, 1.0).astype(np.float32, copy=False)


def _apply_track_influence_like_request(
    base_cost_arr: np.ndarray,
    tracks_norm_arr: np.ndarray,
    forest_mask: np.ndarray,
    mode_params: dict[str, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    w_outside = float(mode_params["w_outside"])
    w_forest = float(mode_params["w_forest"])
    track_power = float(mode_params.get("track_power", 1.0))
    if track_power <= 0.0:
        raise ValueError("track_power must be > 0")

    forest_arr = forest_mask.astype(np.float32, copy=False)
    weight_arr = (w_outside + (w_forest - w_outside) * forest_arr).astype(np.float32, copy=False)
    tracks_shaped_arr = np.power(tracks_norm_arr, track_power).astype(np.float32, copy=False)
    modifier_arr = (1.0 - weight_arr * tracks_shaped_arr).astype(np.float32, copy=False)
    cost_with_tracks = np.maximum(float(config.MIN_COST), base_cost_arr * modifier_arr).astype(np.float32, copy=False)

    return weight_arr, modifier_arr, cost_with_tracks


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

    tracks_norm_arr = _normalize_tracks_like_request(tracks_arr)
    tracks_norm_arr = np.where(nodata_mask, np.nan, tracks_norm_arr).astype(np.float32, copy=False)
    forest_debug_arr = np.where(nodata_mask, np.nan, forest_mask.astype(np.float32)).astype(np.float32, copy=False)

    debug_layer_save(tracks_norm_arr, "08a_tracks_normalized.tif", profile, output_dir)
    debug_layer_save(forest_debug_arr, "08b_tracks_forest_mask.tif", profile, output_dir)

    for mode_name, mode_params in config.TRACK_INFLUENCE_PARAMS.items():
        weight_arr, modifier_arr, cost_with_tracks = _apply_track_influence_like_request(
            base_cost_arr=base_cost_arr,
            tracks_norm_arr=tracks_norm_arr,
            forest_mask=forest_mask,
            mode_params=mode_params,
        )

        delta_arr = (base_cost_arr - cost_with_tracks).astype(np.float32, copy=False)

        weight_arr = np.where(nodata_mask, np.nan, weight_arr).astype(np.float32, copy=False)
        modifier_arr = np.where(nodata_mask, np.nan, modifier_arr).astype(np.float32, copy=False)
        delta_arr = np.where(nodata_mask, np.nan, delta_arr).astype(np.float32, copy=False)
        cost_with_tracks = np.where(nodata_mask, np.nan, cost_with_tracks).astype(np.float32, copy=False)

        debug_layer_save(weight_arr, f"09a_tracks_weight_{mode_name}.tif", profile, output_dir)
        debug_layer_save(modifier_arr, f"09b_tracks_modifier_{mode_name}.tif", profile, output_dir)
        debug_layer_save(delta_arr, f"09c_tracks_delta_{mode_name}.tif", profile, output_dir)
        debug_layer_save(cost_with_tracks, f"09d_cost_with_tracks_{mode_name}.tif", profile, output_dir)



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
    curvature_arr, _ = read_raster(inputs["curvature"])
    curvature_arr = np.nan_to_num(curvature_arr, nan=0.0)
    pra_runout_combined_arr, _ = read_raster(inputs["pra_runout_combined"])

    # Verify shapes
    for arr in [curvature_arr, pra_runout_combined_arr]:
        if arr.shape != slope_arr.shape:
            raise ValueError("Input rasters must have the same shape")

    # NODATA-policies
    pra_runout_combined_arr = np.where(
    np.isnan(pra_runout_combined_arr), 1, pra_runout_combined_arr).astype(np.float32, copy=False) # treat NoData (neither release nor runout) as low cost (1)

    # Terrain transforms
    slope_cost_arr = slope_cost(config.SLOPE_TRANSFORM, slope_arr, **config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"])
    curvature_cost_arr = curvature_cost(curvature_arr, **config.TRANSFORM_PARAMS["curvature"])
    pra_runout_combined_cost_arr = pra_runout_combined_arr  # direct use, already in [1,99]

    if debug_mode:
        debug_layer_save(slope_cost_arr, "01_slope_cost.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(curvature_cost_arr, "02_curvature_cost.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(pra_runout_combined_cost_arr, "03_pra_runout_combined_cost.tif", ref_profile, paths.debug_cost_layer_dir)

    # Combine layers: weighted sum
    layers = {"slope": slope_cost_arr, "curvature": curvature_cost_arr, "pra_runout_combined": pra_runout_combined_cost_arr}
    surface_sum = weighted_sum(layers, config.WEIGHTS_TERRAIN)

    if debug_mode:
        debug_layer_save(surface_sum, "04_weighted_sum.tif", ref_profile, paths.debug_cost_layer_dir)




    # -- Refinements and softer transitions--

    # Release area buffer penalty
    pra_raw_arr, _ = read_raster(inputs["pra_raw"])
    release_mask = pra_raw_arr >= 0.15  # release areas defined as PRA raw >= 0.15
    px = abs(ref_profile['transform'][0])  # pixel size in meters

    release_buffer_penalty = release_area_buffer_penalty(
        release_area_mask=release_mask,
        pixel_size_m=px,
        max_dist=config.RELEASE_BUFFER_PARAMS["max_dist"],       
        max_cost=config.RELEASE_BUFFER_PARAMS["max_cost"],
        exp_scale=config.RELEASE_BUFFER_PARAMS["exp_scale"],
        mode=config.RELEASE_BUFFER_PARAMS["mode"],
    )
    if debug_mode:
        debug_layer_save(release_buffer_penalty, "05a_release_area_buffer_penalty.tif", ref_profile, paths.debug_cost_layer_dir)

    surface_sum = surface_sum + release_buffer_penalty


    # Steep area penalty
    steep_penalty = steep_area_penalty(
        slope_arr=slope_arr,
        start_deg=config.STEEP_AREA_PARAMS["start_deg"],
        full_deg=config.STEEP_AREA_PARAMS["full_deg"],
        max_penalty=config.STEEP_AREA_PARAMS["max_penalty"],
    )
    if debug_mode:
        debug_layer_save(steep_penalty, "05c_steep_area_penalty.tif", ref_profile, paths.debug_cost_layer_dir)

    surface_sum = surface_sum + steep_penalty


    # Extreme steep barrier: hard step above threshold, breaks the 99 ceiling
    extreme_barrier = extreme_steep_barrier(
        slope_arr=slope_arr,
        threshold_deg=config.EXTREME_STEEP_PARAMS["threshold_deg"],
        barrier_value=config.EXTREME_STEEP_PARAMS["barrier_value"],
    )
    if debug_mode:
        debug_layer_save(extreme_barrier, "05d_extreme_steep_barrier.tif", ref_profile, paths.debug_cost_layer_dir)

    surface_sum = max_combine(surface_sum, extreme_barrier)


    # -- Barriers and reductions --

    # Validity weights (kind of safe mask): where reductions are allowed
    slope_w = smooth_gate_below(slope_arr, threshold=config.SAFE_MASK_SOFT_PARAMS["slope_threshold"], width=config.SAFE_MASK_SOFT_PARAMS["slope_width"])
    pra_runout_w = smooth_gate_below(pra_runout_combined_cost_arr, threshold=config.SAFE_MASK_SOFT_PARAMS["pra_runout_combined_threshold"], width=config.SAFE_MASK_SOFT_PARAMS["pra_runout_combined_width"])
    validity_w = slope_w * pra_runout_w
 
    # Barrier / reduction layers
    ocean_mask = read_mask(inputs["ocean"])
    roads_mask = read_mask(inputs["road"])
    tractorroads_trails_forest_mask = read_mask(inputs["tractorroad_trail_forest"])
    bridges_mask = read_mask(inputs["bridge"])

    ocean_barrier = barrier_layer_from_mask(ocean_mask, barrier_value=config.OCEAN_BARRIER_VALUE, min_cost=config.MIN_COST)
    roads_reduction = reduction_layer_from_mask_soft(roads_mask, validity_w, low_value=config.ROADS_REDUCTION_VALUE, elsewhere_value=config.MAX_COST)
    tractorroads_trails_forest_reduction = reduction_layer_from_mask_soft(tractorroads_trails_forest_mask, validity_w, low_value=config.TRACTOROADS_TRAILS_REDUCTION_VALUE, elsewhere_value=config.MAX_COST)
    bridge_validity_w = np.where(bridges_mask.astype(bool), 1.0, validity_w).astype(np.float32, copy=False)
    bridges_reduction = reduction_layer_from_mask_soft(bridges_mask, bridge_validity_w, low_value=config.BRIDGES_REDUCTION_VALUE, elsewhere_value=config.MAX_COST)

    # MAX for barriers, MIN for reductions
    with_barriers = surface_sum
    with_barriers = max_combine(with_barriers, ocean_barrier)
    
    if debug_mode:
        debug_layer_save(with_barriers, "06_with_barriers.tif", ref_profile, paths.debug_cost_layer_dir)

    reduction_layers = [arr for arr in [roads_reduction, tractorroads_trails_forest_reduction, bridges_reduction] if arr is not None]
    with_reductions = with_barriers
    with_reductions = min_combine(with_barriers, *reduction_layers)

    if debug_mode:
        debug_layer_save(with_reductions, "07_with_reductions.tif", ref_profile, paths.debug_cost_layer_dir)


    nodata_mask = np.isnan(slope_arr)

    if debug_mode:
        _save_track_debug_layers(
            inputs=inputs,
            base_cost_arr=with_reductions,
            nodata_mask=nodata_mask,
            profile=ref_profile,
            output_dir=paths.debug_cost_layer_dir,
        )

    # Propagate nodata
    surface_u16 = clip_round(with_reductions, min_cost=1.0, max_cost=float(config.MAX_COST))
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