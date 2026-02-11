import rasterio
import numpy as np

from typing import Dict
from pathlib import Path
from backend import config  
from backend.file_handler.area_paths import AreaPaths
from backend.routing_algorithm.io.rasters import read_raster, read_mask, debug_layer_save                        
from backend.routing_algorithm.cost_surface.transforms import (                       
    slope_cost,
    curvature_cost,
    barrier_layer_from_mask,
    reduction_layer_from_mask_soft,
    smooth_gate_below
)
from backend.routing_algorithm.cost_surface.combine import weighted_sum, min_combine, max_combine, clip_round
from backend.routing_algorithm.cost_surface.refinements import release_area_buffer_penalty, steep_area_penalty, real_tracks_modifier

np.seterr(all='ignore')  # ignore warnings for NaNs



def create_cost_surface(paths: AreaPaths, inputs: Dict[str, Path], debug_mode: bool = True) -> Path:
    """
    Creates and saves a cost surface from input rasters and masks.  
    In debug mode, it saves intermediate layers for tuning.
    """
    output_path = paths.cost_surface
    paths.cost_surface_dir.mkdir(parents=True, exist_ok=True)
    paths.debug_cost_layer_dir.mkdir(parents=True, exist_ok=True)

    # Reference profile
    with rasterio.open(inputs["slope"]) as ref:
        ref_profile = ref.profile

    # Load input rasters
    slope_arr, _ = read_raster(inputs["slope"])
    curvature_arr, _ = read_raster(inputs["curvature"])
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


    # Cliff buffer penalty
    # cliff_mask = slope_arr >= config.CLIFF_BUFFER_PARAMS["steep_threshold"]

    # cliff_penalty = cliff_buffer_penalty(
    #     cliff_mask=cliff_mask,
    #     pixel_size_m=px,
    #     max_dist=config.CLIFF_BUFFER_PARAMS["max_dist"],
    #     penalty_cost=config.CLIFF_BUFFER_PARAMS["penalty_cost"],
    # )
    # if debug_mode:
    #     debug_layer_save(cliff_penalty, "05b_cliff_buffer_penalty.tif", ref_profile)
    
    # surface_sum = surface_sum + cliff_penalty



    # -- Barriers and reductions --

    # Validity weights (kind of safe mask): where reductions are allowed
    slope_w = smooth_gate_below(slope_arr, threshold=config.SAFE_MASK_SOFT_PARAMS["slope_threshold"], width=config.SAFE_MASK_SOFT_PARAMS["slope_width"])
    pra_runout_w = smooth_gate_below(pra_runout_combined_cost_arr, threshold=config.SAFE_MASK_SOFT_PARAMS["pra_runout_combined_threshold"], width=config.SAFE_MASK_SOFT_PARAMS["pra_runout_combined_width"])
    validity_w = slope_w * pra_runout_w
 
    # Barrier / reduction layers
    rivers_mask = read_mask(inputs["river"])
    roads_mask = read_mask(inputs["road"])
    tractorroads_trails_forest_mask = read_mask(inputs["tractorroad_trail_forest"])
    bridges_mask = read_mask(inputs["bridge"])

    rivers_barrier = barrier_layer_from_mask(rivers_mask, barrier_value=config.RIVER_BARRIER_VALUE, min_cost=config.MIN_COST)
    roads_reduction = reduction_layer_from_mask_soft(roads_mask, validity_w, low_value=config.ROADS_REDUCTION_VALUE, elsewhere_value=config.MAX_COST)
    tractorroads_trails_forest_reduction = reduction_layer_from_mask_soft(tractorroads_trails_forest_mask, validity_w, low_value=config.TRACTOROADS_TRAILS_REDUCTION_VALUE, elsewhere_value=config.MAX_COST)
    bridges_reduction = reduction_layer_from_mask_soft(bridges_mask, validity_w, low_value=config.BRIDGES_REDUCTION_VALUE, elsewhere_value=config.MAX_COST)

    # MAX for barriers, MIN for reductions
    with_barriers = surface_sum
    with_barriers = max_combine(with_barriers, rivers_barrier)
    
    if debug_mode:
        debug_layer_save(with_barriers, "06_with_barriers.tif", ref_profile, paths.debug_cost_layer_dir)

    reduction_layers = [arr for arr in [roads_reduction, tractorroads_trails_forest_reduction, bridges_reduction] if arr is not None]
    with_reductions = with_barriers
    with_reductions = min_combine(with_barriers, *reduction_layers)

    if debug_mode:
        debug_layer_save(with_reductions, "07_with_reductions.tif", ref_profile, paths.debug_cost_layer_dir)



    # -- Final modification: Real tracks reduction --

    # Use validity_w optionally --> must eventually change the validity_w to be less strict..!!
    validity_w_tracks = validity_w if config.REAL_TRACKS_REDUCTION_PARAMS["use_validity_w"] else None

    exclude_mask = None
    only_mask = None
 
    tracks_arr, _ = read_raster(inputs["tracks"])
    if tracks_arr.shape != with_reductions.shape:
        raise ValueError("Tracks raster shape does not match cost surface shape")
    
    # Forest mask
    forest_mask = None
    forest_arr, _ = read_raster(inputs["forest"])
    forest_mask = (forest_arr > 0).astype(np.float32)
    if forest_mask.shape != with_reductions.shape:
        raise ValueError("Forest raster shape does not match cost surface shape")


    # Build spatial w map: strong in forest, user controller elsewhere
    w_general = config.REAL_TRACKS_REDUCTION_PARAMS["w_general_default"]
    w_forest = config.REAL_TRACKS_REDUCTION_PARAMS["w_forest"]
    w_map = w_general + (w_forest - w_general) * forest_mask
    
    modifier = real_tracks_modifier(
        tracks_arr=tracks_arr,
        w=w_map,
        p_high_quantile=config.REAL_TRACKS_REDUCTION_PARAMS["p_high_quantile"],
        gamma=config.REAL_TRACKS_REDUCTION_PARAMS["gamma_default"],
        validity_w=validity_w_tracks,
        exclude_mask=exclude_mask,
        only_mask=only_mask,
        effect_weight=None      # Possibly make a more advanced effect weight later??
    )
    with_reductions = with_reductions * modifier
    if debug_mode:
        debug_layer_save(forest_mask, "08a_forest_mask.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(w_map, "08b_tracks_w_map.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(modifier, "08c_real_tracks_modifier.tif", ref_profile, paths.debug_cost_layer_dir)
        debug_layer_save(with_reductions, "08d_with_real_tracks_mod.tif", ref_profile, paths.debug_cost_layer_dir)



    # Propagate nodata
    nodata_mask = np.isnan(slope_arr) | np.isnan(curvature_arr) | np.isnan(pra_runout_combined_arr)
    surface_u8 = clip_round(with_reductions, min_cost=1.0, max_cost=99.0)
    surface_u8[nodata_mask] = config.NODATA_VALUE

    # Write final output raster
    prof = ref_profile.copy()
    prof.update(dtype=rasterio.uint8, count=1, compress='lzw', nodata=config.NODATA_VALUE)
    with rasterio.open(output_path, 'w', **prof) as dst:
        dst.write(surface_u8, 1) 

    print(f"Cost surface written to {output_path}")

    return output_path