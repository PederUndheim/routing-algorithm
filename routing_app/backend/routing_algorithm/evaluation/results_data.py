from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path
from typing import Any


RESULTS_DATA_FOLDERS = {
    "reference_route": "reference_routes",
    "generated_route_track_off": "generated_routes_track_off",
    "generated_route_track_balanced": "generated_routes_track_balanced",
    "balanced_corridor_track_off": "balanced_corridors_track_off",
}


def _clean_token(value: str) -> str:
    value = (
        value.strip()
        .replace("ø", "o")
        .replace("Ø", "O")
        .replace("æ", "ae")
        .replace("Æ", "Ae")
        .replace("å", "a")
        .replace("Å", "A")
    )
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _route_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("area_id", "")), str(row.get("route_id", ""))


def _tour_stem(row: dict[str, Any]) -> str:
    area_id, route_id = _route_key(row)
    return f"{_clean_token(area_id)}__{_clean_token(route_id)}"


def _relative(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _prepare_managed_folders(folders: dict[str, Path]) -> None:
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.iterdir():
            if path.is_file():
                path.unlink()


def export_results_data_bundle(
    rows: list[dict[str, Any]],
    *,
    project_root: str | Path,
    out_root: str | Path | None = None,
) -> dict[str, int] | None:
    """Copy thesis route/corridor artifacts into four easy-to-browse folders.

    The bundle contains one file per tour for reference routes, generated routes
    with track mode off, generated routes with track mode balanced, and balanced
    corridor rasters from the track-off run.
    """

    root = Path(project_root)
    destination_root = Path(out_root) if out_root is not None else root / "data" / "evaluation" / "results_data"
    folders = {key: destination_root / folder for key, folder in RESULTS_DATA_FOLDERS.items()}

    ok_rows = [row for row in rows if row.get("status") == "ok"]
    off_rows = sorted(
        [row for row in ok_rows if str(row.get("track_influence_mode")) == "off"],
        key=lambda row: _route_key(row),
    )
    balanced_rows = [row for row in ok_rows if str(row.get("track_influence_mode")) == "balanced"]

    if not off_rows or not balanced_rows:
        return None

    balanced_by_key = {_route_key(row): row for row in balanced_rows}
    missing_balanced = [key for key in map(_route_key, off_rows) if key not in balanced_by_key]
    if missing_balanced:
        sample = ", ".join(f"{area_id}/{route_id}" for area_id, route_id in missing_balanced[:5])
        raise ValueError(f"Missing balanced generated route rows for {len(missing_balanced)} track-off tours: {sample}")

    planned_copies: list[tuple[Path, Path]] = []
    manifest_rows: list[dict[str, str]] = []

    for off_row in off_rows:
        stem = _tour_stem(off_row)
        balanced_row = balanced_by_key[_route_key(off_row)]

        reference_dst = folders["reference_route"] / f"{stem}.geojson"
        off_route_dst = folders["generated_route_track_off"] / f"{stem}.geojson"
        balanced_route_dst = folders["generated_route_track_balanced"] / f"{stem}.geojson"
        corridor_dst = folders["balanced_corridor_track_off"] / f"{stem}.tif"

        source_reference = Path(str(off_row.get("reference_path", "")))
        source_off_route = Path(str(off_row.get("generated_path", "")))
        source_balanced_route = Path(str(balanced_row.get("generated_path", "")))
        source_corridor = Path(str(off_row.get("corridor_balanced_path", "")))

        planned_copies.extend(
            [
                (source_reference, reference_dst),
                (source_off_route, off_route_dst),
                (source_balanced_route, balanced_route_dst),
                (source_corridor, corridor_dst),
            ]
        )
        manifest_rows.append(
            {
                "area_id": str(off_row.get("area_id", "")),
                "route_id": str(off_row.get("route_id", "")),
                "route_name": str(off_row.get("route_name", "")),
                "reference_route": _relative(reference_dst, root),
                "generated_route_track_off": _relative(off_route_dst, root),
                "generated_route_track_balanced": _relative(balanced_route_dst, root),
                "balanced_corridor_track_off": _relative(corridor_dst, root),
                "source_reference_route": str(source_reference),
                "source_generated_route_track_off": str(source_off_route),
                "source_generated_route_track_balanced": str(source_balanced_route),
                "source_balanced_corridor_track_off": str(source_corridor),
            }
        )

    missing_sources = [str(source) for source, _ in planned_copies if not source.is_file()]
    if missing_sources:
        sample = "\n".join(missing_sources[:10])
        raise FileNotFoundError(f"Missing {len(missing_sources)} source artifact files for results_data export:\n{sample}")

    _prepare_managed_folders(folders)
    for source, destination in planned_copies:
        shutil.copy2(source, destination)

    manifest_path = destination_root / "manifest.csv"
    fieldnames = [
        "area_id",
        "route_id",
        "route_name",
        "reference_route",
        "generated_route_track_off",
        "generated_route_track_balanced",
        "balanced_corridor_track_off",
        "source_reference_route",
        "source_generated_route_track_off",
        "source_generated_route_track_balanced",
        "source_balanced_corridor_track_off",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    counts = {key: len([path for path in folder.iterdir() if path.is_file()]) for key, folder in folders.items()}
    counts["manifest"] = 1
    return counts
