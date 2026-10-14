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


# Corner gaps are closed in at most this many passes. A fill can open a new
# corner against the next steep cell along, so the pass repeats; the halo the
# surface reads with has to cover the same number of cells.
CORNER_PASSES = 4


def fill_corners(
    cost: np.ndarray,
    steep: np.ndarray,
    slope: np.ndarray,
    *,
    passes: int = CORNER_PASSES,
) -> tuple[np.ndarray, np.ndarray]:
    """Close every diagonal gap between steep cells with one cell.

    A gap is two steep cells meeting at a corner with both other cells of
    that 2x2 gentle. r.cost moves 8-connected and charges a diagonal step on
    its two end cells only, so it crosses there - between the two gentle
    cells - and pays for neither steep one. Filling one of the gentle cells
    makes the steep ground 4-connected through the corner, which is what an
    8-connected route cannot cross.

    The steeper of the two gentle cells is filled, with the cheaper of the
    two steep cells' cost: the least change that closes the gap. A gap one
    whole cell wide is not a corner and stays open - it is real ground.

    Returns (cost, steep) with the filled cells added to `steep`, so a ring
    spread after this counts them as steep. Edges are not padded: give it
    arrays read with a halo of `passes` cells.
    """
    cost = cost.astype(np.float32, copy=True)
    steep = steep.astype(bool, copy=True)
    s = np.s_
    # (one steep cell, the other, one gentle corner, the other), as slices of
    # the 2x2 window's top-left corner over the whole array.
    diagonals = (
        (s[:-1, :-1], s[1:, 1:], s[:-1, 1:], s[1:, :-1]),   # top-left to bottom-right
        (s[:-1, 1:], s[1:, :-1], s[:-1, :-1], s[1:, 1:]),   # top-right to bottom-left
    )
    for _ in range(passes):
        fill = np.zeros_like(cost)
        for a, b, p, q in diagonals:
            gap = steep[a] & steep[b] & ~steep[p] & ~steep[q]
            if not gap.any():
                continue
            value = np.where(gap, np.minimum(cost[a], cost[b]), 0.0)
            take_p = slope[p] >= slope[q]
            np.maximum(fill[p], np.where(take_p, value, 0.0), out=fill[p])
            np.maximum(fill[q], np.where(take_p, 0.0, value), out=fill[q])
        filled = fill > 0
        if not filled.any():
            break
        cost = np.maximum(cost, fill)
        steep |= filled
    return cost, steep


def buffer_steep(cost: np.ndarray, steep: np.ndarray, *, add: float) -> np.ndarray:
    """`add` cost units on every gentle cell touching steep ground (its 8
    neighbours), on top of the cell's own cost.

    A fixed toll, not the steep price: it keeps routes a cell off the edge of
    steep ground, but a gentle gap between two steep patches stays far
    cheaper than the patches, so it is still worth the detour. Pricing the
    ring like the steep ground itself was tried and closed those gaps -
    routes then cut across the steep ground instead of round it.

    Edges are not padded: give it arrays read with a halo of one cell.
    """
    if not add:
        return cost
    near = steep.copy()
    rows, cols = steep.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                dst = near[max(0, -dy):rows - max(0, dy), max(0, -dx):cols - max(0, dx)]
                dst |= steep[max(0, dy):rows - max(0, -dy), max(0, dx):cols - max(0, -dx)]
    return np.where(near & ~steep, cost + np.float32(add), cost).astype(np.float32, copy=False)


def clip_round(cost: np.ndarray, *, min_cost: float, max_cost: float) -> np.ndarray:
    return np.round(np.clip(cost, min_cost, max_cost)).astype(np.uint16, copy=False)
