from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.routing_algorithm.evaluation.manual_visual_inspection import write_manual_visual_inspection_outputs


def main() -> None:
    for output in write_manual_visual_inspection_outputs():
        print(output.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
