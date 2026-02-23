# Constants
RIVER_BARRIER_VALUE = 99.0
OCEAN_BARRIER_VALUE = 99.0

ROADS_REDUCTION_VALUE = 1.0 
TRACTOROADS_TRAILS_REDUCTION_VALUE = 2.0
BRIDGES_REDUCTION_VALUE = 1.0     

MIN_COST = 1
MAX_COST = 99

NODATA_VALUE = 255

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

# Steep area penalty parameters
STEEP_AREA_PARAMS = {
    "start_deg": 50.0,      # Start penalty at this slope
    "full_deg": 65.0,       # Full penalty at this slope
    "max_penalty": 35.0,    # Max additive penalty
}

# Cliff buffer penalty parameters
# CLIFF_BUFFER_PARAMS = {
#     "steep_threshold": 60.0,    
#     "max_dist": 20.0,          
#     "penalty_cost": 10.0,      
# }

# Safe mask for where cost reductions are allowed
SAFE_MASK_SOFT_PARAMS = {
    "slope_threshold": 30.0,      
    "slope_width": 6.0,    
    "pra_runout_combined_threshold": 5.0,
    "pra_runout_combined_width": 1.5,
}

# Real tracks reduction parameters
REAL_TRACKS_REDUCTION_PARAMS = {
    "w_general_default": 0.2,      # default reduction fraction
    "w_general_max": 0.4,           # max reduction fraction
    "w_forest": 0.5,                # reduction fraction for mask where extra important, e.g., in forest
    "gamma_default": 1.0,           # default gamma for constrast, >1 popular tracks emphasized more, <1 less used tracks matter more
    "p_high_quantile": 0.995,       # percentile for high usage
    "use_validity_w": False,          
} 


# GRASS routing parameters
ROUTING_SETTINGS = {
    "lambda_weight": 0.55,
    "smooth_threshold": 7.5,
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