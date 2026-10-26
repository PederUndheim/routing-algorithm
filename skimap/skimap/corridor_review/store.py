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
    width            at which width: narrow, standard or wide - what
                     colored-corridors and export draw it at. A verdict
                     from before there were widths has none, and means
                     standard
    colour_computed  what exposure.classify() said about that corridor
    shift            the reviewer's disagreement with it, in ladder steps
                     (-3..+3 for four classes; 0 is agreement)
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

`more_tracks` is a third map of the same shape: tours where even the most
track-reducing model on screen did not follow the tracks far enough, and a
stronger reduction should be tried. It feeds the next `more_tracks` bench
the way needs_fix feeds the next edit of tours.gpkg.

## Rounds

A verdict from an earlier round stays the tour's current answer until the
tour is picked again - export and colored-corridors read it like any other.
But it is not progress on THIS round: `reviewed_this_round` counts only
verdicts made in it, and `previous` names what an earlier round said, so a
re-review can show it beside the panels without counting it as done.
Clearing a verdict made this round puts the earlier round's back, rather
than leaving the tour with nothing - Backspace undoes a pick, it does not
erase round one.

A round need not re-open every tour. `start_round(carry=...)` moves the
named tours' verdicts into the new round as done, marked `carried_from` with
the round that actually made them, so only the rest - flagged tours, new
ones - show as unreviewed. A carried verdict is this round's for progress,
but it was not picked in it: Backspace leaves it alone, and a new pick files
it to history under the round it came from.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Container, Optional

from skimap import config, paths

REVIEW = paths.DATA / "review" / "review.json"

# green -> blue -> red -> black, ordered by the score each class starts at.
# Shifting is a step along this list, so "more severe" means the same thing
# here as it does everywhere else in the repo.
LADDER = tuple(colour for _, colour in config.EXPOSURE_CLASSES)


# The widest disagreement the ladder can express: green to black, or back.
# The reviewer picks a class outright rather than nudging one rung, so a
# verdict may legitimately be three rungs from what classify() said.
MAX_SHIFT = len(LADDER) - 1


STANDARD_WIDTH = "standard"


def verdict_width(verdict: dict[str, Any]) -> str:
    """The width a verdict picked. One recorded before widths existed has
    none, and was a pick of the only corridor there was: the standard one."""
    return verdict.get("width") or STANDARD_WIDTH


def shift_colour(colour: str, shift: int) -> str:
    """Move `colour` along LADDER by `shift`, stopping at either end."""
    if colour not in LADDER:
        return colour
    index = LADDER.index(colour) + int(shift)
    return LADDER[max(0, min(len(LADDER) - 1, index))]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def made_in(verdict: dict[str, Any]) -> int:
    """The round that actually picked this verdict - a carried one's `round`
    is the round it was carried into."""
    return int(verdict.get("carried_from", verdict.get("round", 1)))


def _uncarried(verdict: dict[str, Any]) -> dict[str, Any]:
    """A carried verdict as the round that made it filed it, marked so that
    clear() can carry it again."""
    if "carried_from" not in verdict:
        return verdict
    body = {k: v for k, v in verdict.items() if k != "carried_from"}
    body["round"] = verdict["carried_from"]
    body["was_carried"] = True
    return body


class Store:
    """Verdicts keyed by tour fid, with the ones they replaced kept beside."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else REVIEW
        self.verdicts: dict[int, dict[str, Any]] = {}
        self.needs_fix: dict[int, dict[str, Any]] = {}
        self.more_tracks: dict[int, dict[str, Any]] = {}
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
        self.more_tracks = {int(k): v for k, v in (body.get("more_tracks") or {}).items()}

    def save(self) -> None:
        """Write via a temporary file, so an interrupted write cannot truncate
        the review. os.replace is atomic on Windows as well as POSIX."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "round": self.round,
            "updated": _now(),
            "verdicts": {str(k): v for k, v in sorted(self.verdicts.items())},
            "needs_fix": {str(k): v for k, v in sorted(self.needs_fix.items())},
            "more_tracks": {str(k): v for k, v in sorted(self.more_tracks.items())},
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
               shift: int = 0, note: str = "",
               width: str = STANDARD_WIDTH) -> dict[str, Any]:
        fid = int(fid)
        # Clamped to the ladder, not to one step. It used to be one step,
        # from when the control could only say "more severe" or "less" - and
        # a picker that can name any class would have had every longer
        # disagreement quietly truncated to a single rung, recording a
        # verdict the reviewer did not give.
        shift = max(-MAX_SHIFT, min(MAX_SHIFT, int(shift)))

        previous = self.verdicts.get(fid)
        # Editing only the note is not a changed mind, so it does not go to
        # history. Without this, typing a reason after picking - which is the
        # natural order, now that picking does not advance - would file a
        # superseded verdict identical to the current one on every keystroke
        # pause, and bury the real changes among them.
        #
        # Only within a round: re-picking round one's model in round two is a
        # new judgement that happens to agree, and round one's goes to history
        # like any other - it is what clear() restores and previous() shows.
        amended = (previous is not None
                   and self._this_round(previous)
                   and "carried_from" not in previous
                   and previous.get("model") == model
                   and verdict_width(previous) == width
                   and int(previous.get("shift", 0)) == shift)
        if previous is not None and not amended:
            # Superseded, not overwritten - a changed mind is data too. The
            # fid goes in because a history entry is otherwise unattributable:
            # the verdict itself never carried one (it was the dict's key), so
            # a superseded entry could only be tied back to its tour by
            # chaining `replaced_at` against the next one's `at`. That works
            # right up until you actually need it.
            self.history.append({**_uncarried(previous), "fid": fid,
                                 "replaced_at": _now()})

        verdict = {
            "model": model,
            "width": width,
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
        """Drop this round's verdict on `fid`, restoring an earlier round's.

        Only this round's: a verdict from an earlier round is the answer the
        re-review has not reached yet, and Backspace on a tour you have not
        picked in this round must not erase it."""
        fid = int(fid)
        current = self.verdicts.get(fid)
        if (current is None or not self._this_round(current)
                or "carried_from" in current):
            return False
        del self.verdicts[fid]
        self.history.append({**current, "fid": fid, "cleared_at": _now()})
        earlier = self._earlier(fid)
        if earlier is not None:
            # Undoing a pick over a carried verdict carries it again, or the
            # tour would drop back to unreviewed.
            if earlier.pop("was_carried", False):
                earlier = {**earlier, "carried_from": earlier["round"],
                           "round": self.round}
            self.verdicts[fid] = earlier
        self.save()
        return True

    def get(self, fid: int) -> Optional[dict[str, Any]]:
        return self.verdicts.get(int(fid))

    def this_round(self, fid: int) -> Optional[dict[str, Any]]:
        """The verdict on `fid` if it was made in the current round."""
        verdict = self.get(fid)
        return verdict if verdict is not None and self._this_round(verdict) else None

    def previous(self, fid: int) -> Optional[dict[str, Any]]:
        """What the latest earlier round said about `fid`, or None.

        The current verdict when it is from an earlier round; otherwise the
        last one this round's replaced."""
        verdict = self.get(fid)
        if verdict is not None and not self._this_round(verdict):
            return verdict
        return self._earlier(fid)

    def _this_round(self, verdict: dict[str, Any]) -> bool:
        return int(verdict.get("round", 1)) >= self.round

    def _earlier(self, fid: int) -> Optional[dict[str, Any]]:
        """The last verdict from before this round that a pick in this round
        replaced - from history, which is where record() filed it."""
        for entry in reversed(self.history):
            if (entry.get("fid") == fid and "replaced_at" in entry
                    and int(entry.get("round", 1)) < self.round):
                return {k: v for k, v in entry.items()
                        if k not in ("fid", "replaced_at")}
        return None

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
        return self._set_flag(self.needs_fix, fid, on, note)

    def fix(self, fid: int) -> Optional[dict[str, Any]]:
        return self.needs_fix.get(int(fid))

    def fix_list(self, among: Optional[Container[int]] = None
                 ) -> list[tuple[int, dict[str, Any]]]:
        return sorted(_among(self.needs_fix, among).items())

    # --- tours that want a stronger track reduction tried ----------------

    def set_more_tracks(self, fid: int, on: bool, note: str = ""
                        ) -> Optional[dict[str, Any]]:
        """Flag or unflag this tour for the next more_tracks bench. Apart
        from the verdict for the same reason needs_fix is."""
        return self._set_flag(self.more_tracks, fid, on, note)

    def more_tracks_flag(self, fid: int) -> Optional[dict[str, Any]]:
        return self.more_tracks.get(int(fid))

    def more_tracks_list(self, among: Optional[Container[int]] = None
                         ) -> list[tuple[int, dict[str, Any]]]:
        return sorted(_among(self.more_tracks, among).items())

    def _set_flag(self, table: dict[int, dict[str, Any]], fid: int, on: bool,
                  note: str) -> Optional[dict[str, Any]]:
        fid = int(fid)
        if not on:
            table.pop(fid, None)
            self.save()
            return None
        entry = {"note": note, "round": self.round, "at": _now()}
        table[fid] = entry
        self.save()
        return entry

    def start_round(self, number: Optional[int] = None, *,
                    carry: Optional[Container[int]] = None) -> int:
        """Begin a new round. Verdicts stay; they carry their own round, so
        the ones not revisited remain the current answer for their tour.

        `carry` names tours whose verdict counts as done in the new round
        too - see the module docstring."""
        self.round = int(number) if number else self.round + 1
        for fid, verdict in self.verdicts.items():
            if carry is not None and fid in carry and not self._this_round(verdict):
                verdict["carried_from"] = made_in(verdict)
                verdict["round"] = self.round
        self.save()
        return self.round

    # --- reporting -------------------------------------------------------
    #
    # `among` narrows a report to the tours that still exist. A tour deleted
    # from tours.gpkg keeps its verdict here - it is still a record of what was
    # decided, and a tour deleted by mistake and restored under the same fid
    # gets it back - but it is not progress on the tours there are now, and
    # counting it would put "510 / 819 reviewed" on a review that is at 500.

    def current(self, among: Optional[Container[int]] = None
                ) -> dict[int, dict[str, Any]]:
        """The verdicts, optionally only for fids in `among`."""
        return _among(self.verdicts, among)

    def reviewed_this_round(self, among: Optional[Container[int]] = None
                            ) -> dict[int, dict[str, Any]]:
        """The verdicts made in the current round - a round's progress."""
        return {fid: v for fid, v in self.current(among).items()
                if self._this_round(v)}

    def counts_by_model(self, among: Optional[Container[int]] = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.current(among).values():
            counts[verdict["model"]] = counts.get(verdict["model"], 0) + 1
        return counts

    def counts_by_width(self, among: Optional[Container[int]] = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.current(among).values():
            width = verdict_width(verdict)
            counts[width] = counts.get(width, 0) + 1
        return counts

    def counts_by_colour(self, among: Optional[Container[int]] = None) -> dict[str, int]:
        counts = {colour: 0 for colour in LADDER}
        for verdict in self.current(among).values():
            colour = verdict.get("colour")
            if colour in counts:
                counts[colour] += 1
        return counts

    def shifted(self, among: Optional[Container[int]] = None
                ) -> list[tuple[int, dict[str, Any]]]:
        """Tours where the reviewer disagreed with classify(), worst first."""
        return sorted(
            ((fid, v) for fid, v in self.current(among).items() if v.get("shift")),
            key=lambda item: (-abs(item[1]["shift"]), item[0]),
        )


def _among(entries: dict[int, dict[str, Any]],
           among: Optional[Container[int]]) -> dict[int, dict[str, Any]]:
    if among is None:
        return entries
    return {fid: entry for fid, entry in entries.items() if fid in among}
