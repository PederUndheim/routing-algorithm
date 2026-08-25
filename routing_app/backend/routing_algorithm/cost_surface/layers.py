import numpy as np


def smooth_gate_below(x: np.ndarray, threshold: float, width: float) -> np.ndarray:
    """
    Return a soft validity weight:
    - close to 1 below threshold
    - close to 0 above threshold
    """
    x = x.astype(np.float32, copy=False)
    k = 6.0 / float(width)
    gate_exp = np.clip(k * (x - threshold), -60.0, 60.0)
    return (1.0 / (1.0 + np.exp(gate_exp))).astype(np.float32, copy=False)


def barrier_layer_from_mask(mask: np.ndarray, barrier_value: float, min_cost: float) -> np.ndarray:
    """Build a MAX-combine barrier layer from a boolean mask."""
    mask = mask.astype(bool)
    layer = np.full(mask.shape, min_cost, dtype=np.float32)
    layer[mask] = barrier_value
    return layer


def reduction_layer_from_mask_soft(
    mask: np.ndarray,
    validity_weight: np.ndarray,
    low_value: float,
    elsewhere_value: float,
) -> np.ndarray:
    """Build a MIN-combine reduction layer with soft validity weighting."""
    mask = mask.astype(bool)
    validity_weight = np.clip(validity_weight, 0.0, 1.0).astype(np.float32, copy=False)

    out = np.full(mask.shape, elsewhere_value, dtype=np.float32)
    blended = elsewhere_value - validity_weight * (elsewhere_value - low_value)
    out[mask] = blended[mask]
    return out


def steep_slope_barrier(
    slope_arr: np.ndarray,
    start_deg: float,
    full_deg: float,
    start_value: float,
    barrier_value: float,
    power: float,
) -> np.ndarray:
    """
    Build a MAX-combine barrier for very steep terrain.

    It has no effect below start_deg, reaches start_value at start_deg,
    and reaches barrier_value at and above full_deg.
    """
    if full_deg <= start_deg:
        raise ValueError("full_deg must be greater than start_deg")
    if power <= 0:
        raise ValueError("power must be > 0")

    slope_filled = np.where(np.isnan(slope_arr), start_deg - 1.0, slope_arr).astype(
        np.float32,
        copy=False,
    )
    t = np.clip((slope_filled - start_deg) / (full_deg - start_deg), 0.0, 1.0)
    barrier = start_value + np.power(t, power) * (barrier_value - start_value)
    barrier = np.where(slope_filled < start_deg, 0.0, barrier)
    return barrier.astype(np.float32, copy=False)
