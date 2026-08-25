from pathlib import Path
from typing import Any, Dict, Tuple, List
from backend.file_handler.area_paths import AreaPaths

from backend.routing_algorithm.routing.grass_env import setup_grass_python_path
setup_grass_python_path()

import grass.script as gs
import grass.script.setup as gsetup

from backend import config


def run_multi_routing_for_tour(
    paths: AreaPaths,    
    slug: str,
    tour_name: str,
    start_vec: str,
    end_vec: str,
    direction_rast: str,
    lambda_weight: float,
    smooth_threshold: float,
    dem_name: str,
    cost_name: str,
) -> Dict[str, Any]:
    
    # Output dirs
    routes_geojson_native_dir = paths.multirouting_native / "geojson"
    slug_geojson_native_dir = routes_geojson_native_dir / slug
    routes_shp_dir = paths.multirouting_native / "shapefiles"
    slug_shp_dir = routes_shp_dir / slug
    heatmap_dir = paths.multirouting_heatmap

    routes_geojson_native_dir.mkdir(parents=True, exist_ok=True)
    slug_geojson_native_dir.mkdir(parents=True, exist_ok=True)
    routes_shp_dir.mkdir(parents=True, exist_ok=True)
    slug_shp_dir.mkdir(parents=True, exist_ok=True)
    heatmap_dir.mkdir(parents=True, exist_ok=True)

    debug_dir = heatmap_dir / "debug_penalty" / slug
    debug_dir.mkdir(parents=True, exist_ok=True)



    
    # Helper to sample C_opt
    def _get_point_xy(vec_point: str) -> str:
        # Export point coords from vector. For a single point, take first line.
        txt = gs.read_command("v.out.ascii", input=vec_point, format="point").strip()
        line = [ln for ln in txt.splitlines() if ln.strip()][0].strip()

        # v.out.ascii format can be "x|y" or "x y" depending on settings
        if "|" in line:
            x, y = line.split("|")[:2]
        else:
            x, y = line.split()[:2]
        return f"{x},{y}"


    END_XY = _get_point_xy(end_vec)

    def sample_c_opt(cum_rast: str) -> float:
        out = gs.read_command("r.what", map=cum_rast, coordinates=END_XY).strip()
        # Typical output: "x|y|value"
        val = out.split("|")[-1].strip()
        if val in ("*", "NULL", ""):
            raise ValueError(f"End point is NULL/unreachable in raster {cum_rast}. r.what: {out}")
        return float(val)
    
    # Initialize rasters
    penalty_rast = f"multi_penalty_{slug}"
    heatmap_rast = f"multi_heatmap_{slug}"
    gs.mapcalc(f"{penalty_rast} = 0", overwrite=True)
    gs.mapcalc(f"{heatmap_rast} = 0", overwrite=True)

    # Baseline route cost for stopping
    cum0 = f"multi_cum0_{slug}"
    dir0 = f"multi_dir0_{slug}"
    gs.run_command(
        "r.walk",
        elevation=dem_name,
        friction=cost_name,
        start_points=start_vec,
        output=cum0,
        outdir=dir0,
        lambda_=lambda_weight,
        overwrite=True
    )
    base_C_opt = sample_c_opt(cum0)

    exported_routes_geojson: List[Path] = []
    exported_routes_shp: List[Path] = []

    for i in range(config.MULTIROUTING_PARAMS["no_routes"]):
        idx = f"{i+1:02d}"

        # Build modifies cost surface with penalties from previous routes
        cost_iter = f"multi_cost_{slug}_{idx}"
        gs.mapcalc(f"{cost_iter} = {cost_name} + {penalty_rast}", overwrite=True)

        # Run r.walk
        cum_iter = f"multi_cum_{slug}_{idx}"
        dir_iter = f"multi_dir_{slug}_{idx}"
        gs.run_command(
            "r.walk",
            elevation=dem_name,
            friction=cost_iter,
            start_points=start_vec,
            output=cum_iter,
            outdir=dir_iter,
            lambda_=lambda_weight,
            overwrite=True
        )

        # DEBUG
        print("cost_iter at end:", gs.read_command("r.what", map=cost_iter, coordinates=END_XY).strip())
        print("cum_iter at end:", gs.read_command("r.what", map=cum_iter, coordinates=END_XY).strip())
        print("cost_base at end:", gs.read_command("r.what", map=cost_name, coordinates=END_XY).strip())
        print("dem_base at end:", gs.read_command("r.what", map=dem_name, coordinates=END_XY).strip())



        C_opt_iter = sample_c_opt(cum_iter)

        # Stop if cost too high
        if C_opt_iter > base_C_opt * (1.0 + config.MULTIROUTING_PARAMS["eps_stop"]):
            print(f"[{tour_name}] Stop: route {idx} too expensive ({C_opt_iter:.2f} > {(1+config.MULTIROUTING_PARAMS['eps_stop'])*base_C_opt:.2f})")
            break

        # Extract optimal path
        path_vec_iter = f"multi_path_{slug}_{idx}"
        path_smooth_iter = f"multi_path_smooth_{slug}_{idx}"

        gs.run_command(
            "r.path",
            input=dir_iter,
            format="auto",
            start_points=end_vec,
            vector_path=path_vec_iter,
            overwrite=True
        )

        gs.run_command(
            "v.generalize",
            input=path_vec_iter,
            output=path_smooth_iter,
            method="douglas",
            threshold=smooth_threshold,
            overwrite=True
        )

        # Rasterize path
        path_rast_iter = f"multi_path_rast_{slug}_{idx}"
        gs.run_command(
            "v.to.rast",
            input=path_smooth_iter,
            output=path_rast_iter,
            use="val",
            value=1,
            overwrite=True
        )

        ## Debug stats
        print(gs.read_command("r.univar", map=path_rast_iter, flags="g"))
        print(gs.read_command("r.univar", map=heatmap_rast, flags="g"))

        # Update heatmap raster
        gs.mapcalc(
            f"{heatmap_rast} = if(isnull({heatmap_rast}), 0, {heatmap_rast}) + "
            f"if({path_rast_iter} == 1, 1, 0)",
            overwrite=True
)

        #Distance transform for buffer penalty
        dist_rast_iter = f"multi_dist_{slug}_{idx}"
        gs.run_command(
            "r.grow.distance",
            input=path_rast_iter,  
            distance=dist_rast_iter,
            metric="euclidean",
            overwrite=True
        )

        # Add smooth penalty with a cap
        buffer_m = config.MULTIROUTING_PARAMS["buffer_m"]
        alpha = config.MULTIROUTING_PARAMS["penalty_alpha"]
        cap = config.MULTIROUTING_PARAMS["penalty_cap"]
        penalty_iter = f"multi_penalty_iter_{slug}_{idx}"

        gs.mapcalc(f"{penalty_iter} = {alpha} * exp(-({dist_rast_iter} * {dist_rast_iter}) / (2 * {buffer_m} * {buffer_m}))", overwrite=True)
        #gs.mapcalc(f"{penalty_iter} = if({path_rast_iter} == 1, 0.5, 0.0)", overwrite=True)
        gs.mapcalc(f"{penalty_rast} = if(isnull({penalty_rast}), 0.0, {penalty_rast})", overwrite=True )
        gs.mapcalc(f"{penalty_rast} = min({penalty_rast} + {penalty_iter}, {cap})", overwrite=True)


        ### Export debug rasters
        gs.run_command("r.out.gdal", input=penalty_iter,
               output=str(debug_dir / f"penalty_iter_{idx}.tif"),
               format="GTiff", type="Float32",
               createopt="COMPRESS=LZW", flags="fc", overwrite=True)

        gs.run_command("r.out.gdal", input=penalty_rast,
                    output=str(debug_dir / f"penalty_total_{idx}.tif"),
                    format="GTiff", type="Float32",
                    createopt="COMPRESS=LZW", flags="fc", overwrite=True)
        ###

        # Export route
        out_geojson = slug_geojson_native_dir / f"{slug}_route_{idx}.geojson"
        out_shp = slug_shp_dir / f"{slug}_route_{idx}.shp"

        gs.run_command(
            "v.out.ogr",
            input=path_smooth_iter,
            output=str(out_geojson),
            format="GeoJSON",
            overwrite=True
        )
        gs.run_command(
            "v.out.ogr",
            input=path_smooth_iter,
            output=str(out_shp),
            format="ESRI_Shapefile",
            overwrite=True
        )
        exported_routes_geojson.append(out_geojson)
        exported_routes_shp.append(out_shp)
    
    # Export heatmap
    out_heatmap = heatmap_dir / f"{slug}_heatmap.tif"
    gs.run_command(
        "r.out.gdal",
        input=heatmap_rast,
        output=str(out_heatmap),
        format="GTiff",
        type="Float32",
        createopt="COMPRESS=LZW",
        overwrite=True
    )

    return {
        "base_C_opt": base_C_opt,
        "routes_geojson": exported_routes_geojson,
        "routes_shp": exported_routes_shp,
        "heatmap_tif": out_heatmap
    }