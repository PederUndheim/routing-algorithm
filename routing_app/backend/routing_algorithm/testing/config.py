from __future__ import annotations

# Run pipeline: python -m backend.routing_algorithm.testing.run_testing_pipeline
# Run visualization: python -m backend.routing_algorithm.testing.visualize_slope_pra 
# python -m backend.scripts.visualize_cost_surface_transforms

# Experiment identity / default scope
DEFAULT_EXPERIMENT = "cost_surface_v2"

DEFAULT_TEST_AREAS = [
    "isfjorden_01",
    "jotunheimen_01",
    "kattfjordeidet_01",
]

DEFAULT_TEST_TOURS = {
    "Kyrkjetaket",
    "Galtatind",
    "Kjovskarstinden",
    "Skittentinden",
    "Durmaalstinden",
    "Middagstinden",
    "Storebjoern",
    "Store_Smoerstabbtinden",
}


# Raster output constants
MIN_COST = 1
MAX_COST = 5000
NODATA_VALUE = 65535


# Simple barrier/reduction values for testing.
RIVER_BARRIER_VALUE = 200.0
ROAD_REDUCTION_VALUE = 1.0
TRAIL_REDUCTION_VALUE = 2.0
BRIDGE_REDUCTION_VALUE = 1.0
TRAIL_INPUT_KEY = "tractorroad_trail_forest"

SAFE_MASK_SOFT_PARAMS = {
    "slope_threshold": 30.0,
    "slope_width": 6.0,
    "pra_runout_combined_threshold": 5.0,
    "pra_runout_combined_width": 1.5,
}

STEEP_SLOPE_BARRIER_PARAMS = {
    "enabled": True,
    "start_deg": 45.0,
    "full_deg": 50.0,
    "start_value": 100.0,
    "barrier_value": 1500.0,
    "power": 3.0,
}


# Testing PRA/runout input-layer parameters
PRA_RUNOUT_PARAMS = {
    "output_nodata": -9999.0,
    "release_threshold": 0.15,
    "release_input_max": 0.99,
    "release_min": 7.2,
    "release_max": 100.0,
    "runout_distance_min": 0.0,
    "runout_distance_max": 10000.0,
    "runout_min": 1.0,
    "runout_max": 7.2,
    "distance_lambda": 0.016,
    "distance_alpha": 0.82,
}


# Terrain transform parameters
SLOPE_TRANSFORM = "threshold_jump"

TRANSFORM_PARAMS = {
    "windshelter": {
        "x0": 0.0,
        "k": 5.5,
        "min_cost": 5.0,
        "max_cost": 30.0,
    },
    "slope_threshold_jump": {
        "threshold": 30.0,
        "low_max": 0.05,
        "low_power": 3.0,
        "jump_start": 29.0,
        "jump_end": 30.0,
        "jump_to": 0.35,
        "tail_end": 45.0,
        "min_cost": 2.0,
        "max_cost": 100.0,
    },
}


# Weights for the simple testing cost surface.
WEIGHTS_TERRAIN = {
    "slope": 0.53,
    "windshelter": 0.12,
    "pra_runout_combined": 0.35,
}


# Local testing route settings
ROUTING_SETTINGS = {
    "lambda_weight": 0.6,
    "smooth_threshold": 10.0,
    "region_buffer_m": 5000.0,
}
