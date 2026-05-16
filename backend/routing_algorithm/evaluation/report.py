from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


CORE_FIELD_ORDER = [
    "area_name",
    "area_id",
    "study_area_id",
    "route_id",
    "route_name",
    "track_influence_mode",
    "evaluation_run_id",
    "routing_area_ids",
    "status",
    "quality_label",
    "inspection_priority",
    "needs_visual_review",
    "reference_length_m",
    "generated_length_m",
    "length_ratio_generated_to_reference",
    "distance_symmetric_median_m",
    "distance_symmetric_p95_m",
    "distance_symmetric_max_m",
    "reference_in_generated_buffer_25m_pct",
    "reference_in_generated_buffer_50m_pct",
    "reference_in_generated_buffer_100m_pct",
    "generated_in_reference_buffer_25m_pct",
    "generated_in_reference_buffer_50m_pct",
    "generated_in_reference_buffer_100m_pct",
    "frechet_m",
    "hausdorff_m",
    "corridor_conservative_coverage_pct",
    "corridor_balanced_coverage_pct",
    "corridor_explorative_coverage_pct",
    "reference_ates",
    "reference_path",
    "generated_path",
    "comparison_geojson",
    "generated_to_reference_samples_geojson",
    "reference_to_generated_samples_geojson",
    "plot_path",
    "error",
]


SIMPLIFIED_ROUTE_FIELD_ORDER = [
    "area_name",
    "area_id",
    "study_area_id",
    "route_id",
    "route_name",
    "reference_ates",
    "track_influence_mode",
    "status",
    "quality_label",
    "inspection_priority",
    "needs_visual_review",
    "distance_symmetric_median_m",
    "distance_symmetric_p95_m",
    "hausdorff_m",
    "reference_in_generated_buffer_25m_pct",
    "reference_in_generated_buffer_50m_pct",
    "reference_in_generated_buffer_100m_pct",
    "generated_in_reference_buffer_25m_pct",
    "generated_in_reference_buffer_50m_pct",
    "generated_in_reference_buffer_100m_pct",
    "corridor_conservative_coverage_pct",
    "corridor_balanced_coverage_pct",
    "corridor_explorative_coverage_pct",
    "length_ratio_generated_to_reference",
    "reference_length_m",
    "generated_length_m",
    "generated_route_used_cache",
    "plot_path",
    "comparison_geojson",
    "generated_path",
    "error",
]


SIMPLIFIED_TRACK_COMPARISON_FIELD_ORDER = [
    "area_name",
    "area_id",
    "study_area_id",
    "route_id",
    "route_name",
    "reference_ates",
    "baseline_track_mode",
    "comparison_track_mode",
    "baseline_quality_label",
    "comparison_quality_label",
    "baseline_inspection_priority",
    "comparison_inspection_priority",
    "baseline_distance_symmetric_p95_m",
    "comparison_distance_symmetric_p95_m",
    "delta_distance_symmetric_p95_m",
    "baseline_distance_symmetric_median_m",
    "comparison_distance_symmetric_median_m",
    "delta_distance_symmetric_median_m",
    "baseline_hausdorff_m",
    "comparison_hausdorff_m",
    "delta_hausdorff_m",
    "baseline_reference_in_generated_buffer_25m_pct",
    "comparison_reference_in_generated_buffer_25m_pct",
    "delta_reference_in_generated_buffer_25m_pct",
    "baseline_reference_in_generated_buffer_50m_pct",
    "comparison_reference_in_generated_buffer_50m_pct",
    "delta_reference_in_generated_buffer_50m_pct",
    "baseline_reference_in_generated_buffer_100m_pct",
    "comparison_reference_in_generated_buffer_100m_pct",
    "delta_reference_in_generated_buffer_100m_pct",
    "baseline_generated_in_reference_buffer_25m_pct",
    "comparison_generated_in_reference_buffer_25m_pct",
    "delta_generated_in_reference_buffer_25m_pct",
    "baseline_generated_in_reference_buffer_50m_pct",
    "comparison_generated_in_reference_buffer_50m_pct",
    "delta_generated_in_reference_buffer_50m_pct",
    "baseline_generated_in_reference_buffer_100m_pct",
    "comparison_generated_in_reference_buffer_100m_pct",
    "delta_generated_in_reference_buffer_100m_pct",
    "baseline_corridor_conservative_coverage_pct",
    "comparison_corridor_conservative_coverage_pct",
    "delta_corridor_conservative_coverage_pct",
    "baseline_corridor_balanced_coverage_pct",
    "comparison_corridor_balanced_coverage_pct",
    "delta_corridor_balanced_coverage_pct",
    "baseline_corridor_explorative_coverage_pct",
    "comparison_corridor_explorative_coverage_pct",
    "delta_corridor_explorative_coverage_pct",
    "baseline_length_ratio_generated_to_reference",
    "comparison_length_ratio_generated_to_reference",
    "delta_length_ratio_generated_to_reference",
    "baseline_plot_path",
    "comparison_plot_path",
]


SUMMARY_VALUE_FIELD_ORDER = [
    "routes_total",
    "routes_ok",
    "route_mode_results_total",
    "route_mode_results_ok",
    "visual_review_count",
    "visual_review_pct",
    "visual_review_result_count",
    "visual_review_result_pct",
    "quality_counts_json",
    "quality_result_counts_json",
    "p95_deviation_mean",
    "p95_deviation_median",
    "median_deviation_mean",
    "median_deviation_median",
    "hausdorff_mean",
    "hausdorff_median",
    "reference_25m_coverage_mean",
    "reference_25m_coverage_median",
    "reference_50m_coverage_mean",
    "reference_50m_coverage_median",
    "reference_100m_coverage_mean",
    "reference_100m_coverage_median",
    "generated_25m_coverage_mean",
    "generated_25m_coverage_median",
    "generated_50m_coverage_mean",
    "generated_50m_coverage_median",
    "generated_100m_coverage_mean",
    "generated_100m_coverage_median",
    "conservative_corridor_coverage_mean",
    "conservative_corridor_coverage_median",
    "balanced_corridor_coverage_mean",
    "balanced_corridor_coverage_median",
    "explorative_corridor_coverage_mean",
    "explorative_corridor_coverage_median",
    "reference_length_mean",
    "reference_length_median",
    "generated_length_mean",
    "generated_length_median",
]


def _fieldnames(rows: Iterable[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    row_list = list(rows)
    for row in row_list:
        keys.update(row.keys())
    if not keys:
        return CORE_FIELD_ORDER
    ordered = [field for field in CORE_FIELD_ORDER if field in keys]
    ordered.extend(sorted(keys - set(ordered)))
    return ordered


def write_csv(path: str | Path, rows: list[dict[str, Any]], *, fieldnames: list[str] | None = None) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = _fieldnames(rows)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out


def _select_fields(rows: list[dict[str, Any]], fieldnames: list[str]) -> list[dict[str, Any]]:
    return [{field: row.get(field, "") for field in fieldnames} for row in rows]


def write_simplified_route_metrics_csv(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    return write_csv(
        path,
        _select_fields(rows, SIMPLIFIED_ROUTE_FIELD_ORDER),
        fieldnames=SIMPLIFIED_ROUTE_FIELD_ORDER,
    )


def write_json(path: str | Path, payload: Any) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row.get(key, "nan"))
        except (TypeError, ValueError):
            continue
        if value == value:
            values.append(value)
    return values


def _quality_counts_json(rows: list[dict[str, Any]]) -> str:
    counts = Counter(str(row.get("quality_label", "unknown")) for row in rows if row.get("status") == "ok")
    return json.dumps(dict(sorted(counts.items())), sort_keys=True)


def _route_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("area_id", "")), str(row.get("route_id", ""))


def _unique_route_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {_route_key(row) for row in rows}


def _baseline_summary_rows(rows: list[dict[str, Any]], baseline_mode: str = "off") -> tuple[list[dict[str, Any]], str]:
    available_modes = {
        str(row.get("track_influence_mode"))
        for row in rows
        if row.get("track_influence_mode") not in {None, ""}
    }
    if baseline_mode in available_modes:
        return [row for row in rows if str(row.get("track_influence_mode")) == baseline_mode], baseline_mode
    return rows, "all_available"


def _route_quality_counts_json(rows: list[dict[str, Any]]) -> str:
    severity = {
        "excellent": 0,
        "usable": 1,
        "inspect": 2,
        "likely_bad_failure": 3,
    }
    route_labels: dict[tuple[str, str], str] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        key = _route_key(row)
        label = str(row.get("quality_label", "unknown"))
        existing = route_labels.get(key)
        if existing is None or severity.get(label, -1) > severity.get(existing, -1):
            route_labels[key] = label
    counts = Counter(route_labels.values())
    return json.dumps(dict(sorted(counts.items())), sort_keys=True)


def _group_key(row: dict[str, Any], group_fields: tuple[str, ...]) -> tuple[str, ...]:
    values = []
    for field in group_fields:
        value = row.get(field)
        if value is None or value == "":
            value = "unknown"
        values.append(str(value))
    return tuple(values)


def summarize_groups(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_group_key(row, group_fields), []).append(row)

    summaries: list[dict[str, Any]] = []
    for key, group_rows in sorted(grouped.items()):
        ok_rows = [row for row in group_rows if row.get("status") == "ok"]
        visual_rows = [
            row
            for row in ok_rows
            if row.get("needs_visual_review") is True or str(row.get("inspection_priority")) in {"high", "severe"}
        ]
        route_keys = _unique_route_keys(group_rows)
        ok_route_keys = _unique_route_keys(ok_rows)
        visual_route_keys = _unique_route_keys(visual_rows)

        summary: dict[str, Any] = {
            field: value for field, value in zip(group_fields, key)
        }
        summary.update(
            {
                "routes_total": len(route_keys),
                "routes_ok": len(ok_route_keys),
                "route_mode_results_total": len(group_rows),
                "route_mode_results_ok": len(ok_rows),
                "visual_review_count": len(visual_route_keys),
                "visual_review_pct": 100.0 * len(visual_route_keys) / len(ok_route_keys) if ok_route_keys else "",
                "visual_review_result_count": len(visual_rows),
                "visual_review_result_pct": 100.0 * len(visual_rows) / len(ok_rows) if ok_rows else "",
                "quality_counts_json": _route_quality_counts_json(ok_rows),
                "quality_result_counts_json": _quality_counts_json(ok_rows),
            }
        )

        for source_key, out_prefix in [
            ("distance_symmetric_p95_m", "p95_deviation"),
            ("distance_symmetric_median_m", "median_deviation"),
            ("hausdorff_m", "hausdorff"),
            ("reference_in_generated_buffer_25m_pct", "reference_25m_coverage"),
            ("reference_in_generated_buffer_50m_pct", "reference_50m_coverage"),
            ("reference_in_generated_buffer_100m_pct", "reference_100m_coverage"),
            ("generated_in_reference_buffer_25m_pct", "generated_25m_coverage"),
            ("generated_in_reference_buffer_50m_pct", "generated_50m_coverage"),
            ("generated_in_reference_buffer_100m_pct", "generated_100m_coverage"),
            ("corridor_conservative_coverage_pct", "conservative_corridor_coverage"),
            ("corridor_balanced_coverage_pct", "balanced_corridor_coverage"),
            ("corridor_explorative_coverage_pct", "explorative_corridor_coverage"),
            ("generated_length_m", "generated_length"),
            ("reference_length_m", "reference_length"),
        ]:
            values = _numeric_values(ok_rows, source_key)
            if values:
                summary[f"{out_prefix}_mean"] = mean(values)
                summary[f"{out_prefix}_median"] = median(values)
            else:
                summary[f"{out_prefix}_mean"] = ""
                summary[f"{out_prefix}_median"] = ""

        summaries.append(summary)
    return summaries


def write_group_summary_csv(
    path: str | Path,
    rows: list[dict[str, Any]],
    group_fields: tuple[str, ...],
    *,
    extra_columns: dict[str, Any] | None = None,
) -> Path:
    summary_rows = summarize_groups(rows, group_fields)
    if extra_columns:
        for row in summary_rows:
            row.update(extra_columns)
    metadata_fields = list(extra_columns.keys()) if extra_columns else []
    fieldnames = list(group_fields) + metadata_fields + SUMMARY_VALUE_FIELD_ORDER
    extra_keys: set[str] = set()
    for row in summary_rows:
        extra_keys.update(row.keys())
    extra_fields = sorted(extra_keys - set(fieldnames))
    return write_csv(path, summary_rows, fieldnames=fieldnames + extra_fields)


TRACK_MODE_COMPARISON_METRICS = [
    "distance_symmetric_median_m",
    "distance_symmetric_p95_m",
    "hausdorff_m",
    "reference_in_generated_buffer_25m_pct",
    "reference_in_generated_buffer_50m_pct",
    "reference_in_generated_buffer_100m_pct",
    "generated_in_reference_buffer_25m_pct",
    "generated_in_reference_buffer_50m_pct",
    "generated_in_reference_buffer_100m_pct",
    "corridor_conservative_coverage_pct",
    "corridor_balanced_coverage_pct",
    "corridor_explorative_coverage_pct",
    "length_ratio_generated_to_reference",
    "frechet_m",
]


TRACK_MODE_COMPARISON_FIELD_ORDER = [
    "area_name",
    "area_id",
    "study_area_id",
    "route_id",
    "route_name",
    "reference_ates",
    "baseline_track_mode",
    "comparison_track_mode",
    "baseline_quality_label",
    "comparison_quality_label",
    "baseline_inspection_priority",
    "comparison_inspection_priority",
    "baseline_plot_path",
    "comparison_plot_path",
    "baseline_generated_path",
    "comparison_generated_path",
]
for _metric in TRACK_MODE_COMPARISON_METRICS:
    TRACK_MODE_COMPARISON_FIELD_ORDER.extend(
        [
            f"baseline_{_metric}",
            f"comparison_{_metric}",
            f"delta_{_metric}",
        ]
    )


def _track_mode_sort_key(mode: str) -> tuple[int, str]:
    preferred_order = {"off": 0, "forest_only": 1, "balanced": 2, "strong": 3}
    return preferred_order.get(mode, 99), mode


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def compare_track_modes(rows: list[dict[str, Any]], *, baseline_mode: str = "off") -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        mode = row.get("track_influence_mode")
        if mode in {None, ""}:
            continue
        key = (
            str(row.get("area_id", "")),
            str(row.get("route_id", "")),
            str(row.get("reference_ates", "")),
        )
        grouped.setdefault(key, {})[str(mode)] = row

    comparison_rows: list[dict[str, Any]] = []
    for _, mode_rows in sorted(grouped.items()):
        if len(mode_rows) < 2:
            continue

        modes = sorted(mode_rows, key=_track_mode_sort_key)
        baseline = baseline_mode if baseline_mode in mode_rows else modes[0]
        baseline_row = mode_rows[baseline]

        for mode in modes:
            if mode == baseline:
                continue
            compare_row = mode_rows[mode]
            out: dict[str, Any] = {
                "area_name": compare_row.get("area_name"),
                "area_id": compare_row.get("area_id"),
                "study_area_id": compare_row.get("study_area_id"),
                "route_id": compare_row.get("route_id"),
                "route_name": compare_row.get("route_name"),
                "reference_ates": compare_row.get("reference_ates"),
                "baseline_track_mode": baseline,
                "comparison_track_mode": mode,
                "baseline_quality_label": baseline_row.get("quality_label"),
                "comparison_quality_label": compare_row.get("quality_label"),
                "baseline_inspection_priority": baseline_row.get("inspection_priority"),
                "comparison_inspection_priority": compare_row.get("inspection_priority"),
                "baseline_plot_path": baseline_row.get("plot_path", ""),
                "comparison_plot_path": compare_row.get("plot_path", ""),
                "baseline_generated_path": baseline_row.get("generated_path", ""),
                "comparison_generated_path": compare_row.get("generated_path", ""),
            }

            for metric in TRACK_MODE_COMPARISON_METRICS:
                before = _float_or_none(baseline_row.get(metric))
                after = _float_or_none(compare_row.get(metric))
                out[f"baseline_{metric}"] = "" if before is None else before
                out[f"comparison_{metric}"] = "" if after is None else after
                out[f"delta_{metric}"] = "" if before is None or after is None else after - before

            comparison_rows.append(out)

    return comparison_rows


def write_track_mode_comparison_csv(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    comparison_rows = compare_track_modes(rows)
    return write_csv(path, comparison_rows, fieldnames=TRACK_MODE_COMPARISON_FIELD_ORDER)


def write_simplified_track_mode_comparison_csv(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    comparison_rows = compare_track_modes(rows)
    return write_csv(
        path,
        _select_fields(comparison_rows, SIMPLIFIED_TRACK_COMPARISON_FIELD_ORDER),
        fieldnames=SIMPLIFIED_TRACK_COMPARISON_FIELD_ORDER,
    )


def remove_legacy_kast_summaries(results_dir: str | Path) -> None:
    out_dir = Path(results_dir)
    for filename in [
        "summary_by_kast.csv",
        "summary_by_area_name_and_kast.csv",
        "summary_by_track_mode_and_kast.csv",
    ]:
        path = out_dir / filename
        if path.exists():
            path.unlink()


def write_standard_group_summaries(results_dir: str | Path, rows: list[dict[str, Any]]) -> list[Path]:
    out_dir = Path(results_dir)
    remove_legacy_kast_summaries(out_dir)
    written: list[Path] = []
    baseline_rows, baseline_label = _baseline_summary_rows(rows)
    baseline_meta = {"summary_track_mode": baseline_label}

    written.append(write_group_summary_csv(out_dir / "summary_overall.csv", baseline_rows, (), extra_columns=baseline_meta))
    if any(row.get("area_name") not in {None, ""} for row in baseline_rows):
        written.append(
            write_group_summary_csv(
                out_dir / "summary_by_area_name.csv",
                baseline_rows,
                ("area_name",),
                extra_columns=baseline_meta,
            )
        )
        if any(row.get("reference_ates") not in {None, ""} for row in baseline_rows):
            written.append(
                write_group_summary_csv(
                    out_dir / "summary_by_area_name_and_ates.csv",
                    baseline_rows,
                    ("area_name", "reference_ates"),
                    extra_columns=baseline_meta,
                )
            )
    if any(row.get("reference_ates") not in {None, ""} for row in baseline_rows):
        written.append(
            write_group_summary_csv(
                out_dir / "summary_by_ates.csv",
                baseline_rows,
                ("reference_ates",),
                extra_columns=baseline_meta,
            )
        )
    if any(row.get("track_influence_mode") not in {None, ""} for row in rows):
        written.append(write_group_summary_csv(out_dir / "summary_by_track_mode.csv", rows, ("track_influence_mode",)))
        if any(row.get("area_name") not in {None, ""} for row in rows):
            written.append(
                write_group_summary_csv(
                    out_dir / "summary_by_track_mode_and_area_name.csv",
                    rows,
                    ("track_influence_mode", "area_name"),
                )
            )
        if any(row.get("reference_ates") not in {None, ""} for row in rows):
            written.append(
                write_group_summary_csv(
                    out_dir / "summary_by_track_mode_and_ates.csv",
                    rows,
                    ("track_influence_mode", "reference_ates"),
                )
            )
        written.append(write_track_mode_comparison_csv(out_dir / "track_mode_route_comparison.csv", rows))
        written.append(
            write_simplified_track_mode_comparison_csv(
                out_dir / "track_mode_route_comparison_simplified.csv",
                rows,
            )
        )
    return written


def write_markdown_summary(path: str | Path, rows: list[dict[str, Any]], *, title: str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    route_keys = _unique_route_keys(rows)
    ok_route_keys = _unique_route_keys(ok_rows)
    quality_counts = Counter(json.loads(_route_quality_counts_json(ok_rows)))
    quality_result_counts = Counter(str(row.get("quality_label", "unknown")) for row in ok_rows)
    priority_counts = Counter(str(row.get("inspection_priority", "unknown")) for row in ok_rows)

    p95_values = _numeric_values(ok_rows, "distance_symmetric_p95_m")
    hausdorff_values = _numeric_values(ok_rows, "hausdorff_m")
    ref25_values = _numeric_values(ok_rows, "reference_in_generated_buffer_25m_pct")
    ref100_values = _numeric_values(ok_rows, "reference_in_generated_buffer_100m_pct")
    conservative_corridor = _numeric_values(ok_rows, "corridor_conservative_coverage_pct")
    balanced_corridor = _numeric_values(ok_rows, "corridor_balanced_coverage_pct")
    explorative_corridor = _numeric_values(ok_rows, "corridor_explorative_coverage_pct")
    track_counts = Counter(str(row.get("track_influence_mode", "unknown")) for row in ok_rows)
    area_name_counts = Counter(str(row.get("area_name", "unknown")) for row in ok_rows)
    ates_counts = Counter(str(row.get("reference_ates", "unknown")) for row in ok_rows)

    lines = [
        f"# {title}",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Overview",
        "",
        f"- Reference tours evaluated: {len(ok_route_keys)}/{len(route_keys)}",
        f"- Route-mode result rows evaluated: {len(ok_rows)}/{len(rows)}",
        f"- Route-mode rows with errors or skipped routes: {len(rows) - len(ok_rows)}",
        f"- Quality labels, unique tours: {dict(sorted(quality_counts.items()))}",
        f"- Quality labels, route-mode rows: {dict(sorted(quality_result_counts.items()))}",
        f"- Inspection priorities: {dict(sorted(priority_counts.items()))}",
    ]
    if track_counts:
        lines.append(f"- Track modes: {dict(sorted(track_counts.items()))}")
    if area_name_counts and set(area_name_counts.keys()) != {"unknown"}:
        lines.append(f"- Area names: {dict(sorted(area_name_counts.items()))}")
    if ates_counts and set(ates_counts.keys()) != {"unknown"}:
        lines.append(f"- ATES classes: {dict(sorted(ates_counts.items()))}")
    if p95_values:
        lines.append(f"- Median symmetric p95 deviation: {median(p95_values):.1f} m")
    if hausdorff_values:
        lines.append(f"- Median Hausdorff distance: {median(hausdorff_values):.1f} m")
    if ref25_values:
        lines.append(f"- Median reference coverage inside 25 m generated buffer: {median(ref25_values):.1f}%")
    if ref100_values:
        lines.append(f"- Median reference coverage inside 100 m generated buffer: {median(ref100_values):.1f}%")
    if conservative_corridor:
        lines.append(f"- Median reference coverage inside conservative corridor: {median(conservative_corridor):.1f}%")
    if balanced_corridor:
        lines.append(f"- Median reference coverage inside balanced corridor: {median(balanced_corridor):.1f}%")
    if explorative_corridor:
        lines.append(f"- Median reference coverage inside explorative corridor: {median(explorative_corridor):.1f}%")

    flagged = [
        row
        for row in ok_rows
        if str(row.get("inspection_priority")) in {"high", "severe"} or row.get("needs_visual_review") is True
    ]
    lines.extend(["", "## Visual Review Candidates", ""])
    if not flagged:
        lines.append("- None")
    else:
        for row in sorted(flagged, key=lambda r: str(r.get("inspection_priority")), reverse=True):
            p95 = row.get("distance_symmetric_p95_m", "")
            ref100 = row.get("reference_in_generated_buffer_100m_pct", "")
            lines.append(
                f"- {row.get('area_id')}/{row.get('route_id')}: "
                f"{row.get('quality_label')} ({row.get('inspection_priority')}), "
                f"p95={float(p95):.1f} m, ref100={float(ref100):.1f}%"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Use symmetric point-to-line deviations and bidirectional buffer coverage as the main similarity metrics.",
            "- Use Fréchet and Hausdorff as stress metrics because they react strongly to route ordering and outliers.",
            "- Treat the quality label as inspection triage, not proof that a route is correct or incorrect.",
            "- Corridor coverage answers a different question: whether the reference route lies inside the algorithm's near-optimal corridor.",
        ]
    )

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
