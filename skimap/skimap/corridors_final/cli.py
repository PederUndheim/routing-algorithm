r"""The last step of the review: the picked corridors as one ordered set.

    python -m skimap.corridors_final plan
    python -m skimap.corridors_final build
    python -m skimap.corridors_final build --draft --out <scratch dir>
    python -m skimap.corridors_final colored     # data/colored_corridors from it

`plan` decides everything - which tours merge, which region each corridor
goes in, what id it gets - and prints it, writing nothing. Run it until it
reads right, then `build`.

`build` refuses while the review is unfinished: a tour with no verdict, a
tour not yet looked at this round, or linked tours merges.json does not
settle. `--draft` builds anyway, from whatever verdict each tour has now,
leaving out what cannot be built and saying so in build.json and id_map -
to try the next stage before the review is done. A draft's ids are not the
final ones: every tour reviewed later can still move them.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from skimap import paths
from skimap.corridors_final import build as build_module, chains


def report(build: build_module.Build) -> None:
    plan = build.plan
    merged = [c for c in build.corridors if len(c.parts) > 1]
    print(f"{len(build.tours)} tours -> {len(build.corridors)} corridors "
          f"({len(merged)} merged from {sum(len(c.parts) for c in merged)} tours)")

    print(f"\nmerges (gap <= {build.decisions.gap_m:g} m):")
    built = {c.fids: c.id for c in merged}
    for group in (g for g in plan.groups if len(g.fids) > 1):
        corridor_id = built.get(group.fids)
        print(f"  {corridor_id if corridor_id else '-':>5}  "
              f"{' + '.join(str(f) for f in group.fids):24s} {group.how}"
              f"{'' if corridor_id else '   (not built: a piece has no corridor yet)'}")
    if build.decisions.keep_apart:
        print(f"  kept apart: {sorted(build.decisions.keep_apart)}")
    if plan.unresolved:
        print(f"\n{len(plan.unresolved)} linked group(s) branch and are not "
              f"settled in merges.json - each tour stays its own corridor for now:")
        for group in plan.unresolved:
            inner = [f"{l.head}->{l.tail}" for l in plan.links
                     if l.head in group and l.tail in group]
            print(f"  {list(group)}  links {', '.join(inner)}")
    if plan.near_misses:
        print(f"\nnear misses, an end within {chains.NEAR_M:.0f} m of a start "
              f"(name them in merges.json 'merge' if they are a split):")
        for link in plan.near_misses:
            print(f"  end of {link.head} -> start of {link.tail}: {link.gap_m:.1f} m")
    for warning in build.warnings:
        print(f"WARNING: {warning}")

    print("\nregions:")
    for region, ids in build_module.region_table(build):
        label = f"{region.id} {region.name}" if region.id else region.name
        print(f"  {region.rank:3d}  {label:30s} {region.kind:1s}  "
              f"{len(ids):4d}  ids {ids[0]}-{ids[-1]}")

    if build.left_out:
        print(f"\n{len(build.left_out)} tour(s) in no corridor:")
        for fid, why in sorted(build.left_out.items()):
            print(f"  {fid:6d}  {why}")
    if build.pending:
        print(f"\n{len(build.pending)} tour(s) not yet reviewed in round "
              f"{build.review_round} (built from an earlier verdict where there "
              f"is one): {build.pending}")
    print(f"\n{'complete' if build.complete else 'NOT complete'}: "
          f"{'ready for build' if build.complete else 'build needs --draft'}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skimap.corridors_final",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="stage", required=True)
    for name, text in (("plan", "show merges, regions and ids; write nothing"),
                       ("build", "write data/corridors_final")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--regions", type=Path, help=f"default {paths.FORECAST_REGIONS}")
        p.add_argument("--merges", type=Path, help=f"default {paths.CORRIDOR_MERGES}")
        if name == "build":
            p.add_argument("--out", type=Path, help=f"default {paths.CORRIDORS_FINAL}")
            p.add_argument("--draft", action="store_true",
                           help="build before the review is finished")
    p = sub.add_parser("colored", help="repaint data/colored_corridors from the "
                                       "built final set")
    p.add_argument("--final", type=Path, help=f"the built set, default {paths.CORRIDORS_FINAL}")
    p.add_argument("--out", type=Path, help=f"default {paths.COLORED_CORRIDORS}")
    p.add_argument("--draft", action="store_true", help="paint from a draft build too")
    args = parser.parse_args(argv)

    if args.stage == "colored":
        from skimap.corridors_final import colored
        colored.write(args.final, args.out, allow_draft=args.draft)
        return 0

    build = build_module.prepare(regions_path=args.regions, merges_path=args.merges)
    report(build)
    if args.stage == "build":
        if not build.complete and not args.draft:
            raise SystemExit("\nNot built: the review is not finished (see above). "
                             "--draft builds it anyway.")
        print()
        out = build_module.write(build, args.out)
        print(f"{len(build.corridors)} corridors -> {out}"
              f"{'' if build.complete else '  (DRAFT)'}")
    return 0
