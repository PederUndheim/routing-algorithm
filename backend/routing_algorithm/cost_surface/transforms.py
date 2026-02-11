import numpy as np
from backend import config

EPS = 1e-9

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


def to_cost_x_y(unit_0_to_1: np.ndarray, min_cost=config.MIN_COST, max_cost=config.MAX_COST) -> np.ndarray:
    """
    Map a [0,1] unit value to [min_cost, max_cost].
    """
    out = min_cost + unit_0_to_1 * (max_cost - min_cost)
    return out.astype(np.float32, copy=False)

def smooth_gate_below(x: np.ndarray, threshold: float, width: float) -> np.ndarray:
    """
    Returns weight in [0,1]:
      ~1 well below threshold
      ~0 well above threshold
    width controls how gradual the transition is (bigger = softer).
    """
    x = x.astype(np.float32, copy=False)
    # Logistic centered at threshold, flipped so "below" gives high weight
    k = 6.0 / float(width)
    return (1.0 / (1.0 + np.exp(k * (x - threshold)))).astype(np.float32)



# --- Terrain transforms ---
def slope_cost(transform: str, slope: np.ndarray, *, min_cost: float, max_cost: float, **params) -> np.ndarray:
    if transform == "logistic":
        u = logistic(slope, **params)
    elif transform == "richards":
        u = richards_curve(slope, **params)
    elif transform == "hyperbolic":
        u = hyperbolic_tangent(slope, **params)
    else:
        raise ValueError(f"Unknown slope transform: {transform}")
    return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)

def curvature_cost(curvature: np.ndarray, x0: float, k: float, min_cost: float, max_cost: float) -> np.ndarray:
    u = logistic(curvature, x0=x0, k=k)
    return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)

# def curvature_cost_with_neutral(
#     curvature: np.ndarray,
#     t: float,               # values in [-t, t] are neutral
#     x0: float,              # midpoint for logistic
#     k: float,               # steepness for logistic      
#     min_cost: float,
#     max_cost: float
# ) -> np.ndarray:
#     c = _as_float(curvature)
#     if not (0.0 <= t < 1.0):
#         raise ValueError("Parameter t must be in [0, 1).")
#     denom = max(EPS, 1.0 - t)

#     c2 = np.zeros_like(c, dtype=np.float32)
#     mask_pos = c > t
#     mask_neg = c < -t
#     c2[mask_pos] = (c[mask_pos] - t) / denom
#     c2[mask_neg] = (c[mask_neg] + t) / denom
#     c2 = np.clip(c2, -1.0, 1.0)

#     u = logistic(c2, x0=x0, k=k)

#     return to_cost_x_y(u, min_cost=min_cost, max_cost=max_cost)




# --- Layer builder for MIN/MAX-logic ---

def barrier_layer_from_mask(mask: np.ndarray, barrier_value: float, min_cost: float) -> np.ndarray:
    """
    Build a 'barrier' layer that is 1 everywhere, barrier_value where mask is True.
    Intended for MAX combine so barriers trump.
    """
    mask = _as_float(mask)
    layer = np.full_like(mask, min_cost, dtype=np.float32)
    layer[mask.astype(bool)] = barrier_value
    return layer

def reduction_layer_from_mask_soft(mask: np.ndarray, validity_weight: np.ndarray, low_value: float, elsewhere_value: float) -> np.ndarray:
    """
    Build a 'reduction' layer that is low_value on mask (roads/tracks) if in validity mask (ex. not in avalanche danger), high elsewhere.
    Soft gate based on validity weight in [0,1].
    Intended for MIN combine so tracks lower the cost.
    """
    mask = mask.astype(bool)
    validity_weight = np.clip(validity_weight, 0.0, 1.0).astype(np.float32, copy=False)

    out = np.full(mask.shape, elsewhere_value, dtype=np.float32)
    blended = elsewhere_value - validity_weight * (elsewhere_value - low_value)
    out[mask] = blended[mask]
    return out