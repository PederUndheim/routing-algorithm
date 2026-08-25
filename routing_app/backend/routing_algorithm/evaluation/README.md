# Routing Evaluation

This package evaluates generated ski-touring routes against reference routes in
`data/areas/<area_id>/evaluation/evaluation_routes`.

The default pipeline uses each reference route's own first and last coordinate
as the routing request. Generated routes, corridors, metric tables, diagnostic
GeoJSON files, and plots are written below:

```text
data/areas/<area_id>/evaluation/evaluation_results/
```

`area_id` is the study-area folder, for example `jotunheimen_01`. The route
statistics also include `area_name`, derived by removing the trailing numeric
suffix, for example `jotunheimen`. Routing uses all study-area tiles that share
that `area_name`, so a route stored under `jotunheimen_01` can cross into
`jotunheimen_02`, `jotunheimen_03`, and so on.

## Main Metrics

The most useful thesis metrics are:

- Bidirectional buffer coverage at 25, 50, and 100 m.
- Mean, median, p90, p95, max, and RMSE point-to-line deviations in both
  directions.
- Symmetric point-to-line deviations, formed from both directions together.
- Fréchet and Hausdorff distances as stress metrics for large detours and
  outliers.
- Length ratio and endpoint errors as sanity checks.

The `quality_label` and `inspection_priority` columns are only triage labels.
They should be used to decide which routes need visual inspection, not as a
claim that one route is objectively correct.

## Commands

Run one area and generate routes from the reference endpoints:

```bash
python -m backend.scripts.run_evaluation --area isfjorden_01
```

Run every area that has files in `evaluation/evaluation_routes`:

```bash
python -m backend.scripts.run_evaluation
```

Recompute an area from scratch:

```bash
python -m backend.scripts.run_evaluation --area isfjorden_01 --force-reroute
```

Use `--force-reroute` after changing the routing extent or when evaluating
routes that may cross study-area tile borders. Otherwise the evaluator may reuse
older cached routes from `evaluation_results/routing`.

Compare routing with all thesis track modes:

```bash
python -m backend.scripts.run_evaluation --area isfjorden_01 --force-reroute --all-track-modes
```

Compare all thesis track modes for all areas:

```bash
python -m backend.scripts.run_evaluation --force-reroute --all-track-modes
```

Evaluate cached outputs without GRASS:

```bash
python -m backend.scripts.run_evaluation --area isfjorden_01 --no-reroute
```

Use existing `output/route` files as a fast exploratory fallback:

```bash
python -m backend.scripts.run_evaluation --area isfjorden_01 --no-reroute --use-area-route-fallback
```

## Corridor Evaluation

The corridor metrics sample the reference route against the generated corridor
rasters. The key question is:

```text
How much of the reference route lies inside the algorithm's near-optimal route corridor?
```

This is often fairer than strict line matching when several route choices are
reasonable.

## Terrain Class Hooks

ATES is read from reference route GeoJSON properties. The current route files
often store this as `kast`, so the evaluator reads `ates` when present and falls
back to `kast`. The route-level table exposes this as `reference_ates`, and the
report writer creates grouped summaries when the attribute exists:

```text
eval_metrics_simplified.csv
summary_overall.csv
summary_by_ates.csv
summary_by_area_name.csv
summary_by_area_name_and_ates.csv
summary_by_track_mode.csv
summary_by_track_mode_and_area_name.csv
summary_by_track_mode_and_ates.csv
track_mode_route_comparison.csv
track_mode_route_comparison_simplified.csv
```

When all areas are evaluated, aggregate copies are written to:

```text
data/evaluation/evaluation_results/
```

The most useful aggregate files are:

```text
all_areas_eval_metrics_simplified.csv
summary_overall.csv
summary_by_area_name.csv
summary_by_ates.csv
summary_by_track_mode_and_area_name.csv
summary_by_track_mode_and_ates.csv
track_mode_route_comparison_simplified.csv
visual_review_candidates.csv
```

The optional raster terrain hook is still available through `--terrain-raster`,
but it is not needed for the normal route-level ATES statistics.

`track_mode_route_comparison.csv` is written when at least two track modes are
present. It compares each route against `off` when available, with deltas for
the main deviation, buffer, corridor, and length metrics.
The `_simplified` version keeps only the columns that are most useful for quick
inspection and thesis tables.

The simplified and summary tables include the strict 25 m buffer coverage and
Hausdorff distance in addition to the broader 50/100 m coverage and p95
deviation metrics.

In baseline summary tables such as `summary_overall.csv`,
`summary_by_area_name.csv`, `summary_by_ates.csv`, and
`summary_by_area_name_and_ates.csv`, the rows are filtered to `off` when that
track mode is available. The `summary_track_mode` column records this. The
`summary_by_track_mode*` tables still include every evaluated track mode.

In all summary tables, `routes_total`, `routes_ok`, and `visual_review_count`
count unique reference tours. This means that evaluating several track modes
does not double or triple the tour count. The `route_mode_results_*` columns
show the number of actual route-mode result rows when that distinction matters.

Use `--all-track-modes` for the thesis comparison modes: `off`, `forest_only`,
`balanced`, and `strong`. Conservative, balanced, and explorative corridor
coverage are included in the detailed, simplified, summary, and track-mode
comparison CSVs.
