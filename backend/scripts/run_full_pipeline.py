from backend.scripts._cli import parse_area_arg
from backend.scripts.make_input_layers import run as run_inputs
from backend.scripts.build_cost_surface import run as run_cost
from backend.scripts.run_routing import run as run_routing

def main():
    area_id = parse_area_arg()

    print("=== Running full pipeline ===")
    print(f"=== Area: {area_id} ===")

    print("\n=== Step 1: Making input layers ===")
    run_inputs(area_id)

    print("\n=== Step 2: Building cost surface ===")
    run_cost(area_id, debug_mode=True)

    print("\n=== Step 3: Routing ===")
    run_routing(area_id)


if __name__ == "__main__":
    main()