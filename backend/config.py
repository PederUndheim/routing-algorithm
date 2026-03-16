# Constants
from typing import Union


RIVER_BARRIER_VALUE = 200.0
OCEAN_BARRIER_VALUE = 5000.0

ROADS_REDUCTION_VALUE = 1.0 
TRACTOROADS_TRAILS_REDUCTION_VALUE = 2.0
BRIDGES_REDUCTION_VALUE = 1.0     

MIN_COST = 1
MAX_COST = 5000

NODATA_VALUE = 65535

# PRA runout combined parameters
PRA_RUNOUT_COMBINED_PARAMS = {
    "runout_min": 1.0,
    "runout_max": 15,
    "release_min": 15,
    "release_max": 99.0,    
}

# --- Transform parameters  ---
SLOPE_TRANSFORM = 'hyperbolic'  # options: 'logistic', 'richards', 'hyperbolic'

TRANSFORM_PARAMS = {   
    'curvature': {'x0': 0.0, 'k': 5.5, 'min_cost': 3.0, 'max_cost': 97.0},
    'slope_logistic': {'x0': 32, 'k': 0.6, 'min_cost': 1.0, 'max_cost': 99.0},
    'slope_richards': {'x0': 28, 'k': -0.7, 'nu': 5, 'min_cost': 1.0, 'max_cost': 99.0},
    'slope_hyperbolic': {'x0': 34.0, 'k': 9.0, 'min_cost': 1.0, 'max_cost': 99.0},
}

# --- Weights for SUM-based terrain-cost-surface ---
WEIGHTS_TERRAIN = {
    "slope": 5.0,
    "curvature": 1.0,
    "pra_runout_combined": 4.0
}

# Release area buffer penalty parameters
RELEASE_BUFFER_PARAMS = {
    "max_dist": 150.0,  
    "max_cost": 5.0,      
    "exp_scale": 25.0,    
    "mode": "exp",        
}

# Steep area penalty parameters (smooth ramp into the hard barrier below)
STEEP_AREA_PARAMS = {
    "start_deg": 45.0,      # Start penalty at this slope
    "full_deg": 50.0,       # Full penalty at this slope
    "max_penalty": 35.0,    # Max additive penalty
}

# Extreme steep barrier: hard step above this threshold, applied via max_combine.
# Breaks the normal 1-99 ceiling so thin cliff bands (few pixels) cannot be
# cheaply traversed. Threshold should sit at or just above STEEP_AREA_PARAMS full_deg.
EXTREME_STEEP_PARAMS = {
    "threshold_deg": 50.0,    # At or above this slope → barrier cost
    "barrier_value": 1500.0,
}

# Safe mask for where cost reductions are allowed
SAFE_MASK_SOFT_PARAMS = {
    "slope_threshold": 30.0,      
    "slope_width": 6.0,    
    "pra_runout_combined_threshold": 5.0,
    "pra_runout_combined_width": 1.5,
}

# Track influence modes: named parameters for readability.
TRACK_INFLUENCE_PARAMS: dict[str, dict[str, float]] = {
    "off": {"w_outside": 0.0, "w_forest": 0.0, "track_power": 1.0},
    "forest_only": {"w_outside": 0.0, "w_forest": 0.35, "track_power": 1.4},
    "balanced": {"w_outside": 0.1, "w_forest": 0.3, "track_power": 1.6},
    "strong": {"w_outside": 0.2, "w_forest": 0.45, "track_power": 1.4},
}

# Request-time tracks normalization settings.
# method:
# - "max": scale by max(log1p(tracks)) over request mosaic
# - "percentile": scale by percentile(log1p(tracks)) to reduce hotspot dominance
TRACK_NORMALIZATION = {
    "method": "percentile",
    "percentile": 95.0,
}

# Corridor rendering modes: controls corridor width and contrast
CORRIDOR_MODE_PARAMS: dict[str, dict[str, float]] = {
    "conservative": {"slack": 0.1, "gamma": 6.0},
    "balanced": {"slack": 0.2, "gamma": 4.0},
    "explorative": {"slack": 0.3, "gamma": 1.5},
}


# GRASS routing parameters
ROUTING_SETTINGS = {
    "lambda_weight": 0.55,
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

# hyperbolic: 
# slope: 5, curvature: 1, pra_runout_combined: 4, lambda: 0.55
# lambda: 0.5 --> lang bue Kyrkjetaket, høyre Kjøvskarstind
# lambda: 0.6 --> kortere bue Kyrkjetaket, venstre Kjøvskarstind

# logistic:
# slope: 5, curvature: 1, pra_runout_combined: 4, lambda: 0.5

# richards:
# bad