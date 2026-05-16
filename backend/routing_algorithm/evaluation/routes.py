from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
from shapely.geometry import LineString

from backend.file_handler.area_context import PROJECT_ROOT, load_area

from .config import DEFAULT_SETTINGS
from .geometry import endpoints, ensure_metric_crs, ensure_single_line


_SAFE_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def safe_slug(value: str) -> str:
    slug = _SAFE_SLUG_RE.sub("_", value.lower()).strip("_")
    return slug or "route"


def route_id_from_path(path: str | Path, provider_suffixes: Iterable[str] = DEFAULT_SETTINGS.provider_suffixes) -> str:
    stem = Path(path).stem.lower()
    for suffix in provider_suffixes:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return safe_slug(stem)


def area_id_from_path(path: str | Path) -> str | None:
    parts = Path(path).parts
    for i, part in enumerate(parts):
        if part == "areas" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def area_name_from_area_id(area_id: str) -> str:
    return re.sub(r"_\d+$", "", area_id)


def study_area_ids_for_area_name(area_name: str, project_root: Path = PROJECT_ROOT) -> list[str]:
    areas_root = project_root / "data" / "areas"
    if not areas_root.exists():
        return []
    return sorted(
        p.name
        for p in areas_root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and area_name_from_area_id(p.name) == area_name
    )


def routing_area_ids_for_study_area(area_id: str, project_root: Path = PROJECT_ROOT) -> list[str]:
    area_name = area_name_from_area_id(area_id)
    candidates = study_area_ids_for_area_name(area_name, project_root)
    return candidates or [area_id]


@dataclass(frozen=True)
class EvaluationRoute:
    area_id: str
    area_name: str
    route_id: str
    display_name: str
    source_path: Path
    metric_crs: str
    line: LineString
    source_crs: str | None
    properties: dict[str, Any]

    @property
    def start_xy(self) -> tuple[float, float]:
        return endpoints(self.line)[0]

    @property
    def end_xy(self) -> tuple[float, float]:
        return endpoints(self.line)[1]

    @property
    def length_m(self) -> float:
        return float(self.line.length)


def discover_evaluation_route_paths(area_id: str, project_root: Path = PROJECT_ROOT) -> list[Path]:
    paths, _ = load_area(area_id)
    route_dir = paths.evaluation_routes
    if not route_dir.exists():
        return []
    return sorted(p for p in route_dir.glob("*.geojson") if p.is_file())


def discover_areas_with_evaluation_routes(project_root: Path = PROJECT_ROOT) -> list[str]:
    areas_root = project_root / "data" / "areas"
    if not areas_root.exists():
        return []
    area_ids: list[str] = []
    for area_dir in sorted(p for p in areas_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        route_dir = area_dir / "evaluation" / "evaluation_routes"
        if any(route_dir.glob("*.geojson")):
            area_ids.append(area_dir.name)
    return area_ids


def _first_properties(gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    if gdf.empty:
        return {}
    row = gdf.iloc[0].drop(labels=["geometry"], errors="ignore")
    out: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        try:
            if value != value:
                continue
        except TypeError:
            pass
        out[str(key)] = value.item() if hasattr(value, "item") else value
    return out


def _display_name(route_id: str, properties: dict[str, Any]) -> str:
    for key in ("navn", "name", "title"):
        value = properties.get(key)
        if value:
            return str(value)
    return route_id.replace("_", " ").title()


def load_evaluation_route(
    path: str | Path,
    *,
    area_id: str | None = None,
    metric_crs: str = DEFAULT_SETTINGS.metric_crs,
    provider_suffixes: Iterable[str] = DEFAULT_SETTINGS.provider_suffixes,
) -> EvaluationRoute:
    source_path = Path(path)
    route_area_id = area_id or area_id_from_path(source_path)
    if route_area_id is None:
        raise ValueError(f"Could not infer area id from path: {source_path}")

    raw_gdf = ensure_metric_crs(gpd.read_file(source_path))
    source_crs = str(raw_gdf.crs) if raw_gdf.crs is not None else None
    properties = _first_properties(raw_gdf)
    metric_gdf = raw_gdf.to_crs(metric_crs)
    line = ensure_single_line(metric_gdf)
    route_id = route_id_from_path(source_path, provider_suffixes)

    return EvaluationRoute(
        area_id=route_area_id,
        area_name=area_name_from_area_id(route_area_id),
        route_id=route_id,
        display_name=_display_name(route_id, properties),
        source_path=source_path,
        metric_crs=metric_crs,
        line=line,
        source_crs=source_crs,
        properties=properties,
    )


def load_evaluation_routes(
    area_id: str,
    *,
    metric_crs: str = DEFAULT_SETTINGS.metric_crs,
    route_ids: set[str] | None = None,
    provider_suffixes: Iterable[str] = DEFAULT_SETTINGS.provider_suffixes,
) -> list[EvaluationRoute]:
    routes: list[EvaluationRoute] = []
    for path in discover_evaluation_route_paths(area_id):
        route_id = route_id_from_path(path, provider_suffixes)
        if route_ids is not None and route_id not in route_ids:
            continue
        routes.append(
            load_evaluation_route(
                path,
                area_id=area_id,
                metric_crs=metric_crs,
                provider_suffixes=provider_suffixes,
            )
        )
    return routes
