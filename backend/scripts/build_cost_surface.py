from backend.file_handler.area_context import load_area
from backend.routing_algorithm.cost_surface.build import create_cost_surface


def run(area_id: str, debug_mode: bool) -> None:
    paths, inputs = load_area(area_id)
    create_cost_surface(paths, inputs, debug_mode=debug_mode)


def main():
    from backend.scripts._cli import parse_area_arg
    run(parse_area_arg(), debug_mode=True)


if __name__ == "__main__":
    main()