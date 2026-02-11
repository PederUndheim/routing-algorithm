import argparse

def parse_area_arg() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", required=True, help="Area ID, e.g. isfjorden")
    args = parser.parse_args()
    return args.area