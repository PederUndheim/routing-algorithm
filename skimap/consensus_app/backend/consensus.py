"""The meetings, and what a meeting can decide about a corridor.

## The meetings

Two, fixed, plus a test meeting: the experts who attend and whose verdicts are shown, and the
one expert whose assigned corridors make up the meeting's list. The ids of
those corridors are resolved from the validation app's assignments.json by
`python -m consensus_app.prepare` and kept in meetings.json beside this file,
so the API needs no access to the validation app's assignment table.

`id` is what storage keys on (the partition), so it must never change once
the meeting has started writing.

## A consensus

    kast         green | blue | red | black, or None while not settled.
                 Main class only - no -/0/+ in the meeting
    size         -1, 0, +1: corridor should be smaller / is OK / bigger
    problematic  "problematisk for publisering"
    change       what should be changed before it can be published
    note         the meeting's common comment

There are no users: everyone in the meeting may edit, and the last write to
a field wins. Writes are patches, so two people changing different fields of
the same corridor both keep theirs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPERT_NAMES = {"havard": "Håvard", "finn": "Finn", "halvor": "Halvor",
                "markus": "Markus", "andreas": "Andreas"}

# In the order the start page shows them. `corridorsOf` is the expert whose
# assignment in the validation app is the meeting's list.
MEETINGS: list[dict[str, Any]] = [
    {"id": "m20261123", "date": "2026-11-23", "label": "23. november",
     "experts": ["havard", "finn", "andreas"], "corridorsOf": "andreas"},
    {"id": "m20261130", "date": "2026-11-30", "label": "30. november",
     "experts": ["havard", "finn", "halvor"], "corridorsOf": "halvor"},
    # For trying the app: the first meeting's corridors and experts, left out
    # of every export, and the only meeting that can be reset.
    {"id": "test", "date": "", "label": "Prøvemøte",
     "experts": ["havard", "finn", "andreas"], "corridorsOf": "andreas", "test": True},
]
MEETING_IDS = {m["id"] for m in MEETINGS}
TEST_MEETING = "test"

IDS_FILE = Path(__file__).resolve().parent / "meetings.json"

KAST_CLASSES = ("green", "blue", "red", "black")
TEXT_MAX = 4000

DEFAULT: dict[str, Any] = {
    "kast": None, "size": 0, "problematic": False, "change": "", "note": "",
}


def meetings() -> list[dict[str, Any]]:
    """MEETINGS with each one's corridor ids and the experts' names."""
    ids = json.loads(IDS_FILE.read_text(encoding="utf-8")) if IDS_FILE.exists() else {}
    return [{**m, "experts": [{"id": e, "name": EXPERT_NAMES[e]} for e in m["experts"]],
             "corridors": ids.get(m["id"], [])} for m in MEETINGS]


def validate_patch(patch: Any) -> dict[str, Any]:
    """`patch` with every field checked, or ValueError naming the first bad one."""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch must be a non-empty object")
    clean: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "kast":
            if value is not None and value not in KAST_CLASSES:
                raise ValueError(f"kast must be one of {KAST_CLASSES} or null")
        elif key == "size":
            if isinstance(value, bool) or value not in (-1, 0, 1):
                raise ValueError("size must be -1, 0 or 1")
        elif key in ("change", "note"):
            if not isinstance(value, str) or len(value) > TEXT_MAX:
                raise ValueError(f"{key} must be text of at most {TEXT_MAX} characters")
        elif key == "problematic":
            if not isinstance(value, bool):
                raise ValueError("problematic must be true or false")
        else:
            raise ValueError(f"unknown field {key!r}")
        clean[key] = value
    return clean


def complete(row: dict[str, Any]) -> dict[str, Any]:
    """A stored consensus with defaults for the fields it never had."""
    return {**DEFAULT, **{k: v for k, v in row.items() if k in DEFAULT or k == "updatedAt"}}
