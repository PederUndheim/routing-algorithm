r"""Which corridors each meeting goes through -> backend/meetings.json.

    & "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" -m consensus_app.prepare

A meeting's list is the validation assignment of its `corridorsOf` expert
(see backend/consensus.py), resolved the way `validation_app.admin assign`
resolves it: from validation_app/assignments.json against the corridor
index. Both files are only read. Run it again if either changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from validation_app.admin import _index, resolve
from validation_app.backend.verdicts import USERS

from .backend.consensus import IDS_FILE, MEETINGS

VALIDATION = Path(__file__).resolve().parents[1] / "validation_app"


def main() -> int:
    index = _index()
    spec = json.loads((VALIDATION / "assignments.json").read_text(encoding="utf-8-sig"))
    resolved = resolve(spec, index)
    every = sorted(c["id"] for c in index)
    known = {u["id"] for u in USERS}
    out = {}
    for m in MEETINGS:
        who = m["corridorsOf"]
        if who not in known:
            raise SystemExit(f"{m['id']}: {who!r} is not a validation user")
        out[m["id"]] = resolved.get(who, every)
        print(f"  {m['label']:14s} {who:8s} {len(out[m['id']])} corridors")
    IDS_FILE.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(f"-> {IDS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
