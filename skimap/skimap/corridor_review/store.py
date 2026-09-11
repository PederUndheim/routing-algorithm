"""The verdicts, on disk as JSON.

One file, `data/review/review.json`, holding the current verdict per tour and
every verdict it replaced. JSON rather than a column on tours.gpkg because a
review runs in rounds: you want to diff round two against round one, see what
changed and why, and occasionally fix a misclick in a text editor. A binary
GeoPackage is a poor medium for all three. `export` writes the GPKG when the
round is done - see cli.export.

Every verdict is written through immediately. A review of 842 tours is not
one sitting, and nothing is worse than losing an evening's judgements to a
closed laptop.

## What a verdict records

    model            which model's corridor was picked
    colour_computed  what exposure.classify() said about that corridor
    shift            -1, 0 or +1: the reviewer's disagreement with it
    colour           the class after the shift - what export writes

Both the computed class and the shift are kept, never just the result. The
disagreements are the interesting part: a run of tours where the reviewer
pushed green to blue is evidence about config.EXPOSURE_CLASSES itself, and
that signal is gone the moment you store only the final answer.

## Tours that need re-digitizing

`needs_fix` is a second, independent map: fid -> why. Reviewing corridors is
the fastest way anybody will ever find a bad tour - you are looking at the
ground it was routed over, at the right zoom, with the slope underneath - and
the flag exists so that noticing costs one keystroke instead of a note in
another window.

It is kept apart from the verdicts because it answers a different question.
"This is the best of the three corridors" and "the tour these were routed
from is wrong" can both be true, either can be true alone, and a new round
that re-picks every corridor should not quietly drop a list of tours somebody
found broken.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from skimap import config, paths

REVIEW = paths.DATA / "review" / "review.json"

# green -> blue -> red -> black, ordered by the score each class starts at.
# Shifting is a step along this list, so "more severe" means the same thing
# here as it does everywhere else in the repo.
LADDER = tuple(colour for _, colour in config.EXPOSURE_CLASSES)


def shift_colour(colour: str, shift: int) -> str:
    """Move `colour` along LADDER by `shift`, stopping at either end."""
    if colour not in LADDER:
        return colour
    index = LADDER.index(colour) + int(shift)
    return LADDER[max(0, min(len(LADDER) - 1, index))]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Verdicts keyed by tour fid, with the ones they replaced kept beside."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else REVIEW
        self.verdicts: dict[int, dict[str, Any]] = {}
        self.needs_fix: dict[int, dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []
        self.round = 1
        self._load()

    # --- disk ------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.is_file():
            return
        body = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self.round = int(body.get("round", 1))
        self.history = list(body.get("history") or [])
        # JSON object keys are strings; fids are ints everywhere else.
        self.verdicts = {int(k): v for k, v in (body.get("verdicts") or {}).items()}
        self.needs_fix = {int(k): v for k, v in (body.get("needs_fix") or {}).items()}

    def save(self) -> None:
        """Write via a temporary file, so an interrupted write cannot truncate
        the review. os.replace is atomic on Windows as well as POSIX."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "round": self.round,
            "updated": _now(),
            "verdicts": {str(k): v for k, v in sorted(self.verdicts.items())},
            "needs_fix": {str(k): v for k, v in sorted(self.needs_fix.items())},
            "history": self.history,
        }
        text = json.dumps(body, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent,
            prefix=self.path.name, suffix=".tmp", delete=False,
        ) as handle:
            handle.write(text)
            temporary = Path(handle.name)
        temporary.replace(self.path)

    # --- verdicts --------------------------------------------------------

    def record(self, fid: int, *, model: str, colour_computed: str,
               shift: int = 0, note: str = "") -> dict[str, Any]:
        fid = int(fid)
        shift = max(-1, min(1, int(shift)))

        previous = self.verdicts.get(fid)
        # Editing only the note is not a changed mind, so it does not go to
        # history. Without this, typing a reason after picking - which is the
        # natural order, now that picking does not advance - would file a
        # superseded verdict identical to the current one on every keystroke
        # pause, and bury the real changes among them.
        amended = (previous is not None
                   and previous.get("model") == model
                   and int(previous.get("shift", 0)) == shift)
        if previous is not None and not amended:
            # Superseded, not overwritten - a changed mind is data too. The
            # fid goes in because a history entry is otherwise unattributable:
            # the verdict itself never carried one (it was the dict's key), so
            # a superseded entry could only be tied back to its tour by
            # chaining `replaced_at` against the next one's `at`. That works
            # right up until you actually need it.
            self.history.append({**previous, "fid": fid, "replaced_at": _now()})

        verdict = {
            "model": model,
            "colour_computed": colour_computed,
            "shift": shift,
            "colour": shift_colour(colour_computed, shift),
            "note": note,
            "round": self.round,
            # An amendment keeps the moment the judgement was made. Only the
            # reason for it was written later.
            "at": previous["at"] if amended and previous.get("at") else _now(),
        }
        self.verdicts[fid] = verdict
        self.save()
        return verdict

    def clear(self, fid: int) -> bool:
        fid = int(fid)
        previous = self.verdicts.pop(fid, None)
        if previous is None:
            return False
        self.history.append({**previous, "fid": fid, "cleared_at": _now()})
        self.save()
        return True

    def get(self, fid: int) -> Optional[dict[str, Any]]:
        return self.verdicts.get(int(fid))

    # --- tours that need re-digitizing -----------------------------------

    def set_fix(self, fid: int, on: bool, note: str = "") -> Optional[dict[str, Any]]:
        """Flag or unflag this tour as needing work in tours.gpkg.

        Deliberately not part of the verdict. "This corridor is the best of
        the three" and "the tour this was routed from is wrong" are different
        claims, and a tour can need its start point moved whether or not you
        have decided anything about its corridors. Keeping them apart means
        flagging one does not commit you to the other, and the fix list
        survives a new round that re-picks every corridor.
        """
        fid = int(fid)
        if not on:
            self.needs_fix.pop(fid, None)
            self.save()
            return None
        entry = {"note": note, "round": self.round, "at": _now()}
        self.needs_fix[fid] = entry
        self.save()
        return entry

    def fix(self, fid: int) -> Optional[dict[str, Any]]:
        return self.needs_fix.get(int(fid))

    def fix_list(self) -> list[tuple[int, dict[str, Any]]]:
        return sorted(self.needs_fix.items())

    def start_round(self, number: Optional[int] = None) -> int:
        """Begin a new round. Verdicts stay; they carry their own round, so
        the ones not revisited remain the current answer for their tour."""
        self.round = int(number) if number else self.round + 1
        self.save()
        return self.round

    # --- reporting -------------------------------------------------------

    def counts_by_model(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.verdicts.values():
            counts[verdict["model"]] = counts.get(verdict["model"], 0) + 1
        return counts

    def counts_by_colour(self) -> dict[str, int]:
        counts = {colour: 0 for colour in LADDER}
        for verdict in self.verdicts.values():
            colour = verdict.get("colour")
            if colour in counts:
                counts[colour] += 1
        return counts

    def shifted(self) -> list[tuple[int, dict[str, Any]]]:
        """Tours where the reviewer disagreed with classify(), worst first."""
        return sorted(
            ((fid, v) for fid, v in self.verdicts.items() if v.get("shift")),
            key=lambda item: (-abs(item[1]["shift"]), item[0]),
        )
