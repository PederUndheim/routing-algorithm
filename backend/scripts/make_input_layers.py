from backend.file_handler.area_context import load_area
from backend.routing_algorithm.inputs.make_pra_runout_combined import build_pra_runout_layer
from backend.routing_algorithm.inputs.make_tractorroads_trails_in_forest import build_tractor_trails_in_forest

def run(area_id: str) -> None:
    paths, inputs = load_area(area_id)

    print(f"=== Building input layers, area={area_id} ===")

    out_pra = build_pra_runout_layer(paths, inputs)
    inputs["pra_runout_combined"] = out_pra

    out_tt = build_tractor_trails_in_forest(paths, inputs)
    inputs["tractorroads_trails_in_forest"] = out_tt

    print("\n=== Done building input layers ===")


def main():
    from backend.scripts._cli import parse_area_arg
    run(parse_area_arg())


if __name__ == "__main__":
    main()