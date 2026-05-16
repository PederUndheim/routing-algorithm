import numpy as np
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "MPLCONFIGDIR" not in os.environ:
    mpl_config_dir = Path(os.getenv("TMPDIR", "/tmp")) / "routing_algorithm_matplotlib"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)

if "XDG_CACHE_HOME" not in os.environ:
    xdg_cache_dir = Path(os.getenv("TMPDIR", "/tmp")) / "routing_algorithm_cache"
    xdg_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["XDG_CACHE_HOME"] = str(xdg_cache_dir)

import matplotlib

from backend import config
from backend.file_handler.area_context import load_area
from backend.routing_algorithm.cost_surface.layers import steep_slope_barrier
from backend.routing_algorithm.cost_surface.raster_helpers import read_raster
from backend.routing_algorithm.cost_surface.transforms import (
    slope_cost,
    threshold_jump_slope,
    to_cost_x_y,
)
from backend.routing_algorithm.testing import config as testing_config
from backend.routing_algorithm.testing.transforms import (
    threshold_jump_slope as testing_threshold_jump_slope,
    to_cost_x_y as testing_to_cost_x_y,
)

SHOW_FIGURES = os.getenv("SHOW_FIGURES", "0") == "1"
if not SHOW_FIGURES:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt

# Output folder
FIG_DIR = PROJECT_ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

# Style
plt.rcParams.update({
    "font.size": 15,
    "axes.labelsize": 15,
    "legend.fontsize": 12,
})


def save_plot(path: Path):
    plt.savefig(path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close()


# --- Membership functions ---
def tanh_membership(x, x0, k):
    return 0.5 * (1 + np.tanh((x - x0) / k))

def logistic_membership(x, x0, k):
    return 1.0 / (1.0 + np.exp(-k * (x - x0)))

def weibull_decay(x, lam, alpha):
    return np.exp(- (lam * x) ** alpha)





# --- Plot functions ---
def plot_tanh(x0, k):
    x = np.linspace(0, 90, 500)
    y = tanh_membership(x, x0, k)

    plt.figure(figsize=(6, 4))
    plt.plot(x, y, linewidth=2)

    plt.xlabel("Slope (°)")    
    plt.ylabel("Membership value")
    plt.ylim(-0.05, 1.05)
    plt.grid(True, alpha=0.2)

    # Equation
    plt.text(29, 0.07, r"$f(x)=\frac{1}{2}\left(1+\tanh\left(\frac{x-34}{9}\right)\right)$", fontsize=18)

    save_plot(FIG_DIR / "tanh_membership.pdf")

def plot_logistic(x0, k):
    x = np.linspace(-1.4, 1.4, 500)
    y = logistic_membership(x, x0, k)

    plt.figure(figsize=(6, 4))
    plt.plot(x, y, linewidth=2)

    plt.xlabel("Wind shelter index")
    plt.ylabel("Membership value")
    plt.ylim(-0.05, 1.05)
    plt.grid(True, alpha=0.2)

    # Equation
    plt.text(0.05, 0.28, r"$f(x)=\frac{1}{1+e^{-5.5(x-0.0)}}$", fontsize=18)

    save_plot(FIG_DIR / "logistic_membership.pdf")

def plot_weibull(lam, alpha):
    x = np.linspace(0, 400, 500)  # distance in meters
    y = weibull_decay(x, lam, alpha)

    plt.figure(figsize=(6, 4))
    plt.plot(x, y, linewidth=2)

    plt.xlabel("Horizontal distance from release area (m)")
    plt.ylabel("Membership value")
    plt.ylim(-0.05, 1.05)
    plt.grid(True, alpha=0.2)

    # Equation
    plt.text(
        52, 0.675,
        rf"$f(x)=\exp\left[-({lam:.3f}x)^{{{alpha:.2f}}}\right]$"
    )

    save_plot(FIG_DIR / "weibull_decay.pdf")


def plot_threshold_jump_slope():
    params = config.TRANSFORM_PARAMS["slope_threshold_jump"].copy()
    min_cost = params.pop("min_cost")
    max_cost = params.pop("max_cost")

    x = np.linspace(0, 60, 700)
    y = threshold_jump_slope(x, **params)
    cost = to_cost_x_y(y, min_cost=min_cost, max_cost=max_cost)
    threshold = float(params["threshold"])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(x, y, linewidth=2.5, color="#367E98", label="Membership")
    ax.axvline(threshold, color="black", linestyle="--", linewidth=1.4, alpha=0.65)
    ax.text(threshold + 0.8, 0.08, f"{threshold:.0f}° threshold", fontsize=13)
    ax.axvline(float(params["jump_start"]), color="#777777", linestyle=":", linewidth=1.1, alpha=0.6)
    ax.axvline(float(params["jump_end"]), color="#777777", linestyle=":", linewidth=1.1, alpha=0.6)
    ax.axvline(float(params["tail_end"]), color="#EE7B04", linestyle=":", linewidth=1.1, alpha=0.6)

    ax.set_xlabel("Slope (°)")
    ax.set_ylabel("Membership value")
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlim(0, 60)
    ax.grid(True, alpha=0.2)

    ax_cost = ax.twinx()
    ax_cost.plot(x, cost, linewidth=1.7, color="#EE7B04", alpha=0.85, label="Cost")
    ax_cost.set_ylabel("Slope cost")
    ax_cost.set_ylim(
        min_cost - 0.05 * (max_cost - min_cost),
        max_cost + 0.05 * (max_cost - min_cost),
    )

    label_text = (
        f"low_max={params['low_max']:.2f}\n"
        f"sharp linear {params['jump_start']:.1f}° to {params['jump_end']:.1f}°\n"
        f"slower linear {params['jump_end']:.1f}° to {params['tail_end']:.1f}°"
    )
    ax.text(2, 0.72, label_text, fontsize=13)

    lines, labels = ax.get_legend_handles_labels()
    cost_lines, cost_labels = ax_cost.get_legend_handles_labels()
    ax.legend(lines + cost_lines, labels + cost_labels, loc="lower right")

    save_plot(FIG_DIR / "threshold_jump_slope_membership.pdf")


def plot_testing_threshold_jump_slope():
    params = testing_config.TRANSFORM_PARAMS[
        f"slope_{testing_config.SLOPE_TRANSFORM}"
    ].copy()
    min_cost = params.pop("min_cost")
    max_cost = params.pop("max_cost")

    x = np.linspace(0, 60, 700)
    membership = testing_threshold_jump_slope(x, **params)
    cost = testing_to_cost_x_y(membership, min_cost=min_cost, max_cost=max_cost)

    threshold = float(params["threshold"])
    barrier_params = getattr(testing_config, "STEEP_SLOPE_BARRIER_PARAMS", {})
    barrier_start = float(barrier_params.get("start_deg", np.nan))
    barrier_full = float(barrier_params.get("full_deg", np.nan))

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.plot(x, membership, linewidth=2.6, color="#367E98", label="Slope membership")
    ax.axvline(threshold, color="black", linestyle="--", linewidth=1.3, alpha=0.65)
    ax.text(threshold + 0.7, 0.06, f"{threshold:.0f}° threshold", fontsize=12)
    ax.axvline(float(params["jump_start"]), color="#777777", linestyle=":", linewidth=1.1, alpha=0.6)
    ax.axvline(float(params["jump_end"]), color="#777777", linestyle=":", linewidth=1.1, alpha=0.6)

    if np.isfinite(barrier_start):
        ax.axvline(barrier_start, color="#EE7B04", linestyle=":", linewidth=1.4, alpha=0.8)
        ax.text(barrier_start + 0.7, 0.18, f"{barrier_start:.1f}° barrier start", fontsize=11)
    if np.isfinite(barrier_full):
        ax.axvline(barrier_full, color="#B33A3A", linestyle=":", linewidth=1.4, alpha=0.8)
        ax.text(barrier_full + 0.7, 0.30, f"{barrier_full:.0f}° barrier full", fontsize=11)

    ax.set_title("Testing Slope Membership Function")
    ax.set_xlabel("Slope (°)")
    ax.set_ylabel("Membership value")
    ax.set_xlim(0, 60)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.2)

    ax_cost = ax.twinx()
    ax_cost.plot(x, cost, linewidth=1.8, color="#EE7B04", alpha=0.9, label="Slope cost")
    ax_cost.set_ylabel("Slope cost")
    ax_cost.set_ylim(
        min_cost - 0.05 * (max_cost - min_cost),
        max_cost + 0.05 * (max_cost - min_cost),
    )

    label_text = (
        f"low_max={params['low_max']:.2f}\n"
        f"jump_to={params['jump_to']:.2f}\n"
        f"sharp linear {params['jump_start']:.1f}° to {params['jump_end']:.1f}°\n"
        f"slower linear {params['jump_end']:.1f}° to {params['tail_end']:.1f}°"
    )
    ax.text(2, 0.73, label_text, fontsize=12)

    lines, labels = ax.get_legend_handles_labels()
    cost_lines, cost_labels = ax_cost.get_legend_handles_labels()
    ax.legend(lines + cost_lines, labels + cost_labels, loc="lower right")

    save_plot(FIG_DIR / "testing_slope_membership_function.pdf")


def _normal_slope_cost_curve(slope_deg: np.ndarray) -> np.ndarray:
    return slope_cost(
        config.SLOPE_TRANSFORM,
        slope_deg,
        **config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"],
    )


def _steep_slope_barrier_curve(slope_deg: np.ndarray) -> np.ndarray:
    params = config.STEEP_SLOPE_BARRIER_PARAMS
    return steep_slope_barrier(
        slope_arr=slope_deg,
        start_deg=float(params["start_deg"]),
        full_deg=float(params["full_deg"]),
        start_value=float(params["start_value"]),
        barrier_value=float(params["barrier_value"]),
        power=float(params["power"]),
    )


def _load_normal_slope_and_pra(area_id: str) -> tuple[np.ndarray, np.ndarray]:
    _, inputs = load_area(area_id)
    slope, _ = read_raster(inputs["slope"])
    pra_cost, _ = read_raster(inputs["pra_runout_combined"])
    pra_cost = np.where(np.isnan(pra_cost), 1.0, pra_cost).astype(np.float32, copy=False)

    if slope.shape != pra_cost.shape:
        raise ValueError(f"slope and PRA/runout rasters must have the same shape for {area_id}")

    finite = np.isfinite(slope) & np.isfinite(pra_cost)
    return slope[finite].astype(np.float32, copy=False), pra_cost[finite].astype(np.float32, copy=False)


def _collect_normal_slope_and_pra(area_ids: list[str]) -> tuple[np.ndarray, np.ndarray]:
    slope_parts = []
    pra_parts = []
    for area_id in area_ids:
        slope, pra_cost = _load_normal_slope_and_pra(area_id)
        slope_parts.append(slope)
        pra_parts.append(pra_cost)
    return np.concatenate(slope_parts), np.concatenate(pra_parts)


def _binned_pra_statistics(
    slope: np.ndarray,
    pra_cost: np.ndarray,
    *,
    max_slope: float = 60.0,
    bin_width: float = 1.0,
) -> dict[str, np.ndarray]:
    bin_edges = np.arange(0.0, max_slope + bin_width, bin_width, dtype=np.float32)
    centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    pra_mean = np.full_like(centers, np.nan, dtype=np.float32)
    pra_median = np.full_like(centers, np.nan, dtype=np.float32)
    pra_p95 = np.full_like(centers, np.nan, dtype=np.float32)
    counts = np.zeros_like(centers, dtype=np.int64)

    finite = np.isfinite(slope) & np.isfinite(pra_cost)
    slope = slope[finite]
    pra_cost = pra_cost[finite]

    for i, (lo, hi) in enumerate(zip(bin_edges[:-1], bin_edges[1:])):
        in_bin = (slope >= lo) & (slope < hi)
        counts[i] = int(np.count_nonzero(in_bin))
        if counts[i] == 0:
            continue
        values = pra_cost[in_bin]
        pra_mean[i] = float(np.nanmean(values))
        pra_median[i] = float(np.nanmedian(values))
        pra_p95[i] = float(np.nanpercentile(values, 95))

    slope_curve = _normal_slope_cost_curve(centers)
    combined_mean = (slope_curve + pra_median) / 2.0

    return {
        "centers": centers,
        "counts": counts,
        "slope_curve": slope_curve,
        "pra_mean": pra_mean,
        "pra_median": pra_median,
        "pra_p95": pra_p95,
        "combined_mean": combined_mean,
    }


def _peak_xy(
    x: np.ndarray,
    y: np.ndarray,
    counts: np.ndarray,
    *,
    min_count: int = 50,
) -> tuple[float, float]:
    valid = np.isfinite(y) & (counts >= min_count)
    if not np.any(valid):
        return np.nan, np.nan
    valid_idx = np.flatnonzero(valid)
    peak_idx = int(valid_idx[np.nanargmax(y[valid])])
    return float(x[peak_idx]), float(y[peak_idx])


def plot_slope_pra_thesis_relationship(
    area_ids: list[str] | None = None,
    *,
    max_slope: float = 70.0,
    bin_width: float = 1.0,
    min_peak_count: int = 50,
) -> Path:
    area_ids = list(area_ids or testing_config.DEFAULT_TEST_AREAS)
    slope, pra_cost = _collect_normal_slope_and_pra(area_ids)
    series = _binned_pra_statistics(
        slope,
        pra_cost,
        max_slope=max_slope,
        bin_width=bin_width,
    )

    x = series["centers"]
    counts = series["counts"]
    p95_peak = _peak_xy(x, series["pra_p95"], counts, min_count=min_peak_count)

    fig, ax = plt.subplots(figsize=(9.5, 5.7))
    mean_color = "#7FA9B8"
    median_color = "#2F6F86"
    p95_color = "#17475A"
    ax.plot(x, series["pra_mean"], color=mean_color, linewidth=2.1, alpha=0.9, label="Derived mean of avalanche exposure cost")
    ax.plot(x, series["pra_median"], color=median_color, linewidth=2.4, label="Derived median of avalanche exposure cost")
    ax.plot(x, series["pra_p95"], color=p95_color, linewidth=1.9, linestyle="--", alpha=0.9, label="Derived P95 of avalanche exposure cost")

    if np.all(np.isfinite(p95_peak)):
        ax.scatter([p95_peak[0]], [p95_peak[1]], s=54, color=p95_color, edgecolor="black", zorder=6)
        ax.annotate(
            f"P95 peak\n({p95_peak[0]:.1f}°)",
            xy=p95_peak,
            xytext=(max(p95_peak[0] + 7, 6.0), min(p95_peak[1] + 4.0, 100.0)),
            arrowprops={"arrowstyle": "->", "color": p95_color, "linewidth": 1.1},
            fontsize=11,
        )

    ax.set_xlabel("Slope (°)")
    ax.set_ylabel("Cost value")
    ax.set_xlim(0, max_slope)
    ax.set_ylim(0, 108)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=True)

    out_path = FIG_DIR / "thesis_slope_pra_relationship.pdf"
    fig.savefig(out_path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

    print(f"Slope/PRA thesis figure written to {out_path}")
    return out_path


def plot_slope_cost_thesis_focus(
    area_ids: list[str] | None = None,
    *,
    max_slope: float = 70.0,
    bin_width: float = 1.0,
) -> Path:
    area_ids = list(area_ids or testing_config.DEFAULT_TEST_AREAS)
    slope, pra_cost = _collect_normal_slope_and_pra(area_ids)
    series = _binned_pra_statistics(
        slope,
        pra_cost,
        max_slope=max_slope,
        bin_width=bin_width,
    )

    slope_params = config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"]
    threshold = float(slope_params["threshold"])
    jump_start = float(slope_params["jump_start"])
    jump_end = float(slope_params["jump_end"])
    tail_end = float(slope_params["tail_end"])

    x = np.linspace(0.0, max_slope, 1000, dtype=np.float32)
    slope_curve = _normal_slope_cost_curve(x)

    fig, ax = plt.subplots(figsize=(9.5, 5.7))
    ax.plot(
        series["centers"],
        series["combined_mean"],
        color="#888888",
        linewidth=2.0,
        alpha=0.75,
        label="Mean of slope and avalanche exposure cost",
    )
    ax.plot(
        series["centers"],
        series["pra_median"],
        color="#B8B8B8",
        linewidth=1.8,
        linestyle="--",
        alpha=0.9,
        label="Derived median of avalanche exposure cost",
    )
    ax.plot(x, slope_curve, color="#2F6F86", linewidth=3.4, label="Slope cost")

    ax.axvspan(jump_start, jump_end, color="#2F6F86", alpha=0.10)
    ax.axvspan(jump_end, tail_end, color="#E07A24", alpha=0.08)
    ax.axvline(threshold, color="#333333", linestyle="--", linewidth=1.2, alpha=0.72)
    ax.axvline(tail_end, color="#E07A24", linestyle=":", linewidth=1.5, alpha=0.80)

    ax.text(2.0, 8.0, "gentle increase below threshold", fontsize=12, color="#31434B")
    ax.text(21, 34.0, "rapid ramp\n(29° - 30°)", fontsize=12, color="#31434B")
    ax.text(30.5, 76.0, "linear rise\n(30° - 45°)", fontsize=12, color="#31434B")
    ax.text(tail_end + 1, 94.0, "slope cost reaches max", fontsize=12, color="#31434B")

    ax.set_xlabel("Slope (°)")
    ax.set_ylabel("Cost value")
    ax.set_xlim(0, max_slope)
    ax.set_ylim(0, 112)
    ax.grid(True, alpha=0.22)

    lines, labels = ax.get_legend_handles_labels()
    ax.legend(lines, labels, loc="upper left", frameon=True)

    out_path = FIG_DIR / "thesis_slope_cost_with_pra_context.pdf"
    fig.savefig(out_path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

    print(f"Slope cost thesis figure written to {out_path}")
    return out_path


def plot_steep_slope_barrier_thesis(*, max_slope: float = 60.0) -> Path:
    params = config.STEEP_SLOPE_BARRIER_PARAMS
    start_deg = float(params["start_deg"])
    full_deg = float(params["full_deg"])
    start_value = float(params["start_value"])
    barrier_value = float(params["barrier_value"])
    power = float(params["power"])

    x = np.linspace(0.0, max_slope, 1000, dtype=np.float32)
    barrier_curve = _steep_slope_barrier_curve(x)

    fig, ax = plt.subplots(figsize=(9.5, 5.7))
    ax.plot(
        x,
        barrier_curve,
        color="#B33A3A",
        linewidth=3.2,
        label="Steep slope barrier layer",
    )

    ax.axvspan(start_deg, full_deg, color="#B33A3A", alpha=0.10)
    ax.axvline(start_deg, color="#B33A3A", linestyle=":", linewidth=1.4, alpha=0.85)
    ax.axvline(full_deg, color="#2F3437", linestyle=":", linewidth=1.4, alpha=0.85)

    ax.scatter(
        [start_deg, full_deg],
        [start_value, barrier_value],
        s=[48, 58],
        color=["#B33A3A", "#B33A3A"],
        edgecolor="white",
        linewidth=0.8,
        zorder=6,
    )
    ax.annotate(
        f"barrier begins at {start_deg:.0f}°",
        xy=(start_deg, start_value),
        xytext=(30.5, 250),
        arrowprops={"arrowstyle": "->", "color": "#B33A3A", "linewidth": 1.1},
        fontsize=12,
        color="#31434B",
    )
    ax.annotate(
        f"full barrier at {full_deg:.0f}°",
        xy=(full_deg, barrier_value),
        xytext=(32.5, 1330),
        arrowprops={"arrowstyle": "->", "color": "#B33A3A", "linewidth": 1.1},
        fontsize=12,
        color="#31434B",
    )
    ax.text(
        50.4,
        420,
        rf"cubic ramp $(t^{power:.0f})$",
        fontsize=10.5,
        color="#31434B",
    )
    ax.text(10.3, 70.0, f"no barrier below {start_deg:.0f}°", fontsize=12, color="#31434B")

    ax.set_xlabel("Slope (°)")
    ax.set_ylabel("Cost value")
    ax.set_xlim(0, max_slope)
    ax.set_ylim(0, barrier_value * 1.08)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=True)

    out_path = FIG_DIR / "thesis_steep_slope_barrier.pdf"
    fig.savefig(out_path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

    print(f"Steep slope barrier thesis figure written to {out_path}")
    return out_path





# --- Main ---
def main():
    plot_tanh(x0=34, k=9)
    plot_logistic(x0=0.0, k=5.5)
    plot_weibull(lam=0.016, alpha=0.82)
    plot_threshold_jump_slope()
    plot_testing_threshold_jump_slope()
    plot_slope_pra_thesis_relationship()
    plot_slope_cost_thesis_focus()
    plot_steep_slope_barrier_thesis()


if __name__ == "__main__":
    main()
