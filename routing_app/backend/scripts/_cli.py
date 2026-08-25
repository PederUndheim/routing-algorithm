import argparse
from typing import Optional

def parse_area_arg() -> Optional[str]:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--area",
        required=False,
        help="Area ID, e.g. isfjorden_01. If omitted, all areas are processed.",
    )
    args = parser.parse_args()
    return args.area