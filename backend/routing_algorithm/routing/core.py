from pathlib import Path
import subprocess
from typing import Tuple, Dict, Any, Optional
from backend.file_handler.area_paths import AreaPaths

from backend.routing_algorithm.routing.grass_env import setup_grass_python_path, GRASS_DB, GRASS_LOCATION, GRASS_MAPSET
from backend.routing_algorithm.routing.multi_routing import run_multi_routing_for_tour

setup_grass_python_path()

import grass.script as gs
import grass.script.setup as gsetup


def _grass_base_names(area_id: str) -> tuple[str, str]:
    safe = _safe_name(area_id.lower())
    return f"dem__{safe}", f"cost__{safe}"

def ensure_base_rasters(area_id: str, dem_path: Path, cost_surface_path: Path) -> tuple[str, str]:
    """
    Import DEM + cost surface into GRASS raster names unique per area.
    Returns (DEM_NAME, COST_NAME).
    Safe to call multiple times.
    """
    dem_name, cost_name = _grass_base_names(area_id)

    existing = set(gs.list_strings(type="raster"))

    if dem_name not in existing:
        print(f"Importing DEM -> {dem_name}")
        gs.run_command("r.in.gdal", input=str(dem_path), output=dem_name, overwrite=True)
    else:
        print(f"DEM already present -> {dem_name}")

    if cost_name not in existing:
        print(f"Importing cost surface -> {cost_name}")
        gs.run_command("r.in.gdal", input=str(cost_surface_path), output=cost_name, overwrite=True)
    else:
        print(f"Cost surface already present -> {cost_name}")

    return dem_name, cost_name

# Initialize a GRASS session once per run
def init_grass():
    gsetup.init(GRASS_DB, GRASS_LOCATION, GRASS_MAPSET)
    print(f"GRASS initialized: location={GRASS_LOCATION}, mapset={GRASS_MAPSET}")


# Import a single (x,y) point as a GRASS vector
def _import_points(name: str, coords: Tuple[float, float]):
    x, y = coords
    coords_str = f"{x},{y}\n"
    cmd = ["v.in.ascii", "input=-", f"output={name}", "separator=,", "--overwrite"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    stdout_data, stderr_data = proc.communicate(input=coords_str)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to import points '{name}': {stderr_data}")
    if stdout_data:
        print(stdout_data.strip())
    print(f"Imported point {name} at ({x}, {y}).")


# Create a GRASS-safe layer name
def _safe_name(base: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in base)
    if out and out[0].isdigit():
        out = "_" + out
    return out

# Sample raster value at vector point
def _sample_raster_at_point(raster: str, vector_point: str) -> float:
    out = gs.read_command("r.what", map=raster, points=vector_point).strip()

    # expected: x|y|value
    parts = out.split("|")
    if len(parts) < 3:
        raise RuntimeError(f"Unexpected r.what output: {out}")

    try:
        value = float(parts[-1])
    except Exception:
        raise RuntimeError(f"Failed to parse value from r.what output: {out}")

    return value


def run_routing_for_tour(
    paths: AreaPaths,
    inputs: Dict[str, Any],
    tour_name: str,
    start_coords: Tuple[float, float],
    end_coords: Tuple[float, float],
    *,
    lambda_weight: float,
    smooth_threshold: float,
    multi_routing: bool = False,
    multi_routing_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run the full GRASS routing for a single tour and export outputs.
    Returns a dict with output file paths.
    """
    slug = _safe_name(tour_name.lower())
    start_vec = f"start_{slug}"
    end_vec = f"end_{slug}"

    cum_start = f"cum_start_{slug}"
    cum_end = f"cum_end_{slug}"
    direction_rast = f"dir_start_{slug}"
    corridor_rast = f"corridor_{slug}"
    optimal_path = f"path_{slug}"
    smooth_path = f"path_smooth_{slug}"

    dem_name, cost_name = ensure_base_rasters(
    area_id=paths.area_id,
    dem_path=inputs["dem"],
    cost_surface_path=paths.cost_surface,
)

    # Ensure output dirs
    corridor_dir = paths.corridor
    geojson_native_dir = paths.routes_geojson_native
    shp_dir = paths.routes_shp

    corridor_dir.mkdir(parents=True, exist_ok=True)
    geojson_native_dir.mkdir(parents=True, exist_ok=True)
    shp_dir.mkdir(parents=True, exist_ok=True)

    corridor_tif = corridor_dir / f"{slug}_corridor.tif"
    path_geojson = geojson_native_dir / f"{slug}_path.geojson"
    path_shp = shp_dir / f"{slug}_path.shp"


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
        overwrite=True
    )

    # 3) Corridor
    print(f"[{tour_name}] Computing corridor...")

    # Sum corridor (optional, good for debugging)
    gs.mapcalc(f"{corridor_rast} = {cum_start} + {cum_end}", overwrite=True)

    # Optimal cost from start to end
    C_opt = _sample_raster_at_point(cum_start, end_vec)

    # Extra cost (gap) relative to optimal path cost
    corridor_gap = f"corridor_gap_{slug}"
    gs.mapcalc(f"{corridor_gap} = ({cum_start} + {cum_end}) - {C_opt}", overwrite=True)

    # Tuning knobs
    SLACK = 0.03   # corridor width as fraction of C_opt (0.01 to 0.03 typical)
    GAMMA = 3.0    # contrast (2 to 6 typical). Higher makes center pop more.

    MAX_GAP = C_opt * SLACK

    # Clamp negatives and remove NULL influence
    corridor_gap_pos = f"corridor_gap_pos_{slug}"
    gs.mapcalc(
        f"{corridor_gap_pos} = if(isnull({cum_start}) || isnull({cum_end}), null(), if({corridor_gap} < 0, 0, {corridor_gap}))",
        overwrite=True
    )

    # Fix 1: linear corridor score (interpretable and not all 0.98)
    # 1 at optimal, 0 at MAX_GAP boundary
    corridor_score = f"corridor_score_{slug}"
    gs.mapcalc(
        f"{corridor_score} = if({corridor_gap_pos} <= {MAX_GAP}, 1 - ({corridor_gap_pos} / {MAX_GAP}), null())",
        overwrite=True
    )

    # Optional gamma contrast
    corridor_score_gamma = f"corridor_score_gamma_{slug}"
    gs.mapcalc(
        f"{corridor_score_gamma} = pow({corridor_score}, {GAMMA})",
        overwrite=True
    )



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

    # 5) Export: corridor GeoTIFF + path as Shapefile (native CRS) + GeoJSON (native CRS)
    print(f"[{tour_name}] Exporting corridor and vector path...")
    gs.run_command(
        "r.out.gdal",
        input=corridor_score_gamma,
        output=str(corridor_tif),
        format="GTiff",
        overwrite=True
    )
    gs.run_command(
        "v.out.ogr",
        input=smooth_path,
        output=str(path_shp),
        format="ESRI_Shapefile",
        overwrite=True
    )
    gs.run_command(
        "v.out.ogr",
        input=smooth_path,
        output=str(path_geojson),
        format="GeoJSON",
        overwrite=True
    )


    return {
        "corridor_tif": corridor_tif,
        "path_shapefile": path_shp,
        "path_geojson_native": path_geojson
    }