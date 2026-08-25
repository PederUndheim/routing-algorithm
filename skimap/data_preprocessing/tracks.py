"""National GPS-track normalization.

The percentile scale is computed once over all national track data and
cached, then every tile applies that same constant. Normalizing per tile
would map the same track density to different cost reductions on either
side of a tile edge, and the national mosaic would show a grid of seams.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from osgeo import gdal

from skimap import config, paths

gdal.UseExceptions()

_BINS = 65536   # tracks is UInt16, so a full histogram is exact and cheap


def compute_scale(out_path: Path = paths.TRACK_SCALE) -> tuple[float, float]:
    """Percentile scale over the national tracks data. Caches to out_path.

    Percentiles are taken over positive pixels only - the zero background
    is most of the country and would otherwise drag the scale down until
    sparse, one-pass tracks read as busy routes.

    Note the scale comes from the ~56% of tiles the source rasters cover.
    That is correct rather than convenient: uncovered ground has no tracks,
    so it gets no reduction, and including its zeros would only distort the
    scale for the ground that does have data.

    Exact, not sampled: the source is UInt16, so one 65536-bin histogram
    holds the whole national distribution and the percentiles come straight
    out of its cumulative sum. Sampling would make the scale depend on
    which pixels were drawn, and the whole point of computing it once is
    that it never moves.
    """
    src = paths.layer("tracks")
    ds = gdal.Open(str(src))
    band = ds.GetRasterBand(1)
    w, h = ds.RasterXSize, ds.RasterYSize
    if band.DataType != gdal.GDT_UInt16:
        raise ValueError(
            f"{src.name} is {gdal.GetDataTypeName(band.DataType)}, expected UInt16 - "
            "the exact histogram below assumes it"
        )

    counts = np.zeros(_BINS, dtype=np.int64)
    block = 256   # rows; at national width one row is ~84k px
    for y in range(0, h, block):
        ny = min(block, h - y)
        arr = band.ReadAsArray(0, y, w, ny)
        counts += np.bincount(arr.ravel(), minlength=_BINS)
        if (y // block) % 50 == 0:
            print(f"  {100 * (y + ny) / h:5.1f}%", flush=True)
    ds = None

    background = int(counts[0])
    counts[0] = 0   # nodata and untravelled ground are the same thing here
    positive = int(counts.sum())
    if positive == 0:
        raise ValueError(f"No positive pixels in {src} - nothing to normalize against")

    cum = np.cumsum(counts)
    p = config.TRACK_NORMALIZATION
    lower = float(np.searchsorted(cum, positive * p["lower_percentile"] / 100.0))
    upper = float(np.searchsorted(cum, positive * p["upper_percentile"] / 100.0))
    if upper <= lower:
        raise ValueError(
            f"Track percentiles collapsed: p{p['lower_percentile']:g}={lower:g} "
            f">= p{p['upper_percentile']:g}={upper:g}. The density values are too "
            "coarse for this pair of percentiles to separate."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "source": src.name,
                "lower_percentile": p["lower_percentile"],
                "upper_percentile": p["upper_percentile"],
                "lower": lower,
                "upper": upper,
                "positive_px": positive,
                "background_px": background,
                "max": float(np.flatnonzero(counts)[-1]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"{positive:,} positive px of {positive + background:,} "
        f"({100 * positive / (positive + background):.2f}%)\n"
        f"p{p['lower_percentile']:g} = {lower:g}, p{p['upper_percentile']:g} = {upper:g} "
        f"-> {out_path}"
    )
    return lower, upper


def load_scale(path: Path = paths.TRACK_SCALE) -> tuple[float, float]:
    if not path.exists():
        raise FileNotFoundError(
            f"No track scale at {path}. Build it with 'python -m skimap.cli tracks'."
        )
    d = json.loads(path.read_text(encoding="utf-8"))
    return float(d["lower"]), float(d["upper"])


def normalize(tracks: np.ndarray, scale: tuple[float, float]) -> np.ndarray:
    """Map track density onto [0, 1] using the one national scale."""
    lo, hi = scale
    if hi <= lo:
        return np.zeros_like(tracks, dtype=np.float32)
    return np.clip((tracks - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)
