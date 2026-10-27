"""The reviewers, and what one of them can say about a corridor.

## The users

Fixed, not registered: four experts and a test user. `id` is what storage
keys on - ASCII, so it is a valid Table Storage partition key - and `name`
is what the page shows. Renaming someone is a change to `name` only; changing
an `id` orphans everything that user has done.

The test user is for trying the app. It sees every corridor, is left out of
every export, and is the only user whose answers can be reset.

## A verdict

    kast         green | blue | red | black, or None while not yet judged
    sub          -1, 0, +1: the -/0/+ within the class
    size         -1, 0, +1: corridor too big / about right / too small.
                 A judgement only - nothing is redrawn
    note         free text
    doubt        "usikker": the reviewer is unsure of this one
    problematic  "problematisk for publisering"

A corridor counts as reviewed once `kast` is set. Everything else has a
default that means "nothing to add", so an untouched corridor and one the
reviewer looked at and agreed with are only told apart by `kast`.

Writes are patches: only the fields that changed. Two browser tabs for one
user then lose nothing either way unless both changed the same field.
"""

from __future__ import annotations

from typing import Any

USERS = [
    {"id": "havard", "name": "Håvard"},
    {"id": "markus", "name": "Markus"},
    {"id": "andreas", "name": "Andreas"},
    {"id": "finn", "name": "Finn"},
    {"id": "test", "name": "Test"},
]
USER_IDS = {u["id"] for u in USERS}
TEST_USER = "test"

KAST_CLASSES = ("green", "blue", "red", "black")
NOTE_MAX = 4000

DEFAULT: dict[str, Any] = {
    "kast": None, "sub": 0, "size": 0, "note": "", "doubt": False, "problematic": False,
}


def validate_patch(patch: Any) -> dict[str, Any]:
    """`patch` with every field checked, or ValueError naming the first bad one."""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch must be a non-empty object")
    clean: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "kast":
            if value is not None and value not in KAST_CLASSES:
                raise ValueError(f"kast must be one of {KAST_CLASSES} or null")
        elif key in ("sub", "size"):
            if isinstance(value, bool) or value not in (-1, 0, 1):
                raise ValueError(f"{key} must be -1, 0 or 1")
        elif key == "note":
            if not isinstance(value, str) or len(value) > NOTE_MAX:
                raise ValueError(f"note must be text of at most {NOTE_MAX} characters")
        elif key in ("doubt", "problematic"):
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
        else:
            raise ValueError(f"unknown field {key!r}")
        clean[key] = value
    return clean


def complete(verdict: dict[str, Any]) -> dict[str, Any]:
    """A stored verdict with defaults for the fields it never had."""
    return {**DEFAULT, **{k: v for k, v in verdict.items() if k in DEFAULT or k == "updatedAt"}}
