from __future__ import annotations

import csv
import os
from pathlib import Path


MPL_CONFIG_DIR = Path("/private/tmp/routing_algorithm_mpl")
XDG_CACHE_DIR = Path("/private/tmp/routing_algorithm_xdg_cache")
MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
XDG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(XDG_CACHE_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.ticker import PercentFormatter


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "evaluation" / "evaluation_results"
FIGURE_DIR = REPO_ROOT / "figures" / "evaluation"

TRACK_ORDER = ["off", "forest_only", "balanced", "strong"]
TRACK_LABELS = {
    "off": "Off",
    "forest_only": "Forest only",
    "balanced": "Balanced",
    "strong": "Strong",
}
AREA_ORDER = ["hemsedal", "isfjorden", "jotunheimen", "kattfjordeidet", "sogndal", "svolvaer"]
AREA_LABELS = {
    "hemsedal": "Hemsedal",
    "isfjorden": "Isfjorden",
    "jotunheimen": "Jotunheimen",
    "kattfjordeidet": "Kattfjordeidet",
    "sogndal": "Sogndal",
    "svolvaer": "Svolvær",
}
SIMILARITY_LABELS = {
    "excellent": "Very high similarity",
    "usable": "High similarity",
    "inspect": "Moderate similarity",
    "likely_bad_failure": "Low similarity",
}
SIMILARITY_ORDER = [
    "Very high similarity",
    "High similarity",
    "Moderate similarity",
    "Low similarity",
]
SIMILARITY_COLORS = {
    "Very high similarity": "#2a9d8f",
    "High similarity": "#8ab17d",
    "Moderate similarity": "#f4a261",
    "Low similarity": "#c44536",
}
MANUAL_COMPARISON_TRACK_ORDER = ["off", "balanced"]

TRACK_MODE_EFFECT_TEXT = {
    "title": 16,
    "axis_label": 16,
    "tick_label": 14,
    "legend": 13,
    "annotation": 14,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def style_axes(ax: plt.Axes) -> None:
    ax.grid(axis="y", color="#d7dde2", linewidth=0.8, alpha=0.75)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#8d99a6")
    ax.spines["bottom"].set_color("#8d99a6")
    ax.tick_params(colors="#243447")


def annotate_points(
    ax: plt.Axes,
    xs: list[int],
    ys: list[float],
    fmt: str,
    *,
    dx: float = 0.05,
    dy: float,
    fontsize: float = 8.5,
) -> None:
    for x, y in zip(xs, ys):
        ax.text(x + dx, y + dy, fmt.format(y), ha="center", va="bottom", fontsize=fontsize, color="#243447")


def plot_track_mode_effect() -> Path:
    rows = {row["track_influence_mode"]: row for row in read_csv(DATA_DIR / "summary_by_track_mode.csv")}
    labels = [TRACK_LABELS[mode] for mode in TRACK_ORDER]
    xs = list(range(len(TRACK_ORDER)))

    median_dev = [as_float(rows[mode], "median_deviation_median") for mode in TRACK_ORDER]
    p95_dev = [as_float(rows[mode], "p95_deviation_median") for mode in TRACK_ORDER]
    ref_100 = [as_float(rows[mode], "reference_100m_coverage_median") for mode in TRACK_ORDER]
    review = [as_float(rows[mode], "visual_review_pct") for mode in TRACK_ORDER]

    fig, (ax_dev, ax_pct) = plt.subplots(1, 2, figsize=(11.2, 4.9), constrained_layout=True)

    ax_dev.plot(xs, p95_dev, marker="s", linewidth=2.2, color="#d95f02", label="P95 symmetric deviation")
    ax_dev.plot(xs, median_dev, marker="o", linewidth=2.2, color="#255c99", label="Median symmetric deviation")
    annotate_points(
        ax_dev,
        xs,
        median_dev,
        "{:.1f}",
        dy=6.0,
        fontsize=TRACK_MODE_EFFECT_TEXT["annotation"],
    )
    annotate_points(
        ax_dev,
        xs,
        p95_dev,
        "{:.1f}",
        dy=6.0,
        fontsize=TRACK_MODE_EFFECT_TEXT["annotation"],
    )
    ax_dev.set_title("Deviation metrics", loc="left", fontsize=TRACK_MODE_EFFECT_TEXT["title"], fontweight="bold")
    ax_dev.set_xticks(xs, labels)
    ax_dev.set_ylabel("Distance (m)", fontsize=TRACK_MODE_EFFECT_TEXT["axis_label"])
    ax_dev.set_ylim(0, max(p95_dev) * 1.22)
    ax_dev.legend(
        frameon=False,
        fontsize=TRACK_MODE_EFFECT_TEXT["legend"],
        loc="lower left",
        bbox_to_anchor=(0, 0.335),
    )
    style_axes(ax_dev)
    ax_dev.tick_params(labelsize=TRACK_MODE_EFFECT_TEXT["tick_label"])

    ax_pct.plot(xs, ref_100, marker="o", linewidth=2.2, color="#1b9e77", label="Reference route in 100 m buffer")
    ax_pct.plot(xs, review, marker="s", linewidth=2.2, color="#b23a48", label="Weak agreement (moderate/low similarity)")
    annotate_points(
        ax_pct,
        xs,
        ref_100,
        "{:.1f}",
        dy=2,
        fontsize=TRACK_MODE_EFFECT_TEXT["annotation"],
    )
    annotate_points(
        ax_pct,
        xs,
        review,
        "{:.1f}",
        dy=2,
        fontsize=TRACK_MODE_EFFECT_TEXT["annotation"],
    )
    ax_pct.set_title(
        "Coverage and review metrics",
        loc="left",
        fontsize=TRACK_MODE_EFFECT_TEXT["title"],
        fontweight="bold",
    )
    ax_pct.set_xticks(xs, labels)
    ax_pct.set_ylabel("Routes (%)", fontsize=TRACK_MODE_EFFECT_TEXT["axis_label"])
    ax_pct.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    ax_pct.set_ylim(0, 108)
    ax_pct.legend(
        frameon=False,
        fontsize=TRACK_MODE_EFFECT_TEXT["legend"],
        loc="lower left",
    )
    style_axes(ax_pct)
    ax_pct.tick_params(labelsize=TRACK_MODE_EFFECT_TEXT["tick_label"])

    out = FIGURE_DIR / "track_mode_effect.pdf"
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_similarity_distribution_off() -> Path:
    rows = [
        row
        for row in read_csv(DATA_DIR / "all_areas_eval_metrics_simplified.csv")
        if row["track_influence_mode"] == "off" and row["status"] == "ok"
    ]
    xs = [0]
    bottoms = [0]

    fig, ax = plt.subplots(figsize=(7.6, 6.5), constrained_layout=False)
    fig.subplots_adjust(left=0.12, right=0.72, bottom=0.12, top=0.88)
    for label in SIMILARITY_ORDER:
        values = [sum(1 for row in rows if SIMILARITY_LABELS.get(row["quality_label"], row["quality_label"]) == label)]
        bars = ax.bar(
            xs,
            values,
            bottom=bottoms,
            label=label,
            color=SIMILARITY_COLORS[label],
            width=0.38,
        )
        for bar, value, bottom in zip(bars, values, bottoms):
            if value:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bottom + value / 2,
                    str(value),
                    ha="center",
                    va="center",
                    fontsize=TRACK_MODE_EFFECT_TEXT["annotation"],
                    color="white",
                )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]

    ax.set_xticks([])
    ax.set_ylabel("Number of routes", fontsize=TRACK_MODE_EFFECT_TEXT["axis_label"])
    ax.set_ylim(0, max(bottoms) + 4)
    ax.set_xlim(-0.5, 0.5)
    style_axes(ax)
    ax.tick_params(labelsize=TRACK_MODE_EFFECT_TEXT["tick_label"])
    ax.legend(
        frameon=False,
        fontsize=TRACK_MODE_EFFECT_TEXT["legend"],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        ncol=1,
    )

    out = FIGURE_DIR / "similarity_label_distribution_off.pdf"
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out



def main() -> None:
    outputs = [
        plot_track_mode_effect(),
        plot_similarity_distribution_off(),
    ]
    for output in outputs:
        print(output.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
