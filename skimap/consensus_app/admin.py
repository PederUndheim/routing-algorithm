r"""Results out: the admin side of the consensus app.

    $py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
    & $py -m consensus_app.admin export      # -> data/consensus/export/konsensus_<time>.xlsx
    & $py -m consensus_app.admin backup      # -> data/consensus/backup/konsensus_<time>.json

Each talks to the API: --api (default: CONSENSUS_API, else localhost) with
--key (default: CONSENSUS_ADMIN_KEY, else "dev", the local server's key).

## The export

One sheet per meeting, one row per corridor, in corridor order: its status
(enige fra start / avklart i møtet / gjenstår), the consensus as the meeting
sees it - for a corridor the experts agreed on and the meeting never
touched, that is their class - then each expert's verdict and why they
differ. The test meeting is never in it. A last sheet holds every write ever
made, oldest first.

The agreement rule is the page's (frontend/src/agreement.ts): the same main
class from every expert, size OK, nobody problematic or usikker.
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
STATUS_NO = {"agreed": "enige fra start", "settled": "avklart i møtet", "todo": "gjenstår"}


def _call(args: argparse.Namespace, path: str) -> Any:
    request = Request(args.api.rstrip("/") + path, headers={"X-Admin-Key": args.key})
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except HTTPError as e:
        raise SystemExit(f"GET {path}: {e.code} {e.read().decode(errors='replace')}")


def agreed_class(experts: list[str], verdicts: dict[str, dict[str, dict]], cid: int) -> str | None:
    given = [verdicts.get(e, {}).get(str(cid)) for e in experts]
    if any(not v or not v.get("kast") for v in given):
        return None
    if len({v["kast"] for v in given}) > 1:
        return None
    if any(v.get("size") or v.get("problematic") or v.get("doubt") for v in given):
        return None
    return given[0]["kast"]


def reasons(experts: list[str], verdicts: dict[str, dict[str, dict]], cid: int) -> str:
    given = {e: verdicts.get(e, {}).get(str(cid)) or {} for e in experts}
    out = []
    missing = [EXPERT_NAMES[e] for e, v in given.items() if not v.get("kast")]
    if missing:
        out.append("ikke vurdert av " + " og ".join(missing))
    classes = {v["kast"] for v in given.values() if v.get("kast")}
    if len(classes) > 1:
        out.append("ulik klasse")
    for field, label in (("size", "størrelse"), ("problematic", "problematisk"), ("doubt", "usikker")):
        who = [EXPERT_NAMES[e] for e, v in given.items() if v.get(field)]
        if who:
            out.append(f"{label}: {', '.join(who)}")
    return "; ".join(out)


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
        header = ["ID", "Region", "Lengde (m)", "Status", "Konsensus KAST", "Størrelse",
                  "Problematisk", "Hva bør endres", "Felles kommentar"]
        for e in experts:
            n = EXPERT_NAMES[e]
            header += [f"{n} KAST", f"{n} størrelse", f"{n} usikker", f"{n} problematisk", f"{n} notat"]
        header += ["Hvorfor ikke enige"]
        sheet.append(header)
        for cid in m["corridors"]:
            c = index.get(cid, {"region": "", "lengthM": ""})
            row = current.get((m["id"], cid), {})
            agreed = agreed_class(experts, verdicts, cid)
            status = "agreed" if agreed else "settled" if row.get("kast") else "todo"
            kast = row.get("kast") or agreed
            line: list[Any] = [
                cid, c["region"], c["lengthM"], STATUS_NO[status], CLASS_NO.get(kast, ""),
                SIZE_NO[row.get("size", 0)], "ja" if row.get("problematic") else "",
                row.get("change", ""), row.get("note", ""),
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
            wide = title.endswith(("notat", "kommentar", "endres", "enige"))
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
