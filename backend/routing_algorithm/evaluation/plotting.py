from __future__ import annotations
import os
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import LineString
from mpl_toolkits.axes_grid1 import make_axes_locatable
from .geometry import densify, sample_points

def plot_pair(out_png: str, auto_line: LineString, expert_line: LineString, sample_m: float):
    la_d = densify(auto_line, sample_m)
    samples = sample_points(la_d, sample_m)
    dists = np.array([expert_line.distance(p) for p in samples])

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(*expert_line.xy, label="Skiguide.app route", linewidth=2)
    ax.plot(*la_d.xy, label="Generated route", linestyle="--")

    sc = ax.scatter([p.x for p in samples], [p.y for p in samples], c=dists, s=9)
    ax.set_title("Route comparison")
    ax.set_aspect("equal")
    ax.legend()

    # Remove axis ticks and labels
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")

    # --- Create perfectly aligned colorbar ---
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="4%", pad=0.05)
    cbar = fig.colorbar(sc, cax=cax)
    cbar.set_label("Deviation between routes (m)")

    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    plt.savefig(out_png, dpi=160, bbox_inches="tight")
    plt.close(fig)
