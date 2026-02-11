from backend.scripts._cli import parse_area_arg
from backend.scripts.make_input_layers import run as run_inputs
from backend.scripts.build_cost_surface import run as run_cost
# from backend.scripts.run_routing import run as run_routing

from data_preprocessing.utils.config import load_config
from data_preprocessing.utils.iter_areas import iter_areas


def run_pipeline_for_area(area_id: str) -> None:
    print("\n====================================")
    print(f"=== Area: {area_id} ===")

    print("\n=== Step 1: Making input layers ===")
    run_inputs(area_id)

    print("\n=== Step 2: Building cost surface ===")
    run_cost(area_id, debug_mode=True)

    # print("\n=== Step 3: Routing ===")
    # run_routing(area_id)


def main():
    area_id = parse_area_arg()

    print("=== Running full pipeline ===")

    if area_id:
        run_pipeline_for_area(area_id)
    else:
        cfg = load_config()
        for area in iter_areas(cfg.study_areas, crs_epsg=cfg.crs_epsg):
            run_pipeline_for_area(area.area_id)


if __name__ == "__main__":
    main()
