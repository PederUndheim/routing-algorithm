"""Assembling cost layers: barriers combine with MAX, reductions with MIN."""

from __future__ import annotations

import numpy as np


def weighted_sum(layers: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    """Weighted mean of the terrain layers. Weights are normalized here.

    Every layer must cover every pixel. Dropping one where its data is
    missing and renormalizing the rest sounds neutral and is not: see the
    note on the windshelter fill in cost.surface.
    """
    total = np.zeros_like(next(iter(layers.values())), dtype=np.float32)
    wsum = 0.0
    for name, arr in layers.items():
        w = float(weights[name])
        total += arr.astype(np.float32, copy=False) * w
        wsum += w
    if wsum <= 0:
        raise ValueError("Sum of weights must be > 0")
    return total / wsum


def max_combine(*arrays: np.ndarray) -> np.ndarray:
    out = arrays[0].astype(np.float32, copy=False)
    for a in arrays[1:]:
        out = np.maximum(out, a.astype(np.float32, copy=False))
    return out


def min_combine(*arrays: np.ndarray) -> np.ndarray:
    out = arrays[0].astype(np.float32, copy=False)
    for a in arrays[1:]:
        out = np.minimum(out, a.astype(np.float32, copy=False))
    return out


def gate_below(x: np.ndarray, *, threshold: float, width: float) -> np.ndarray:
    """Soft 1 -> 0 step at `threshold`, so gating fades instead of snapping."""
    k = 6.0 / float(width)
    e = np.clip(k * (x.astype(np.float32, copy=False) - threshold), -60.0, 60.0)
    return (1.0 / (1.0 + np.exp(e))).astype(np.float32, copy=False)


def barrier_from_mask(mask: np.ndarray, *, barrier_value: float, min_cost: float) -> np.ndarray:
    out = np.full(mask.shape, min_cost, dtype=np.float32)
    out[mask.astype(bool)] = barrier_value
    return out


def reduction_from_mask(
    mask: np.ndarray,
    gate: np.ndarray,
    *,
    low_value: float,
    elsewhere: float,
) -> np.ndarray:
    """Drop cost to low_value on the mask, scaled by the gate; elsewhere no-op."""
    mask = mask.astype(bool)
    gate = np.clip(gate, 0.0, 1.0).astype(np.float32, copy=False)

    out = np.full(mask.shape, elsewhere, dtype=np.float32)
    out[mask] = (elsewhere - gate * (elsewhere - low_value))[mask]
    return out


def steep_slope_barrier(
    slope: np.ndarray,
    *,
    start_deg: float,
    full_deg: float,
    start_value: float,
    barrier_value: float,
    power: float,
) -> np.ndarray:
    """Zero below start_deg, rising to barrier_value at full_deg."""
    if full_deg <= start_deg:
        raise ValueError("full_deg must be greater than start_deg")
    if power <= 0:
        raise ValueError("power must be > 0")

    s = np.where(np.isnan(slope), start_deg - 1.0, slope).astype(np.float32, copy=False)
    t = np.clip((s - start_deg) / (full_deg - start_deg), 0.0, 1.0)
    out = start_value + np.power(t, power) * (barrier_value - start_value)
    return np.where(s < start_deg, 0.0, out).astype(np.float32, copy=False)


def clip_round(cost: np.ndarray, *, min_cost: float, max_cost: float) -> np.ndarray:
    return np.round(np.clip(cost, min_cost, max_cost)).astype(np.uint16, copy=False)
