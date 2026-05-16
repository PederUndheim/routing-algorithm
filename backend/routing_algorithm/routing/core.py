from pathlib import Path
import subprocess
import os
import socket
from typing import Tuple, Dict, Any, Optional, Literal
from backend import config
from backend.file_handler.area_paths import AreaPaths

from backend.routing_algorithm.routing.grass_env import setup_grass_python_path, GRASS_DB, GRASS_LOCATION, GRASS_MAPSET
from backend.routing_algorithm.routing.multi_routing import run_multi_routing_for_tour

setup_grass_python_path()

import grass.script as gs
import grass.script.setup as gsetup


# Create a GRASS-safe layer name
def _safe_name(base: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in base)
    if out and out[0].isdigit():
        out = "_" + out
    return out

def _grass_base_names(area_id: str) -> tuple[str, str]:
    safe = _safe_name(area_id.lower())
    return f"dem__{safe}", f"cost__{safe}"

def ensure_base_rasters(paths: AreaPaths) -> tuple[str, str]:
    """
    Import DEM + cost surface into GRASS raster names unique per area.
    Returns (DEM_NAME, COST_NAME).
    Safe to call multiple times.
    """

    print("USING ensure_base_rasters(paths) NEW VERSION", paths.dem, paths.cost_surface)
    
    dem_name, cost_name = _grass_base_names(paths.area_id)

    existing = set(gs.list_strings(type="raster"))

    if dem_name not in existing:
        dem_path = paths.dem
        if not dem_path.exists():
            raise FileNotFoundError(f"Runtime DEM missing: {dem_path}")
        gs.run_command("r.in.gdal", input=str(dem_path), output=dem_name, overwrite=True)

    if cost_name not in existing:
        cost_path = paths.cost_surface
        if not cost_path.exists():
            raise FileNotFoundError(f"Runtime cost surface missing: {cost_path}")
        gs.run_command("r.in.gdal", input=str(cost_path), output=cost_name, overwrite=True)

    return dem_name, cost_name

# Initialize a GRASS session once per run
def init_grass():
    """
    Ensure GRASS DB + LOCATION exists, then start a GRASS session.
    Works on fresh Docker/Azure containers.
    """
    os.makedirs(GRASS_DB, exist_ok=True)

    location_path = os.path.join(GRASS_DB, GRASS_LOCATION)

    # If location is missing, create it with the correct projection.
    # Default is EPSG:25833 (UTM33N), but override via env GRASS_EPSG if needed.
    if not os.path.isdir(location_path):
        epsg = os.environ.get("GRASS_EPSG", "25833")
        print(f"GRASS location missing. Creating: {location_path} (EPSG:{epsg})")
        subprocess.check_call(["grass", "-c", f"EPSG:{epsg}", "-e", location_path])

    tmp_root = os.path.join(location_path, GRASS_MAPSET, ".tmp")
    os.makedirs(tmp_root, exist_ok=True)
    os.makedirs(os.path.join(tmp_root, socket.gethostname()), exist_ok=True)

    gsetup.init(GRASS_DB, GRASS_LOCATION, GRASS_MAPSET)
    print(f"GRASS initialized: db={GRASS_DB}, location={GRASS_LOCATION}, mapset={GRASS_MAPSET}")


# Import a single (x,y) point as a GRASS vector
def _import_points(name: str, coords: Tuple[float, float]) -> None:
    x, y = coords
    coords_str = f"{x},{y}\n"

    # Import as point with x in column 1 and y in column 2
    gs.write_command(
        "v.in.ascii",
        input="-",
        output=name,
        separator=",",
        format="point",
        x=1,
        y=2,
        overwrite=True,
        stdin=coords_str,
    )

    # Quick sanity check, should report points=1
    info = gs.read_command("v.info", map=name, flags="t").strip()
    print(info)
    print(f"Imported point {name} at ({x}, {y}).")


# Sample raster value at vector point
def _sample_raster_at_point(raster: str, vector_point: str) -> float:
    out = gs.read_command("r.what", map=raster, points=vector_point).strip()
    parts = out.split("|")
    if len(parts) < 4:
        raise RuntimeError(f"Unexpected r.what output: {out}")

    val = parts[-1].strip()
    if val in {"*", ""}:
        raise RuntimeError(
            f"Raster '{raster}' is NULL at point '{vector_point}'. "
            "Start and end may be disconnected, outside valid cost area, "
            f"or DEM/cost has NULL there. r.what='{out}'"
        )

    try:
        return float(val)
    except Exception:
        raise RuntimeError(f"Failed to parse value from r.what output: {out}")

OutputMode = Literal["area", "run"]

def run_routing_for_tour(
    paths: AreaPaths,
    inputs: Dict[str, Any],
    tour_name: str,
    start_coords: Tuple[float, float],
    end_coords: Tuple[float, float],
    *,
    lambda_weight: float,
    smooth_threshold: float,
    corridor_mode: Literal["conservative", "balanced", "explorative"] = "balanced",
    multi_routing: bool = False,
    cost_surface_override: Optional[str] = None,
    dem_override: Optional[str] = None,
    preserve_region: bool = False,
    output_mode: OutputMode = "area",
    run_id: Optional[str] = None,
    output_root: Optional[Path] = None,
    output_suffix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full GRASS routing for a single tour and export outputs.
    Returns a dict with output file paths.
    """
    slug_parts = [_safe_name(tour_name.lower())]
    if run_id:
        slug_parts.append(_safe_name(run_id.lower()))
    if output_suffix:
        slug_parts.append(_safe_name(output_suffix.lower()))
    slug = "_".join(part for part in slug_parts if part)
    start_vec = f"start_{slug}"
    end_vec = f"end_{slug}"

    cum_start = f"cum_start_{slug}"
    cum_end = f"cum_end_{slug}"
    sym_cum_start = f"sym_cum_start_{slug}"
    sym_cum_end = f"sym_cum_end_{slug}"
    direction_rast = f"dir_start_{slug}"
    corridor_rast = f"corridor_{slug}"
    optimal_path = f"path_{slug}"
    smooth_path = f"path_smooth_{slug}"

    if dem_override is not None and cost_surface_override is not None:
        dem_name = dem_override
        cost_name = cost_surface_override
    else:
        dem_name, cost_name = ensure_base_rasters(paths)


    if preserve_region:
        gs.run_command("g.region", align=dem_name, quiet=True)
    else:
        gs.run_command("g.region", raster=dem_name, flags="a")

    grass_memory_mb = int(config.ROUTING_SETTINGS.get("grass_memory_mb", 0) or 0)
    walk_kwargs = {"memory": grass_memory_mb} if grass_memory_mb > 0 else {}

    # Ensure output dirs
    if output_mode == "run":
        if not run_id:
            raise ValueError("run_id must be provided when output_mode is 'run'")
        if output_root is None:
            raise ValueError("output_root must be provided when output_mode is 'run'")

        output_root = Path(output_root).resolve()
        output_base = (output_root / "runs_output" / run_id).resolve()

        corridor_dir = output_base / "corridor"
        route_dir = output_base / "route"
    else:
        corridor_dir = paths.corridor
        route_dir = paths.route_dir

    corridor_dir.mkdir(parents=True, exist_ok=True)
    route_dir.mkdir(parents=True, exist_ok=True)

    if output_mode == "run":
        path_geojson = route_dir / (f"path_{output_suffix}.geojson" if output_suffix else "path.geojson")
    else:
        path_geojson = route_dir / f"{slug}_path.geojson"





    # 1) Import points
    print(f"[{tour_name}] Importing start/end points...")
    _import_points(start_vec, start_coords)
    _import_points(end_vec, end_coords)
    

    if multi_routing:
        print(f"[{tour_name}] Running multi-routing...")
        multi_routing_out = run_multi_routing_for_tour(
            paths=paths,
            slug=slug,
            tour_name=tour_name,
            start_vec=start_vec,
            end_vec=end_vec,
            direction_rast=direction_rast,
            lambda_weight=lambda_weight,
            smooth_threshold=smooth_threshold,
            dem_name=dem_name,
            cost_name=cost_name,
        )
        return {
            "multi_routing_heatmap_tif": str(multi_routing_out["heatmap_tif"]),
            "multi_routing_routes_geojson": [str(p) for p in multi_routing_out["routes_geojson"]],
            "multi_routing_routes_shp": [str(p) for p in multi_routing_out["routes_shp"]],
        }

    # 2) Cumulative costs (both directions) and direction raster from start
    print(f"[{tour_name}] Running r.walk (start -> all)...")
    gs.run_command(
        "r.walk",
        elevation=dem_name,
        friction=cost_name,
        start_points=start_vec,
        output=cum_start,
        outdir=direction_rast,
        lambda_=lambda_weight,
        **walk_kwargs,
        overwrite=True
    )

    print(f"[{tour_name}] Running r.walk (end -> all)...")
    gs.run_command(
        "r.walk",
        elevation=dem_name,
        friction=cost_name,
        start_points=end_vec,
        output=cum_end,
        lambda_=lambda_weight,
        **walk_kwargs,
        overwrite=True
    )

    # 3) Corridor
    # Use symmetric accumulated friction for corridor membership.
    # r.walk is directional and good for the route itself, but not for the
    # "near-optimal alternatives" corridor because start->x plus end->x is not
    # the same as start->x plus x->end.
    print(f"[{tour_name}] Computing corridor with r.cost...")

    gs.run_command(
        "r.cost",
        input=cost_name,
        start_points=start_vec,
        output=sym_cum_start,
        **walk_kwargs,
        overwrite=True,
    )

    gs.run_command(
        "r.cost",
        input=cost_name,
        start_points=end_vec,
        output=sym_cum_end,
        **walk_kwargs,
        overwrite=True,
    )

    # Sum corridor (optional, good for debugging)
    gs.mapcalc(f"{corridor_rast} = {sym_cum_start} + {sym_cum_end}", overwrite=True)

    # Optimal symmetric cost from start to end
    C_opt = _sample_raster_at_point(sym_cum_start, end_vec)

    # Extra cost (gap) relative to optimal symmetric path cost
    corridor_gap = f"corridor_gap_{slug}"
    gs.mapcalc(f"{corridor_gap} = ({sym_cum_start} + {sym_cum_end}) - {C_opt}", overwrite=True)

    selected_mode_key = corridor_mode.lower()
    if selected_mode_key not in config.CORRIDOR_MODE_PARAMS:
        raise ValueError(f"Unsupported corridor_mode: {corridor_mode}")

    # Clamp negatives and remove NULL influence
    corridor_gap_pos = f"corridor_gap_pos_{slug}"
    gs.mapcalc(
        f"{corridor_gap_pos} = if(isnull({sym_cum_start}) || isnull({sym_cum_end}), null(), if({corridor_gap} < 0, 0, {corridor_gap}))",
        overwrite=True
    )

    corridor_tifs: Dict[str, str] = {}



    # 4) Extract optimal path using r.path, then smooth
    print(f"[{tour_name}] Extracting optimal path with r.path...")
    gs.run_command(
        "r.path",
        input=direction_rast,      
        format="auto",             
        start_points=end_vec,      
        vector_path=optimal_path, 
        overwrite=True
    )
    

    print(f"[{tour_name}] Smoothing path with v.generalize (Douglas-Peucker)...")
    gs.run_command(
        "v.generalize",
        input=optimal_path,
        output=smooth_path,
        method="douglas",
        threshold=smooth_threshold,
        overwrite=True
    )

    # 5) Export corridor variants + path GeoJSON (native CRS)
    print(f"[{tour_name}] Exporting corridor variants and vector path...")
    for mode_name, corridor_params in config.CORRIDOR_MODE_PARAMS.items():
        slack = float(corridor_params["slack"])
        gamma = float(corridor_params["gamma"])
        max_gap = C_opt * slack

        corridor_score = f"corridor_score_{slug}_{mode_name}"
        gs.mapcalc(
            f"{corridor_score} = if({corridor_gap_pos} <= {max_gap}, 1 - ({corridor_gap_pos} / {max_gap}), null())",
            overwrite=True,
        )

        corridor_score_gamma = f"corridor_score_gamma_{slug}_{mode_name}"
        gs.mapcalc(
            f"{corridor_score_gamma} = pow({corridor_score}, {gamma})",
            overwrite=True,
        )

        corridor_f32 = f"{corridor_score_gamma}_f32"
        gs.mapcalc(f"{corridor_f32} = float({corridor_score_gamma})", overwrite=True)

        if output_mode == "run":
            if output_suffix:
                corridor_tif = corridor_dir / f"corridor_{mode_name}_{output_suffix}.tif"
            else:
                corridor_tif = corridor_dir / f"corridor_{mode_name}.tif"
        else:
            corridor_tif = corridor_dir / f"{slug}_{mode_name}_corridor.tif"

        gs.run_command(
            "r.out.gdal",
            input=corridor_f32,
            output=str(corridor_tif),
            format="GTiff",
            flags="c",
            type="Float32",
            nodata=-9999,
            overwrite=True,
        )
        corridor_tifs[mode_name] = str(corridor_tif)

    gs.run_command(
        "v.out.ogr",
        input=smooth_path,
        output=str(path_geojson),
        format="GeoJSON",
        overwrite=True
    )


    return {
        "corridor_tif": corridor_tifs[selected_mode_key],
        "corridor_tifs": corridor_tifs,
        "path_geojson_native": str(path_geojson)
    }
