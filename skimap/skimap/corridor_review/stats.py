"""Turning a finished round into numbers: which models won, which colours,
and whether config.EXPOSURE_CLASSES still draws its lines where the review
put them.

Everything here reads what a round already produced - verdicts in
review.json, exp_score in each model's routes.gpkg - and writes tables under
data/review/stats/. Nothing here changes a verdict or config.py: the
threshold recommendation is a number to look at and decide on by hand, the
same way EXPOSURE_CLASSES's own comment says to re-derive it after a change,
not something this should ever write back itself.

    python -m skimap.corridor_review stats

Files, all under data/review/stats/:

    model_usage.csv       how often each model won, count and share
    colour_usage.csv      how often each exposure class was the final call
    model_colour.csv      cross-tab: which colours each model's wins carry
    colour_shift.csv      cross-tab: classify()'s colour against the
                           reviewer's, so the diagonal is agreement and
                           everything off it is a class the reviewer moved
    exposure_thresholds.csv   per boundary, the current cutoff, the one that
                           misclassifies the fewest reviewed tours, and how
                           many tours sit wrong on each side of both
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from skimap import config, paths
from skimap.corridor_review import models as models_module, sources
from skimap.corridor_review.store import LADDER, Store

STATS = paths.DATA / "review" / "stats"


def _write_csv(path: Path, header: tuple[str, ...], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


# --- model and colour counts ----------------------------------------------


def model_usage(verdicts: dict[int, dict[str, Any]]) -> list[tuple[str, int, float]]:
    """(model, count, % of reviewed tours), most-picked first."""
    counts: dict[str, int] = {}
    for verdict in verdicts.values():
        counts[verdict["model"]] = counts.get(verdict["model"], 0) + 1
    total = len(verdicts)
    return sorted(
        ((name, n, (n / total * 100) if total else 0.0) for name, n in counts.items()),
        key=lambda row: -row[1],
    )


def colour_usage(verdicts: dict[int, dict[str, Any]]) -> list[tuple[str, int, float]]:
    """(colour, count, % of reviewed tours), in ladder order."""
    counts = {colour: 0 for colour in LADDER}
    for verdict in verdicts.values():
        colour = verdict.get("colour")
        if colour in counts:
            counts[colour] += 1
    total = len(verdicts)
    return [(colour, counts[colour], (counts[colour] / total * 100) if total else 0.0)
            for colour in LADDER]


def model_colour_crosstab(verdicts: dict[int, dict[str, Any]]
                           ) -> tuple[list[str], dict[str, dict[str, int]]]:
    """Which final colours each model's wins carry - the "connection" table.

    Rows are models, in descending win count; columns are LADDER. A model
    that wins mostly black tours and one that wins mostly green ones are
    doing different jobs even if their win counts match, and this is the
    only table that shows it.
    """
    grid: dict[str, dict[str, int]] = {}
    for verdict in verdicts.values():
        model = verdict["model"]
        colour = verdict.get("colour")
        row = grid.setdefault(model, {c: 0 for c in LADDER})
        if colour in row:
            row[colour] += 1
    order = sorted(grid, key=lambda m: -sum(grid[m].values()))
    return order, grid


def colour_shift_matrix(verdicts: dict[int, dict[str, Any]]
                         ) -> dict[str, dict[str, int]]:
    """computed -> final, both in LADDER. The diagonal is agreement.

    Off the diagonal is exactly the signal config.EXPOSURE_CLASSES's own
    docstring asks for: a row of tours the reviewer consistently pushed one
    way is evidence the boundary between those two colours is in the wrong
    place, which is what `exposure_thresholds` below goes and checks.
    """
    grid = {computed: {final: 0 for final in LADDER} for computed in LADDER}
    for verdict in verdicts.values():
        computed, final = verdict.get("colour_computed"), verdict.get("colour")
        if computed in grid and final in grid[computed]:
            grid[computed][final] += 1
    return grid


# --- exposure threshold recommendation ------------------------------------


def _winning_scores(verdicts: dict[int, dict[str, Any]], review_config
                     ) -> list[tuple[str, float]]:
    """(final colour, exp_score) for every verdict whose model is still
    configured and whose winning route carries a score.

    One routes.gpkg read per model, not per tour: a round is a few hundred
    verdicts over a handful of models, and `sources.model_rows` already reads
    the whole file, so caching it here is the difference between a few reads
    and a few hundred.
    """
    cache: dict[str, dict[int, dict[str, Any]]] = {}
    out = []
    for fid, verdict in verdicts.items():
        model = review_config.model(verdict["model"])
        if model is None:
            continue   # a model the config no longer names - nothing to score it against
        rows = cache.setdefault(model.name, sources.model_rows(model))
        row = rows.get(fid)
        if row is None or row.get("exp_score") is None:
            continue
        out.append((verdict["colour"], float(row["exp_score"])))
    return out


def _optimal_threshold(lower_scores: list[float], upper_scores: list[float],
                        current: float) -> tuple[float, int, int]:
    """The exp_score split between two adjacent classes with the fewest
    reviewed tours on the wrong side of it.

    Candidates are midpoints between consecutive distinct scores - a
    decision-stump split, not a score itself, so the recommendation never
    lands exactly on a tour's own value. Ties (a stretch of candidates that
    all misclassify the same number of tours - typically the whole gap
    between the two groups) are broken toward whichever candidate is
    closest to the current threshold, so a config already close to right
    does not get pushed for no reason.
    """
    values = sorted(set(lower_scores) | set(upper_scores))
    if not values:
        return current, 0, 0

    candidates = [values[0] - 1.0]
    candidates += [(a + b) / 2 for a, b in zip(values, values[1:])]
    candidates += [values[-1] + 1.0]

    best_key: Optional[tuple] = None
    best = (current, 0, 0)
    for t in candidates:
        wrong_lower = sum(1 for s in lower_scores if s >= t)   # lower class pushed up
        wrong_upper = sum(1 for s in upper_scores if s < t)    # upper class pushed down
        key = (wrong_lower + wrong_upper, abs(t - current))
        if best_key is None or key < best_key:
            best_key = key
            best = (t, wrong_lower, wrong_upper)
    return best


def exposure_thresholds(verdicts: dict[int, dict[str, Any]], review_config
                         ) -> list[dict[str, Any]]:
    """Per boundary: the current cutoff, the least-wrong one, and the count
    of reviewed tours sitting on the wrong side of each."""
    scored = _winning_scores(verdicts, review_config)
    by_colour: dict[str, list[float]] = {c: [] for c in LADDER}
    for colour, score in scored:
        if colour in by_colour:
            by_colour[colour].append(score)

    out = []
    for i in range(len(LADDER) - 1):
        lower, upper = LADDER[i], LADDER[i + 1]
        current = config.EXPOSURE_CLASSES[i + 1][0]
        lower_scores, upper_scores = by_colour[lower], by_colour[upper]

        recommended, wrong_lower_new, wrong_upper_new = _optimal_threshold(
            lower_scores, upper_scores, current)
        wrong_lower_now = sum(1 for s in lower_scores if s >= current)
        wrong_upper_now = sum(1 for s in upper_scores if s < current)

        out.append({
            "boundary": f"{lower}/{upper}",
            "current_threshold": current,
            "recommended_threshold": round(recommended, 2),
            "n_lower_reviewed": len(lower_scores),
            "n_upper_reviewed": len(upper_scores),
            "current_lower_over": wrong_lower_now,
            "current_upper_under": wrong_upper_now,
            "current_errors": wrong_lower_now + wrong_upper_now,
            "recommended_lower_over": wrong_lower_new,
            "recommended_upper_under": wrong_upper_new,
            "recommended_errors": wrong_lower_new + wrong_upper_new,
        })
    return out


# --- entry point -----------------------------------------------------------


def run(*, out_dir: Optional[Path] = None) -> Path:
    review_config = models_module.load()
    store = Store()
    names = {t["fid"]: t["name"] for t in sources.tour_order()}
    verdicts = store.current(names)
    out_dir = Path(out_dir) if out_dir else STATS

    if not verdicts:
        raise SystemExit("No verdicts to summarize yet.")

    print(f"round {store.round}: {len(verdicts)} reviewed tours\n")

    print("model usage:")
    usage = model_usage(verdicts)
    for name, n, pct in usage:
        print(f"  {name:16s} {n:4d}  {pct:5.1f}%")
    _write_csv(out_dir / "model_usage.csv", ("model", "count", "pct"), usage)

    print("\ncolour usage:")
    colours = colour_usage(verdicts)
    for colour, n, pct in colours:
        print(f"  {colour:8s} {n:4d}  {pct:5.1f}%")
    _write_csv(out_dir / "colour_usage.csv", ("colour", "count", "pct"), colours)

    print("\nmodel x colour (share of that model's own wins):")
    order, grid = model_colour_crosstab(verdicts)
    header = ("model",) + tuple(f"{c}_n" for c in LADDER) + tuple(f"{c}_pct" for c in LADDER) + ("total",)
    rows = []
    for model in order:
        row = grid[model]
        total = sum(row.values())
        pcts = tuple((row[c] / total * 100) if total else 0.0 for c in LADDER)
        print(f"  {model:16s} " + "  ".join(f"{c}:{row[c]:3d} ({p:4.1f}%)"
                                            for c, p in zip(LADDER, pcts)))
        rows.append((model,) + tuple(row[c] for c in LADDER) + pcts + (total,))
    _write_csv(out_dir / "model_colour.csv", header, rows)

    print("\ncomputed -> reviewed colour (diagonal = classify() agreed):")
    shift = colour_shift_matrix(verdicts)
    shift_header = ("computed",) + tuple(LADDER) + ("total",)
    shift_rows = []
    for computed in LADDER:
        row = shift[computed]
        total = sum(row.values())
        print(f"  {computed:8s} " + "  ".join(f"{c}:{row[c]:3d}" for c in LADDER)
              + f"   ({total} total)")
        shift_rows.append((computed,) + tuple(row[c] for c in LADDER) + (total,))
    _write_csv(out_dir / "colour_shift.csv", shift_header, shift_rows)

    print("\nexposure class boundaries - current vs. least-wrong against the review:")
    thresholds = exposure_thresholds(verdicts, review_config)
    threshold_header = tuple(thresholds[0].keys()) if thresholds else ()
    threshold_rows = [tuple(row.values()) for row in thresholds]
    for row in thresholds:
        print(f"  {row['boundary']:10s} current {row['current_threshold']:6.1f} "
              f"({row['current_errors']} wrong: {row['current_lower_over']} over / "
              f"{row['current_upper_under']} under)  ->  "
              f"recommended {row['recommended_threshold']:6.1f} "
              f"({row['recommended_errors']} wrong: {row['recommended_lower_over']} over / "
              f"{row['recommended_upper_under']} under)")
    _write_csv(out_dir / "exposure_thresholds.csv", threshold_header, threshold_rows)

    print(f"\n{out_dir}")
    return out_dir
