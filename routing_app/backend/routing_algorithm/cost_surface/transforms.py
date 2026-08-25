import numpy as np
from backend import config

# --- Mathematical transforms ---

def _as_float(a: np.ndarray) -> np.ndarray:
    return a.astype(np.float32, copy=False)

def logistic(x: np.ndarray, *, x0: float, k: float) -> np.ndarray:
    """
    Logistic membership function.
    Maps input x to [0,1] using parameters:
        x0 -> midpoint (value of x where output = 0.5)
        k  -> slope/steepness (larger = sharper transition)
    """
    x = _as_float(x)
    y = 1.0 / (1.0 + np.exp(-k * (x - x0)))
    y = np.clip(y, 0.0, 1.0)           
    return y.astype(np.float32)

def richards_curve(x: np.ndarray, *, x0: float, k: float, nu: float) -> np.ndarray:
    x = _as_float(x)
    exp_term = np.exp(-(-k * (x - x0)))
    y = 1 - (1.0 / ((1.0 + exp_term) ** (1.0 / nu)))
    y = np.clip(y, 0.0, 1.0)
    return y.astype(np.float32)

def hyperbolic_tangent(x: np.ndarray, *, x0: float, k: float) -> np.ndarray:
    x = _as_float(x)
    y = 0.5 * (1.0 + np.tanh((x - x0) / k))
    y = np.clip(y, 0.0, 1.0)
    return y.astype(np.float32)

def threshold_jump_slope(
    slope: np.ndarray,
    *,
    threshold: float = 30.0,
    low_max: float = 0.05,
    low_power: float = 3.0,
    jump_start: float = 29.0,
    jump_end: float = 30.0,
    jump_to: float = 0.35,
    tail_end: float = 45.0,
) -> np.ndarray:
    if jump_end <= jump_start:
        raise ValueError("jump_end must be greater than jump_start")
    if tail_end <= jump_end:
        raise ValueError("tail_end must be greater than jump_end")

    s = slope.astype(np.float32, copy=False)

    # Gentle increase below the rapid threshold ramp.
    below = low_max * np.clip(s / threshold, 0.0, 1.0) ** low_power
    jump_start_value = low_max * np.clip(jump_start / threshold, 0.0, 1.0) ** low_power

    # Sharp linear ramp into the 30-degree threshold, then a slower linear climb.
    jump_t = np.clip((s - jump_start) / (jump_end - jump_start), 0.0, 1.0)
    jump_ramp = jump_start_value + (jump_to - jump_start_value) * jump_t

    tail_t = np.clip((s - jump_end) / (tail_end - jump_end), 0.0, 1.0)
    linear_tail = jump_to + (1.0 - jump_to) * tail_t

    u = np.where(s < jump_start, below, jump_ramp)
    u = np.where(s < jump_end, u, linear_tail)
    return np.clip(u, 0.0, 1.0).astype(np.float32)


def to_cost_x_y(unit_0_to_1: np.ndarray, min_cost=config.MIN_COST, max_cost=config.BASE_MAX_COST) -> np.ndarray:
    """
    Map a [0,1] unit value to [min_cost, max_cost].
    """
    out = min_cost + unit_0_to_1 * (max_cost - min_cost)
    return out.astype(np.float32, copy=False)

# --- Terrain transforms ---
def slope_cost(transform: str, slope: np.ndarray, *, min_cost: float, max_cost: float, **params) -> np.ndarray:
    if transform == "logistic":
        u = logistic(slope, **params)
    elif transform == "richards":
        u = richards_curve(slope, **params)
    elif transform == "hyperbolic":
        u = hyperbolic_tangent(slope, **params)
    elif transform == "threshold_jump":
        u = threshold_jump_slope(slope, **params)
    else:
        raise ValueError(f"Unknown slope transform: {transform}")
    return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)


def windshelter_cost(windshelter: np.ndarray, x0: float, k: float, min_cost: float, max_cost: float) -> np.ndarray:
    u = logistic(windshelter, x0=x0, k=k)
    return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)
