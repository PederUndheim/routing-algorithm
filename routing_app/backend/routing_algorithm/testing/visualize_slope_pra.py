from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
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

SHOW_FIGURES = os.getenv("SHOW_FIGURES", "0") == "1"
if not SHOW_FIGURES:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt

from backend.file_handler.area_context import load_area
from backend.routing_algorithm.cost_surface.raster_helpers import read_raster
from backend.routing_algorithm.testing import config
from backend.routing_algorithm.testing.paths import TestingAreaPaths
from backend.routing_algorithm.testing.pra_runout import build_testing_pra_runout_layer
from backend.routing_algorithm.testing.transforms import slope_cost


FIG_DIR = PROJECT_ROOT / "figures" / "testing"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def _steep_barrier_curve(slope_deg: np.ndarray) -> np.ndarray:
    params = config.STEEP_SLOPE_BARRIER_PARAMS
    start_deg = float(params["start_deg"])
    full_deg = float(params["full_deg"])
    slope_params = config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"]
    start_value = float(params.get("start_value", slope_params.get("tail_end_cost", config.MIN_COST)))
    barrier_value = float(params["barrier_value"])
    power = float(params["power"])

    if full_deg <= start_deg:
        raise ValueError("Steep slope barrier full_deg must be greater than start_deg")
    if power <= 0:
        raise ValueError("Steep slope barrier power must be > 0")

    slope = slope_deg.astype(np.float32, copy=False)
    t = np.clip((slope - start_deg) / (full_deg - start_deg), 0.0, 1.0)
    barrier = start_value + np.power(t, power) * (barrier_value - start_value)
    barrier = np.where(slope < start_deg, config.MIN_COST, barrier)
    return barrier.astype(np.float32, copy=False)


def _slope_cost_curve(slope_deg: np.ndarray) -> np.ndarray:
    return slope_cost(
        config.SLOPE_TRANSFORM,
        slope_deg,
        **config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"],
    )


def _binned_pra_by_slope(
    slope: np.ndarray,
    pra_cost: np.ndarray,
    *,
    bin_edges: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    median = np.full_like(centers, np.nan, dtype=np.float32)
    p10 = np.full_like(centers, np.nan, dtype=np.float32)
    p90 = np.full_like(centers, np.nan, dtype=np.float32)

    finite = np.isfinite(slope) & np.isfinite(pra_cost)
    slope = slope[finite]
    pra_cost = pra_cost[finite]

    for i, (lo, hi) in enumerate(zip(bin_edges[:-1], bin_edges[1:])):
        in_bin = (slope >= lo) & (slope < hi)
        if not np.any(in_bin):
            continue
        values = pra_cost[in_bin]
        median[i] = float(np.nanmedian(values))
        p10[i] = float(np.nanpercentile(values, 10))
        p90[i] = float(np.nanpercentile(values, 90))

    return centers, median, p10, p90


def _load_or_build_testing_pra(
    paths: TestingAreaPaths,
    inputs: dict[str, Path],
    *,
    rebuild_pra: bool,
) -> Path:
    if rebuild_pra or not paths.pra_runout_combined.exists():
        return build_testing_pra_runout_layer(paths, inputs)
    return paths.pra_runout_combined


def _load_slope_and_pra_cost(
    area_id: str,
    *,
    experiment: str = config.DEFAULT_EXPERIMENT,
    rebuild_pra: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    paths = TestingAreaPaths(area_id=area_id, experiment=experiment)
    _, inputs = load_area(area_id)

    pra_path = _load_or_build_testing_pra(paths, inputs, rebuild_pra=rebuild_pra)

    slope, _ = read_raster(inputs["slope"])
    pra_cost, _ = read_raster(pra_path)
    pra_cost = np.where(np.isnan(pra_cost), 1.0, pra_cost).astype(np.float32, copy=False)

    if slope.shape != pra_cost.shape:
        raise ValueError(f"slope and testing PRA/runout rasters must have the same shape for {area_id}")

    finite = np.isfinite(slope) & np.isfinite(pra_cost)
    return slope[finite].astype(np.float32, copy=False), pra_cost[finite].astype(np.float32, copy=False)


def _slope_pra_series(
    slope: np.ndarray,
    pra_cost: np.ndarray,
    *,
    max_slope: float = 60.0,
    bin_width: float = 1.0,
) -> dict[str, np.ndarray]:
    bin_edges = np.arange(0.0, max_slope + bin_width, bin_width, dtype=np.float32)
    centers, pra_median, pra_p10, pra_p90 = _binned_pra_by_slope(
        slope,
        pra_cost,
        bin_edges=bin_edges,
    )

    slope_curve = _slope_cost_curve(centers)
    mean = (slope_curve + pra_median) / 2.0
    finite_mean = np.isfinite(mean)
    if np.any(finite_mean):
        finite_idx = np.flatnonzero(finite_mean)
        peak_idx = int(finite_idx[np.nanargmax(mean[finite_mean])])
        peak_slope = float(centers[peak_idx])
        peak_mean = float(mean[peak_idx])
    else:
        peak_slope = np.nan
        peak_mean = np.nan

    return {
        "centers": centers,
        "slope_curve": slope_curve,
        "pra_median": pra_median,
        "pra_p10": pra_p10,
        "pra_p90": pra_p90,
        "mean": mean,
        "peak_slope": peak_slope,
        "peak_mean": peak_mean,
    }


def _plot_series(series: dict[str, np.ndarray], *, title: str, out_path: Path, max_slope: float) -> Path:
    threshold = float(config.TRANSFORM_PARAMS[f"slope_{config.SLOPE_TRANSFORM}"]["threshold"])

    centers = series["centers"]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(centers, series["slope_curve"], color="#367E98", linewidth=2.4, label="Slope cost function")
    ax.plot(centers, series["pra_median"], color="#7A5DB8", linewidth=2.2, label="PRA/runout cost, median by slope")
    ax.fill_between(
        centers,
        series["pra_p10"],
        series["pra_p90"],
        color="#7A5DB8",
        alpha=0.16,
        label="PRA/runout p10-p90",
    )
    ax.plot(centers, series["mean"], color="#EE7B04", linewidth=2.3, label="Mean: slope cost + PRA/runout cost")

    peak_slope = float(series["peak_slope"])
    peak_mean = float(series["peak_mean"])
    if np.isfinite(peak_slope) and np.isfinite(peak_mean):
        ax.axvline(peak_slope, color="#EE7B04", linestyle=":", linewidth=1.6, alpha=0.85)
        ax.scatter(
            [peak_slope],
            [peak_mean],
            color="#EE7B04",
            edgecolor="black",
            linewidth=0.8,
            s=52,
            zorder=5,
        )
        ax.annotate(
            f"Mean peak\ncandidate barrier start\n{peak_slope:.1f} deg, {peak_mean:.1f}",
            xy=(peak_slope, peak_mean),
            xytext=(peak_slope + 4.0, min(peak_mean + 13.0, 96.0)),
            arrowprops={"arrowstyle": "->", "color": "#EE7B04", "linewidth": 1.2},
            fontsize=11,
            color="#3a2a14",
        )

    ax.axvline(threshold, color="black", linestyle="--", linewidth=1.2, alpha=0.65)
    ax.text(threshold + 0.8, 5, f"{threshold:.0f} deg slope threshold", fontsize=11)

    ax.set_title(title)
    ax.set_xlabel("Slope (degrees)")
    ax.set_ylabel("Cost value")
    ax.set_xlim(0, max_slope)
    ax.set_ylim(config.MIN_COST - 2, 105)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=True)

    fig.savefig(out_path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

    if np.isfinite(peak_slope) and np.isfinite(peak_mean):
        print(f"Mean peak for '{title}': {peak_slope:.1f} deg, {peak_mean:.2f}")
    print(f"Slope/PRA relationship plot written to {out_path}")
    return out_path


def plot_steep_barrier_function(*, max_slope: float = 90.0) -> Path:
    params = config.STEEP_SLOPE_BARRIER_PARAMS
    start_deg = float(params["start_deg"])
    full_deg = float(params["full_deg"])
    barrier_value = float(params["barrier_value"])
    power = float(params["power"])

    slope = np.linspace(0.0, max_slope, 900, dtype=np.float32)
    barrier = _steep_barrier_curve(slope)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(
        slope,
        barrier,
        color="#B33A3A",
        linewidth=2.5,
        label=f"Steep-slope barrier, power={power:g}",
    )
    ax.axvline(start_deg, color="#EE7B04", linestyle=":", linewidth=1.6, alpha=0.85)
    ax.axvline(full_deg, color="black", linestyle="--", linewidth=1.4, alpha=0.7)
    ax.text(start_deg + 0.35, barrier_value * 0.08, f"start {start_deg:.1f} deg", fontsize=11)
    ax.text(full_deg + 0.35, barrier_value * 0.88, f"full {full_deg:.1f} deg", fontsize=11)

    ax.set_title("Testing Steep-Slope Barrier Function")
    ax.set_xlabel("Slope (degrees)")
    ax.set_ylabel("Barrier cost")
    ax.set_xlim(0, max_slope)
    ax.set_ylim(config.MIN_COST - 10, barrier_value * 1.05)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=True)

    out_path = FIG_DIR / "steep_slope_barrier_function.pdf"
    fig.savefig(out_path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

    print(f"Steep-slope barrier function plot written to {out_path}")
    return out_path


def _plot_barrier_on_mean(
    series: dict[str, np.ndarray],
    *,
    title: str,
    out_path: Path,
    max_slope: float,
) -> Path:
    params = config.STEEP_SLOPE_BARRIER_PARAMS
    start_deg = float(params["start_deg"])
    full_deg = float(params["full_deg"])
    barrier_value = float(params["barrier_value"])

    centers = series["centers"]
    mean = series["mean"]
    barrier = _steep_barrier_curve(centers)
    mean_for_max = np.where(np.isfinite(mean), mean, config.MIN_COST).astype(np.float32, copy=False)
    constrained = np.maximum(mean_for_max, barrier)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(centers, mean, color="#EE7B04", linewidth=2.3, label="Mean: slope cost + PRA/runout cost")
    ax.plot(centers, barrier, color="#B33A3A", linewidth=2.3, label="Steep-slope barrier")
    ax.plot(
        centers,
        constrained,
        color="#1F6F5B",
        linewidth=2.6,
        linestyle="--",
        label="Max(mean, barrier)",
    )

    peak_slope = float(series["peak_slope"])
    peak_mean = float(series["peak_mean"])
    if np.isfinite(peak_slope) and np.isfinite(peak_mean):
        ax.axvline(peak_slope, color="#EE7B04", linestyle=":", linewidth=1.5, alpha=0.85)
        ax.scatter(
            [peak_slope],
            [peak_mean],
            color="#EE7B04",
            edgecolor="black",
            linewidth=0.8,
            s=52,
            zorder=5,
        )
        ax.annotate(
            f"mean peak\n{peak_slope:.1f} deg",
            xy=(peak_slope, peak_mean),
            xytext=(peak_slope - 14.0, peak_mean + 180.0),
            arrowprops={"arrowstyle": "->", "color": "#EE7B04", "linewidth": 1.2},
            fontsize=11,
            color="#3a2a14",
        )

    ax.axvline(start_deg, color="#B33A3A", linestyle=":", linewidth=1.5, alpha=0.85)
    ax.axvline(full_deg, color="black", linestyle="--", linewidth=1.3, alpha=0.7)
    ax.text(start_deg + 0.35, barrier_value * 0.18, f"barrier start {start_deg:.1f} deg", fontsize=11)
    ax.text(full_deg + 0.35, barrier_value * 0.88, f"full {full_deg:.1f} deg", fontsize=11)

    ax.set_title(title)
    ax.set_xlabel("Slope (degrees)")
    ax.set_ylabel("Cost value")
    ax.set_xlim(0, max_slope)
    ax.set_ylim(config.MIN_COST - 5, 200)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=True)

    fig.savefig(out_path, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

    print(f"Mean/barrier max plot written to {out_path}")
    return out_path


def plot_slope_pra_relationship(
    area_id: str,
    *,
    experiment: str = config.DEFAULT_EXPERIMENT,
    rebuild_pra: bool = False,
    max_slope: float = 90.0,
    bin_width: float = 1.0,
) -> Path:
    slope, pra_cost = _load_slope_and_pra_cost(
        area_id,
        experiment=experiment,
        rebuild_pra=rebuild_pra,
    )
    series = _slope_pra_series(
        slope,
        pra_cost,
        max_slope=max_slope,
        bin_width=bin_width,
    )
    return _plot_series(
        series,
        title=f"Slope Cost And PRA/Runout Cost By Slope: {area_id}",
        out_path=FIG_DIR / f"{area_id}_slope_pra_relationship.pdf",
        max_slope=max_slope,
    )


def plot_overall_slope_pra_relationship(
    area_ids: list[str],
    *,
    experiment: str = config.DEFAULT_EXPERIMENT,
    rebuild_pra: bool = False,
    max_slope: float = 90.0,
    bin_width: float = 1.0,
) -> Path:
    slope_parts = []
    pra_parts = []
    for area_id in area_ids:
        slope, pra_cost = _load_slope_and_pra_cost(
            area_id,
            experiment=experiment,
            rebuild_pra=rebuild_pra,
        )
        slope_parts.append(slope)
        pra_parts.append(pra_cost)

    series = _slope_pra_series(
        np.concatenate(slope_parts),
        np.concatenate(pra_parts),
        max_slope=max_slope,
        bin_width=bin_width,
    )
    area_label = ", ".join(area_ids)
    return _plot_series(
        series,
        title=f"Overall Slope Cost And PRA/Runout Cost By Slope: {area_label}",
        out_path=FIG_DIR / "overall_slope_pra_relationship.pdf",
        max_slope=max_slope,
    )


def plot_slope_pra_mean_with_barrier(
    area_id: str,
    *,
    experiment: str = config.DEFAULT_EXPERIMENT,
    rebuild_pra: bool = False,
    max_slope: float = 90.0,
    bin_width: float = 1.0,
) -> Path:
    slope, pra_cost = _load_slope_and_pra_cost(
        area_id,
        experiment=experiment,
        rebuild_pra=rebuild_pra,
    )
    series = _slope_pra_series(
        slope,
        pra_cost,
        max_slope=max_slope,
        bin_width=bin_width,
    )
    return _plot_barrier_on_mean(
        series,
        title=f"Mean Cost With Steep-Slope Max Barrier: {area_id}",
        out_path=FIG_DIR / f"{area_id}_slope_pra_mean_with_barrier.pdf",
        max_slope=max_slope,
    )


def plot_overall_slope_pra_mean_with_barrier(
    area_ids: list[str],
    *,
    experiment: str = config.DEFAULT_EXPERIMENT,
    rebuild_pra: bool = False,
    max_slope: float = 90.0,
    bin_width: float = 1.0,
) -> Path:
    slope_parts = []
    pra_parts = []
    for area_id in area_ids:
        slope, pra_cost = _load_slope_and_pra_cost(
            area_id,
            experiment=experiment,
            rebuild_pra=rebuild_pra,
        )
        slope_parts.append(slope)
        pra_parts.append(pra_cost)

    series = _slope_pra_series(
        np.concatenate(slope_parts),
        np.concatenate(pra_parts),
        max_slope=max_slope,
        bin_width=bin_width,
    )
    area_label = ", ".join(area_ids)
    return _plot_barrier_on_mean(
        series,
        title=f"Overall Mean Cost With Steep-Slope Max Barrier: {area_label}",
        out_path=FIG_DIR / "overall_slope_pra_mean_with_barrier.pdf",
        max_slope=max_slope,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Visualize how testing slope cost and testing PRA/runout cost relate "
            "when binned by slope angle."
        )
    )
    parser.add_argument(
        "areas",
        nargs="*",
        help=(
            "Area IDs, e.g. isfjorden_01. If omitted, the default testing "
            "areas from config.py are used."
        ),
    )
    parser.add_argument(
        "--experiment",
        default=config.DEFAULT_EXPERIMENT,
        help=f"Name under data/testing/. Default: {config.DEFAULT_EXPERIMENT}",
    )
    parser.add_argument(
        "--rebuild-pra",
        action="store_true",
        help="Rebuild the testing PRA/runout layer before plotting.",
    )
    parser.add_argument(
        "--max-slope",
        type=float,
        default=90.0,
        help="Maximum slope shown on the x-axis. Default: 90.",
    )
    parser.add_argument(
        "--bin-width",
        type=float,
        default=1.0,
        help="Slope bin width in degrees. Default: 1.",
    )
    parser.add_argument(
        "--no-overall",
        action="store_true",
        help="Skip the pooled overall figure.",
    )
    parser.add_argument(
        "--no-barrier-plots",
        action="store_true",
        help="Skip the steep-slope barrier diagnostic plots.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    area_ids = list(args.areas) if args.areas else list(config.DEFAULT_TEST_AREAS)

    for area_id in area_ids:
        plot_slope_pra_relationship(
            area_id,
            experiment=args.experiment,
            rebuild_pra=bool(args.rebuild_pra),
            max_slope=float(args.max_slope),
            bin_width=float(args.bin_width),
        )
        if not bool(args.no_barrier_plots):
            plot_slope_pra_mean_with_barrier(
                area_id,
                experiment=args.experiment,
                rebuild_pra=bool(args.rebuild_pra),
                max_slope=float(args.max_slope),
                bin_width=float(args.bin_width),
            )

    if len(area_ids) > 1 and not bool(args.no_overall):
        plot_overall_slope_pra_relationship(
            area_ids,
            experiment=args.experiment,
            rebuild_pra=bool(args.rebuild_pra),
            max_slope=float(args.max_slope),
            bin_width=float(args.bin_width),
        )
        if not bool(args.no_barrier_plots):
            plot_overall_slope_pra_mean_with_barrier(
                area_ids,
                experiment=args.experiment,
                rebuild_pra=bool(args.rebuild_pra),
                max_slope=float(args.max_slope),
                bin_width=float(args.bin_width),
            )

    if not bool(args.no_barrier_plots):
        plot_steep_barrier_function(max_slope=float(args.max_slope))


if __name__ == "__main__":
    main()
