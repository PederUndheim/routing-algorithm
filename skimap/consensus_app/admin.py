r"""Results out: the admin side of the consensus app.

    $py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
    & $py -m consensus_app.admin export      # -> data/consensus/export/konsensus_<time>.xlsx
    & $py -m consensus_app.admin backup      # -> data/consensus/backup/konsensus_<time>.json

Each talks to the API: --api (default: CONSENSUS_API, else localhost) with
--key (default: CONSENSUS_ADMIN_KEY, else "dev", the local server's key).

## The export

One sheet per meeting, one row per corridor, in corridor order: its status
(auto-klassifisert / avklart i møtet / gjenstår), the consensus as the
meeting sees it - for an auto-classified corridor the meeting never touched,
the auto class - and what to do with it later (new waypoint, new end point,
two tours, other, delete), then each expert's verdict and why it went to
the meeting. The test meeting is never in it. A last sheet holds every write ever
made, oldest first.

The auto-classification rule is the page's (frontend/src/agreement.ts):
every expert has set a class; the classes are majority + neighbour (all one
class, or two in one and the third in the class next to it); nobody ticked
Problematisk; and nobody ticked Usikker unless all gave the same class. Size
and notes do not count. The auto class is the median of the twelve steps.
An auto corridor the meeting never sized gets the experts' size, with
"Størrelse fra" saying so; one the review took back to discussion is
"auto-overstyring" until the meeting sets a class.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .backend.consensus import EXPERT_NAMES, TEST_MEETING, meetings

HERE = Path(__file__).resolve().parent
INDEX = HERE.parent / "validation_app" / "frontend" / "public" / "corridors" / "index.json"
OUT = HERE.parent / "data" / "consensus"

CLASS_NO = {"green": "grønn", "blue": "blå", "red": "rød", "black": "svart"}
SUB_MARK = {-1: "−", 0: "", 1: "+"}
SIZE_NO = {-1: "mindre", 0: "", 1: "større"}
STATUS_NO = {"agreed": "auto-klassifisert", "reopened": "auto-overstyring", "settled": "avklart i møtet",
             "todo": "gjenstår"}


def _call(args: argparse.Namespace, path: str) -> Any:
    request = Request(args.api.rstrip("/") + path, headers={"X-Admin-Key": args.key})
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except HTTPError as e:
        raise SystemExit(f"GET {path}: {e.code} {e.read().decode(errors='replace')}")


def _class(kast: str | None, sub: int) -> str:
    return CLASS_NO[kast] + SUB_MARK[sub] if kast else ""


CLASS_ORDER = ("green", "blue", "red", "black")


def majority_neighbour(classes: list[str]) -> bool:
    """All one class, or all but one in one class and that one next to it."""
    if len(set(classes)) <= 1:
        return True
    if len(classes) < 3:
        return False
    idx = [CLASS_ORDER.index(k) for k in classes]
    for c in set(idx):
        others = [i for i in idx if i != c]
        if len(others) == 1 and abs(others[0] - c) == 1:
            return True
    return False


def reasons(experts: list[str], verdicts: dict[str, dict[str, dict]], cid: int) -> str:
    """Why the corridor goes to the meeting; empty when it is auto-classified."""
    given = {e: verdicts.get(e, {}).get(str(cid)) or {} for e in experts}
    rated = {e: v for e, v in given.items() if v.get("kast")}
    out = []
    missing = [EXPERT_NAMES[e] for e in given if e not in rated]
    if missing:
        out.append("ikke vurdert av " + " og ".join(missing))
    classes = [v["kast"] for v in rated.values()]
    if not majority_neighbour(classes):
        out.append("for ulike klasser")
    who = [EXPERT_NAMES[e] for e, v in rated.items() if v.get("problematic")]
    if who:
        out.append(f"problematisk: {', '.join(who)}")
    who = [EXPERT_NAMES[e] for e, v in rated.items() if v.get("doubt")]
    if who and len(set(classes)) > 1:
        out.append(f"usikker og ulik klasse: {', '.join(who)}")
    return "; ".join(out)


def size_hint(experts: list[str], verdicts: dict[str, dict[str, dict]], cid: int) -> tuple[str, str]:
    """The experts' size on an auto corridor: ("mindre" | "større" |
    "mindre/større" | "", who), as on the page."""
    given = {e: verdicts.get(e, {}).get(str(cid)) or {} for e in experts}
    smaller = [EXPERT_NAMES[e] for e, v in given.items() if v.get("kast") and v.get("size") == -1]
    bigger = [EXPERT_NAMES[e] for e, v in given.items() if v.get("kast") and v.get("size") == 1]
    label = "mindre/større" if smaller and bigger else "mindre" if smaller else "større" if bigger else ""
    return label, ", ".join(smaller + bigger)


def agreed_step(experts: list[str], verdicts: dict[str, dict[str, dict]],
                cid: int) -> tuple[str, int] | None:
    """The auto (class, step), or None: the median of the experts' twelve
    steps, as on the page."""
    if not experts or reasons(experts, verdicts, cid):
        return None
    steps = sorted(CLASS_ORDER.index(v["kast"]) * 3 + v.get("sub", 0) + 1
                   for v in (verdicts[e][str(cid)] for e in experts))
    mid = steps[(len(steps) - 1) // 2]
    return CLASS_ORDER[mid // 3], mid % 3 - 1


def export(args: argparse.Namespace) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    dump = _call(args, "/api/admin/dump")
    index = {c["id"]: c for c in json.loads(INDEX.read_text(encoding="utf-8"))}
    current = {(r["meeting"], r["corridor"]): r for r in dump["current"]}

    book = Workbook()
    book.remove(book.active)
    for m in meetings():
        if m["id"] == TEST_MEETING:
            continue
        experts = [e["id"] for e in m["experts"]]
        verdicts = _call(args, f"/api/admin/experts?meeting={m['id']}")["verdicts"]
        sheet = book.create_sheet(m["label"])
        header = ["ID", "Region", "Lengde (m)", "Status", "Konsensus KAST", "Størrelse", "Størrelse fra",
                  "Auto-overstyring", "Felles kommentar",
                  "Nytt mellompunkt", "Mellompunkt hvor", "Endre sluttpunkt", "Sluttpunkt hvor",
                  "To turer", "Tur 1 hvor", "Tur 1 KAST", "Tur 2 hvor", "Tur 2 KAST",
                  "Annet", "Annet hva", "Slett"]
        for e in experts:
            n = EXPERT_NAMES[e]
            header += [f"{n} KAST", f"{n} størrelse", f"{n} usikker", f"{n} problematisk", f"{n} notat"]
        header += ["Hvorfor til møtet"]
        sheet.append(header)
        for cid in m["corridors"]:
            c = index.get(cid, {"region": "", "lengthM": ""})
            row = current.get((m["id"], cid), {})
            agreed = agreed_step(experts, verdicts, cid)
            reopened = bool(row.get("reopened"))
            status = ("agreed" if agreed and not reopened else "settled" if row.get("kast")
                      else "reopened" if agreed else "todo")
            kast, sub = ((row["kast"], row.get("sub", 0)) if row.get("kast")
                         else agreed if agreed and not reopened else (None, 0))
            # The size: the meeting's once it chose one; on an auto corridor it
            # never sized, the experts' - marked as theirs.
            size, size_from = SIZE_NO[row.get("size", 0)], "konsensus" if row.get("sizeSet") or row.get("size") else ""
            if status == "agreed" and not size_from:
                hint, who = size_hint(experts, verdicts, cid)
                if hint:
                    size, size_from = hint, f"ekspert ({who}), ikke avklart i konsensus"
            line: list[Any] = [
                cid, c["region"], c["lengthM"], STATUS_NO[status],
                CLASS_NO[kast] + SUB_MARK[sub] if kast else "",
                size, size_from, "ja" if reopened else "", row.get("note", ""),
                "ja" if row.get("midpoint") else "", row.get("midpointWhere", ""),
                "ja" if row.get("endpoint") else "", row.get("endpointWhere", ""),
                "ja" if row.get("split") else "",
                row.get("split1Where", ""), _class(row.get("split1Kast"), row.get("split1Sub", 0)),
                row.get("split2Where", ""), _class(row.get("split2Kast"), row.get("split2Sub", 0)),
                "ja" if row.get("other") else "", row.get("otherWhat", ""), "ja" if row.get("remove") else "",
            ]
            for e in experts:
                v = verdicts.get(e, {}).get(str(cid)) or {}
                line += [CLASS_NO[v["kast"]] + SUB_MARK[v.get("sub", 0)] if v.get("kast") else "",
                         SIZE_NO[v.get("size", 0)], "ja" if v.get("doubt") else "",
                         "ja" if v.get("problematic") else "", v.get("note", "")]
            line.append(reasons(experts, verdicts, cid))
            sheet.append(line)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "E2"
        sheet.auto_filter.ref = sheet.dimensions
        for i, title in enumerate(header, 1):
            wide = title.endswith(("notat", "kommentar", "møtet", "hvor", "hva", "fra"))
            sheet.column_dimensions[get_column_letter(i)].width = 40 if wide else max(8, min(len(title) + 2, 18))

    log = book.create_sheet("Historikk")
    labels = {m["id"]: m["label"] for m in meetings()}
    log.append(["Tid (server)", "Tid (klient)", "Møte", "ID", "Endring"])
    for h in dump["history"]:
        if h["meeting"] != TEST_MEETING:
            log.append([h["serverTs"], h["clientTs"], labels.get(h["meeting"], h["meeting"]),
                        h["corridor"], json.dumps(h["patch"], ensure_ascii=False)])
    for cell in log[1]:
        cell.font = Font(bold=True)

    out = Path(args.out) if args.out else (
        OUT / "export" / f"konsensus_{datetime.now():%Y%m%d_%H%M}.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)
    print(f"-> {out}")


def backup(args: argparse.Namespace) -> None:
    dump = _call(args, "/api/admin/dump")
    out = Path(args.out) if args.out else (
        OUT / "backup" / f"konsensus_{datetime.now():%Y%m%d_%H%M%S}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(dump['current'])} rows, {len(dump['history'])} history rows -> {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m consensus_app.admin",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--api", default=os.environ.get("CONSENSUS_API", "http://127.0.0.1:8791"))
    parser.add_argument("--key", default=os.environ.get("CONSENSUS_ADMIN_KEY", "dev"))
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export", help="the spreadsheet, one sheet per meeting")
    p.add_argument("--out")
    p.set_defaults(func=export)
    p = sub.add_parser("backup", help="everything in the store, as JSON")
    p.add_argument("--out")
    p.set_defaults(func=backup)
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
