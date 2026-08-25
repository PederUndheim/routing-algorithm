# Constants
from typing import Union

MIN_COST = 1
ROAD_TRAIL_COST = 2
BASE_MAX_COST = 100
MAX_COST = 5000
BARRIER_COST = MAX_COST

NODATA_VALUE = 65535

# PRA runout combined parameters
PRA_RUNOUT_COMBINED_PARAMS = {
    "runout_min": 1.0,
    "runout_max": 7.2,
    "release_min": 7.2,
    "release_max": float(BASE_MAX_COST),
}

# --- Transform parameters  ---
SLOPE_TRANSFORM = 'threshold_jump'  # options: 'logistic', 'richards', 'hyperbolic', 'threshold_jump'

TRANSFORM_PARAMS = {   
    'windshelter': {'x0': 0.0, 'k': 5.5, 'min_cost': 5.0, 'max_cost': 30.0},
    'slope_logistic': {'x0': 32, 'k': 0.6, 'min_cost': 1.0, 'max_cost': float(BASE_MAX_COST)},
    'slope_richards': {'x0': 28, 'k': -0.7, 'nu': 5, 'min_cost': 1.0, 'max_cost': float(BASE_MAX_COST)},
    'slope_hyperbolic': {'x0': 34.0, 'k': 9.0, 'min_cost': 1.0, 'max_cost': float(BASE_MAX_COST)},
    "slope_threshold_jump": {
        "threshold": 30.0,
        "low_max": 0.05,
        "low_power": 3.0,
        "jump_start": 29.0,
        "jump_end": 30.0,
        "jump_to": 0.35,
        "tail_end": 45.0,
        "min_cost": 2.0,
        "max_cost": float(BASE_MAX_COST),
    },
}

# --- Weights for SUM-based terrain-cost-surface ---
WEIGHTS_TERRAIN = {
    "slope": 0.53,
    "windshelter": 0.12,
    "pra_runout_combined": 0.35,
}

# Very steep terrain barrier, applied with max-combine after road/trail reductions.
STEEP_SLOPE_BARRIER_PARAMS = {
    "enabled": True,
    "start_deg": 45.0,
    "full_deg": 50.0,
    "start_value": 100.0,
    "barrier_value": 1500.0,
    "power": 3.0,
}

# Safe mask for where cost reductions are allowed
SAFE_MASK_SOFT_PARAMS = {
    "slope_threshold": 30.0,      
    "slope_width": 6.0,    
    "pra_runout_combined_threshold": 5.0,
    "pra_runout_combined_width": 1.5,
}

# Track influence modes: named parameters for readability.
# Tracks reduce cost by up to a fixed number of cost units, not by a percentage.
# The final reduction is max_reduction * normalized_tracks**track_power.
TRACK_INFLUENCE_PARAMS: dict[str, dict[str, float]] = {
    "off": {"max_reduction_outside": 0.0, "max_reduction_forest": 0.0, "track_power": 1.0},
    "forest_only": {"max_reduction_outside": 0.0, "max_reduction_forest": 4.0, "track_power": 2.0},
    "balanced": {"max_reduction_outside": 2.0, "max_reduction_forest": 4.0, "track_power": 2.0},
    "strong": {"max_reduction_outside": 4.0, "max_reduction_forest": 6.0, "track_power": 2.0},
}

# Request-time tracks normalization settings.
# "positive_percentile_range" ignores zero-track pixels when finding the scale:
# - positive pixels below lower_percentile get no cost reduction
# - positive pixels near/above upper_percentile get full track influence
# This prevents sparse/low-count track pixels from reducing cost.
TRACK_NORMALIZATION = {
    "method": "positive_percentile_range",
    "lower_percentile": 60.0,
    "upper_percentile": 95.0,
    "transform": "linear",
}

# Corridor rendering modes: controls corridor width and contrast
CORRIDOR_MODE_PARAMS: dict[str, dict[str, float]] = {
    "conservative": {"slack": 0.1, "gamma": 6.0},
    "balanced": {"slack": 0.2, "gamma": 4.0},
    "explorative": {"slack": 0.3, "gamma": 1.5},
}


# GRASS routing parameters
ROUTING_SETTINGS = {
    "lambda_weight": 0.6,
    "smooth_threshold": 7.5,
    "region_buffer_m": 5000.0,
    "grass_memory_mb": 2500,
}

# Debug script parameters for backend.scripts.run_routing
RUN_DEBUG_ROUTING_PARAMS: dict[str, Union[str, bool]] = {
    "track_influence_mode": "balanced",
    "corridor_mode": "balanced",
    "avoid_lake": False,
    "avoid_glacier": False,
    "avoid_river": False,
}

MULTIROUTING = False

MULTIROUTING_PARAMS = {
    "no_routes": 50,        
    "eps_stop": 0.3,        # stop if route cost > (1+eps_stop)*base_C_opt
    "penalty_alpha": 0.5,  # strength of penalty added each iteration    
    "penalty_cap": 50.0,    # max total penalty per pixel
    "buffer_m": 5.0,       # width of penalty buffer in meters
}
