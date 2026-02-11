from pathlib import Path
from typing import Union, Dict, List
import geopandas as gpd

from backend import config
from backend.file_handler.area_context import load_area
from backend.routing_algorithm.routing.core import init_grass, run_routing_for_tour


SKITOURS = {
    "Kyrkjetaket": {"start": (132422.6, 6959926.2), "end": (136483.0, 6962328.0)},
    "Galtatind": {"start": (132422.6, 6959926.2), "end": (131960.2, 6962970.3)},
    "Loftskarstinden": {"start": (132422.6, 6959926.2), "end": (132350.27, 6963820.49)},
    "Sore Klauva": {"start": (132422.6, 6959926.2), "end": (135048.5, 6962996.58)},
    "Skarven": {"start": (132422.6, 6959926.2), "end": (133710.6, 6962969.1)},
    "Kjovskarstinden": {"start": (132422.6, 6959926.2), "end": (138549.8, 6962278.5)},
}


def _safe_slug(name: str) -> str:
    s = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name.lower())
    if s and s[0].isdigit():
        s = "_" + s
    return s


PathLike = Union[str, Path]


def export_wgs84_geojson(native_geojson_path: PathLike, out_basename: str, out_dir: Path) -> Path:
    native_geojson_path = Path(native_geojson_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_basename}.geojson"

    gdf = gpd.read_file(native_geojson_path)
    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    gdf_wgs84.to_file(out_path, driver="GeoJSON")
    return out_path


def run(area_id: str) -> None:
    # Load area context
    paths, inputs = load_area(area_id)

    if not paths.cost_surface.exists():
        raise FileNotFoundError(
            f"Cost surface not found at {paths.cost_surface}. "
            f"Build it first for area '{area_id}'."
        )

    print(f"\n=== Area: {area_id} ===")
    print("\n=== Initializing GRASS ===")
    init_grass()

    print("\n=== Routing tours ===")
    final_outputs: Dict[str, Dict] = {}

    for tour_name, pts in SKITOURS.items():
        print(f"\n--- Tour: {tour_name} ---")

        res = run_routing_for_tour(
            paths=paths,
            inputs=inputs,
            tour_name=tour_name,
            start_coords=pts["start"],
            end_coords=pts["end"],
            lambda_weight=config.ROUTING_SETTINGS["lambda_weight"],
            smooth_threshold=config.ROUTING_SETTINGS["smooth_threshold"],
            multi_routing=config.MULTIROUTING,
            multi_routing_params=config.MULTIROUTING_PARAMS,
        )

        slug = _safe_slug(tour_name)

        # Single-route WGS84 export
        if "path_geojson_native" in res:
            wgs84_geojson = export_wgs84_geojson(
                native_geojson_path=res["path_geojson_native"],
                out_basename=f"{slug}_wgs84",
                out_dir=paths.routes_geojson_wgs84,
            )
            res["path_geojson_wgs84"] = str(wgs84_geojson)

        # Multi-route WGS84 export
        if "multi_routing_routes_geojson" in res:
            out_dir = paths.multirouting_geojson_wgs84 / slug
            out_dir.mkdir(parents=True, exist_ok=True)

            wgs84_multi: List[str] = []
            for i, p in enumerate(res["multi_routing_routes_geojson"], start=1):
                out_p = export_wgs84_geojson(
                    native_geojson_path=p,
                    out_basename=f"{slug}_{i:02d}_wgs84",
                    out_dir=out_dir,
                )
                wgs84_multi.append(str(out_p))

            res["multi_routing_routes_geojson_wgs84"] = wgs84_multi

        final_outputs[tour_name] = res

    print("\n=== Done. Outputs ===")
    for tour_name, out in final_outputs.items():
        print(f"\n[{tour_name}]")
        for k, v in out.items():
            print(f"  {k}: {v}")


def main():
    from backend.scripts._cli import parse_area_arg
    run(parse_area_arg())


if __name__ == "__main__":
    main()
