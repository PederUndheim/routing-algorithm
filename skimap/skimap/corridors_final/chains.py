"""Which tours are pieces of one corridor, and which corridor each piece joins.

Some tours were digitized in two or more pieces to get the shape wanted out
of the router: one piece up to a col, the next from the col to the summit.
In tours.gpkg that shows as a tour ending exactly where another starts - a
link. Nothing else in the data puts an end on a start: two tours sharing a
trailhead meet start-to-start, two routes up one summit end-to-end, and
neither is a split.

Most linked pieces form a plain chain, A -> B or A -> B -> C, and those are
merged without asking. A group that branches - two approaches into one top
section, or one approach out to two summits - has no single obvious answer,
so it is never merged on a guess. It has to be decided in merges.json:

    {
      "gap_m": 10,
      "merge": [[1122, 1123], [1122, 1140, 1141]],
      "keep_apart": [[360, 361, 362], [1119, 1120, 1121]],
      "not_splits": [[703, 408], [1063, 1141]]
    }

`merge` lists corridors to build, each from the tours named. A tour may be
in more than one - above, 1122 is the shared approach of two corridors -
and a group may join tours further apart than `gap_m`, for a split that
was digitized with a gap. `keep_apart` names tours that stay corridors of
their own, inner lists only for readability. A linked group is decided once
every tour in it is in one of the two; a group with some tours decided and
some not is reported, not finished off by a guess. `not_splits` lists near
misses (an end and a start up to NEAR_M apart) that were looked at and are
two tours, so they stop being reported.

Pure Python and numpy, no GDAL, so it can be tested on bare coordinates.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np

Point = tuple[float, float]

# A link this close is a split tour. Measured 2026-10-26: the 19 real ones
# sit at 0 - 7 m, the next nearest end-to-start pair at 57 m.
GAP_M = 10.0

# Links up to this far are reported as near misses, so a split digitized
# with a gap is seen and can be named in `merge` by hand.
NEAR_M = 300.0


@dataclass(frozen=True)
class Link:
    head: int       # the tour whose end it is
    tail: int       # the tour whose start it is
    gap_m: float


@dataclass(frozen=True)
class Decisions:
    gap_m: float = GAP_M
    merge: tuple[tuple[int, ...], ...] = ()
    keep_apart: frozenset[int] = frozenset()
    not_splits: frozenset[frozenset[int]] = frozenset()

    @property
    def merged(self) -> frozenset[int]:
        return frozenset(f for group in self.merge for f in group)

    @property
    def decided(self) -> frozenset[int]:
        return self.merged | self.keep_apart


@dataclass(frozen=True)
class Group:
    """One final corridor's tours, start piece first."""
    fids: tuple[int, ...]
    how: str            # "single", "auto" or "merge" (named in merges.json)
    path: bool = True   # each piece starts where the one before ends


@dataclass
class Plan:
    groups: list[Group]
    links: list[Link]                       # every link within gap_m
    unresolved: list[tuple[int, ...]]       # linked groups nobody decided
    near_misses: list[Link]                 # gap_m < gap <= NEAR_M
    warnings: list[str] = field(default_factory=list)


def load_decisions(path: Path) -> Decisions:
    """merges.json, or no decisions at all if there is no file yet."""
    if not path.is_file():
        return Decisions()
    # utf-8-sig: hand-edited on Windows, where Notepad writes a BOM.
    body = json.loads(path.read_text(encoding="utf-8-sig"))
    merge = tuple(tuple(int(f) for f in group) for group in body.get("merge") or ())
    keep = frozenset(int(f) for f in _flatten(body.get("keep_apart") or ()))
    for group in merge:
        if len(group) < 2:
            raise SystemExit(f"{path.name}: merge group {list(group)} has one tour")
        if len(set(group)) != len(group):
            raise SystemExit(f"{path.name}: merge group {list(group)} repeats a tour")
    both = keep & frozenset(f for group in merge for f in group)
    if both:
        raise SystemExit(f"{path.name}: {sorted(both)} both merged and kept apart")
    not_splits = frozenset(frozenset(int(f) for f in pair)
                           for pair in body.get("not_splits") or ())
    return Decisions(gap_m=float(body.get("gap_m", GAP_M)), merge=merge,
                     keep_apart=keep, not_splits=not_splits)


def _flatten(items: Iterable) -> Iterable[int]:
    for item in items:
        if isinstance(item, (list, tuple)):
            yield from _flatten(item)
        else:
            yield item


def find_links(ends: Mapping[int, tuple[Point, Point]], within_m: float
               ) -> list[Link]:
    """Every (end of one tour, start of another) pair within `within_m`,
    closest first. `ends` is fid -> (start, end)."""
    fids = sorted(ends)
    if not fids:
        return []
    starts = np.array([ends[f][0] for f in fids], dtype=float)
    finishes = np.array([ends[f][1] for f in fids], dtype=float)
    # n x n is a few MB at a thousand tours - simpler than a tree, and fast.
    gaps = np.hypot(finishes[:, None, 0] - starts[None, :, 0],
                    finishes[:, None, 1] - starts[None, :, 1])
    np.fill_diagonal(gaps, np.inf)
    heads, tails = np.nonzero(gaps <= within_m)
    links = [Link(fids[h], fids[t], float(gaps[h, t])) for h, t in zip(heads, tails)]
    return sorted(links, key=lambda link: (link.gap_m, link.head, link.tail))


def plan(ends: Mapping[int, tuple[Point, Point]],
         decisions: Optional[Decisions] = None) -> Plan:
    """Every tour in `ends` into exactly the corridors it belongs to."""
    decisions = decisions or Decisions()
    unknown = sorted(decisions.decided - set(ends))
    if unknown:
        raise SystemExit(f"merges.json names tours that do not exist: {unknown}")

    nearby = find_links(ends, max(NEAR_M, decisions.gap_m))
    links = [link for link in nearby if link.gap_m <= decisions.gap_m]
    near_misses = [link for link in nearby if link.gap_m > decisions.gap_m
                   and frozenset((link.head, link.tail)) not in decisions.not_splits]

    groups: list[Group] = []
    warnings: list[str] = []
    for named in decisions.merge:
        fids, is_path = order(named, nearby)
        if fids is None:
            warnings.append(f"merge {list(named)}: no end meets a start within "
                            f"{NEAR_M:.0f} m, kept in the order written")
            fids, is_path = tuple(named), False
        groups.append(Group(fids, "merge", is_path))

    unresolved: list[tuple[int, ...]] = []
    linked: set[int] = set()
    for component in _components(links):
        linked.update(component)
        undecided = [f for f in component if f not in decisions.decided]
        if not undecided:
            continue
        if len(undecided) == len(component):
            fids, is_path = order(component, links)
            if fids is not None and is_path and _is_chain(component, links):
                groups.append(Group(fids, "auto"))
                continue
        unresolved.append(tuple(sorted(component)))

    merged = decisions.merged | {f for g in groups if g.how == "auto" for f in g.fids}
    for fid in sorted(ends):
        if fid not in merged:
            groups.append(Group((fid,), "single"))

    near_misses = [link for link in near_misses
                   if not any({link.head, link.tail} <= set(g.fids) for g in groups)]
    return Plan(groups=groups, links=links, unresolved=unresolved,
                near_misses=near_misses, warnings=warnings)


def _components(links: Sequence[Link]) -> list[list[int]]:
    """Tours connected by any chain of links, each sorted, in fid order."""
    neighbours: dict[int, set[int]] = defaultdict(set)
    for link in links:
        neighbours[link.head].add(link.tail)
        neighbours[link.tail].add(link.head)
    seen: set[int] = set()
    out = []
    for fid in sorted(neighbours):
        if fid in seen:
            continue
        component, stack = [], [fid]
        while stack:
            here = stack.pop()
            if here in seen:
                continue
            seen.add(here)
            component.append(here)
            stack.extend(neighbours[here] - seen)
        out.append(sorted(component))
    return out


def _is_chain(component: Sequence[int], links: Sequence[Link]) -> bool:
    """No piece has two pieces leading into it or two leading on from it."""
    members = set(component)
    inner = [l for l in links if l.head in members and l.tail in members]
    heads = [l.head for l in inner]
    tails = [l.tail for l in inner]
    return (len(set(heads)) == len(heads) and len(set(tails)) == len(tails)
            and len(inner) == len(members) - 1)


def order(fids: Iterable[int], links: Sequence[Link]
          ) -> tuple[Optional[tuple[int, ...]], bool]:
    """`fids` start piece first, and whether they form one unbroken path.

    The order follows the links among them, the closest link winning where
    a piece has two candidates. (None, False) when the pieces are not
    linked at all, so the caller can say so instead of inventing an order.
    """
    members = list(dict.fromkeys(fids))
    if len(members) == 1:
        return (members[0],), True
    member_set = set(members)
    inner = sorted((l for l in links if l.head in member_set and l.tail in member_set),
                   key=lambda l: l.gap_m)
    after: dict[int, int] = {}
    before: dict[int, int] = {}
    for link in inner:
        if link.head not in after and link.tail not in before:
            after[link.head] = link.tail
            before[link.tail] = link.head
    if not after:
        return None, False

    # Walk each chain from its first piece; leftovers are a branch, placed
    # after the chain they hang off so the start piece still comes first.
    out: list[int] = []
    for first in [f for f in members if f not in before]:
        here: Optional[int] = first
        while here is not None and here not in out:
            out.append(here)
            here = after.get(here)
    out += [f for f in members if f not in out]
    is_path = all(after.get(a) == b for a, b in zip(out, out[1:]))
    return tuple(out), is_path
