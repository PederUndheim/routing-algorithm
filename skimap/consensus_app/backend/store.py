"""Where the meetings' decisions live: Azure Table Storage, or a local file log.

The same design as the validation app's store, which has carried the expert
verdicts without a loss:

    current   one row per (meeting, corridor): the consensus as it stands
    history   one row per write, never changed or removed: the patch and when

History is written first, and a retry carries the same `op_id`, so a write
that dies halfway is completed by the client's retry and never counted twice.
`current` can always be rebuilt from history.

The partition is the meeting, not a user: there are no users here, everyone
in the meeting edits the same rows.

`state(meeting, since)` returns only rows changed at or after `since`, so the
pages can ask every few seconds what the others have done without fetching
the whole meeting each time.

These are the consensus app's own tables (kons*), in its own storage
account. It never writes to the validation app's tables - it reads the
experts' verdicts through a read-only SAS, see experts.py.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from .consensus import complete


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store(Protocol):
    name: str

    def state(self, meeting: str, since: Optional[str] = None) -> dict[int, dict[str, Any]]: ...
    def apply(self, meeting: str, corridor: int, patch: dict[str, Any],
              op_id: str, client_ts: str) -> dict[str, Any]: ...
    def reset(self, meeting: str) -> int: ...
    def dump(self) -> dict[str, Any]: ...


# --- local ---------------------------------------------------------------

class FileStore:
    """An append-only log in `root/log.jsonl`, replayed into memory on start."""

    name = "file"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "log.jsonl"
        self._lock = threading.Lock()
        self._current: dict[str, dict[int, dict[str, Any]]] = {}
        self._history: list[dict[str, Any]] = []
        self._ops: set[tuple[str, str]] = set()
        if self.log.exists():
            for line in self.log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._replay(json.loads(line))

    def _replay(self, event: dict[str, Any]) -> None:
        meeting = event["meeting"]
        if event["type"] == "reset":
            self._current.pop(meeting, None)
            self._history = [h for h in self._history if h["meeting"] != meeting]
            self._ops = {op for op in self._ops if op[0] != meeting}
            return
        self._history.append(event)
        self._ops.add((meeting, event["opId"]))
        row = self._current.setdefault(meeting, {}).setdefault(event["corridor"], {})
        row.update(event["patch"])
        row["updatedAt"] = event["serverTs"]

    def _append(self, event: dict[str, Any]) -> None:
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def state(self, meeting: str, since: Optional[str] = None) -> dict[int, dict[str, Any]]:
        with self._lock:
            return {cid: complete(v) for cid, v in self._current.get(meeting, {}).items()
                    if since is None or v["updatedAt"] >= since}

    def apply(self, meeting: str, corridor: int, patch: dict[str, Any],
              op_id: str, client_ts: str) -> dict[str, Any]:
        with self._lock:
            if (meeting, op_id) not in self._ops:
                event = {"type": "patch", "meeting": meeting, "corridor": corridor, "patch": patch,
                         "opId": op_id, "clientTs": client_ts, "serverTs": _now()}
                self._append(event)
                self._replay(event)
            return complete(self._current[meeting][corridor])

    def reset(self, meeting: str) -> int:
        with self._lock:
            count = len(self._current.get(meeting, {}))
            event = {"type": "reset", "meeting": meeting, "serverTs": _now()}
            self._append(event)
            self._replay(event)
            return count

    def dump(self) -> dict[str, Any]:
        with self._lock:
            current = [{"meeting": m, "corridor": cid, **complete(v)}
                       for m, rows in self._current.items() for cid, v in rows.items()]
            return {"current": current, "history": list(self._history), "dumpedAt": _now()}


# --- Azure ---------------------------------------------------------------

CURRENT_TABLE = "current"
HISTORY_TABLE = "history"


def _row(corridor: int) -> str:
    return f"{corridor:04d}"


class TableStore:
    """Azure Table Storage. PartitionKey is always the meeting."""

    name = "azure-tables"

    def __init__(self, connection_string: str, prefix: str = "kons") -> None:
        from azure.data.tables import TableServiceClient

        self._service = TableServiceClient.from_connection_string(connection_string)
        self._prefix = prefix   # tables are konscurrent, konshistory
        for table in (CURRENT_TABLE, HISTORY_TABLE):
            self._service.create_table_if_not_exists(prefix + table)
        # A TableClient per thread: the SDK does not promise a shared one is safe.
        self._local = threading.local()

    def _table(self, name: str):
        clients = getattr(self._local, "clients", None)
        if clients is None:
            clients = self._local.clients = {}
        if name not in clients:
            clients[name] = self._service.get_table_client(self._prefix + name)
        return clients[name]

    # Table Storage has no null: an unset class is stored as "".
    @staticmethod
    def _to_entity(patch: dict[str, Any]) -> dict[str, Any]:
        return {k: ("" if k == "kast" and v is None else v) for k, v in patch.items()}

    @staticmethod
    def _from_entity(entity: dict[str, Any]) -> dict[str, Any]:
        row = {k: v for k, v in entity.items() if k not in ("PartitionKey", "RowKey")}
        if row.get("kast") == "":
            row["kast"] = None
        return complete(row)

    def state(self, meeting: str, since: Optional[str] = None) -> dict[int, dict[str, Any]]:
        query, params = "PartitionKey eq @meeting", {"meeting": meeting}
        if since is not None:
            # ISO timestamps of one format compare correctly as strings.
            query += " and updatedAt ge @since"
            params["since"] = since
        rows = self._table(CURRENT_TABLE).query_entities(query, parameters=params)
        return {int(e["RowKey"]): self._from_entity(e) for e in rows}

    def apply(self, meeting: str, corridor: int, patch: dict[str, Any],
              op_id: str, client_ts: str) -> dict[str, Any]:
        from azure.core.exceptions import ResourceExistsError
        from azure.data.tables import UpdateMode

        server_ts = _now()
        try:
            self._table(HISTORY_TABLE).create_entity({
                "PartitionKey": meeting,
                "RowKey": f"{_row(corridor)}_{op_id}",
                "corridor": corridor,
                "patch": json.dumps(patch, ensure_ascii=False),
                "clientTs": client_ts,
                "serverTs": server_ts,
            })
        except ResourceExistsError:
            pass   # a retry of a write whose history row already landed
        self._table(CURRENT_TABLE).upsert_entity(
            {"PartitionKey": meeting, "RowKey": _row(corridor),
             **self._to_entity(patch), "updatedAt": server_ts},
            mode=UpdateMode.MERGE)
        entity = self._table(CURRENT_TABLE).get_entity(meeting, _row(corridor))
        return self._from_entity(entity)

    def reset(self, meeting: str) -> int:
        count = 0
        for name in (CURRENT_TABLE, HISTORY_TABLE):
            table = self._table(name)
            for entity in list(table.query_entities(
                    "PartitionKey eq @meeting", parameters={"meeting": meeting},
                    select=["PartitionKey", "RowKey"])):
                table.delete_entity(entity["PartitionKey"], entity["RowKey"])
                count += name == CURRENT_TABLE
        return count

    def dump(self) -> dict[str, Any]:
        current = [{"meeting": e["PartitionKey"], "corridor": int(e["RowKey"]),
                    **self._from_entity(e)}
                   for e in self._table(CURRENT_TABLE).list_entities()]
        history = [{"meeting": e["PartitionKey"], "corridor": e["corridor"],
                    "patch": json.loads(e["patch"]), "opId": e["RowKey"].split("_", 1)[1],
                    "clientTs": e["clientTs"], "serverTs": e["serverTs"]}
                   for e in self._table(HISTORY_TABLE).list_entities()]
        history.sort(key=lambda h: h["serverTs"])
        return {"current": current, "history": history, "dumpedAt": _now()}


def open_store(data_dir: Path) -> Store:
    """TableStore when a connection string is set, else a FileStore in `data_dir`."""
    connection = os.environ.get("CONSENSUS_TABLES_CONNECTION")
    if connection:
        return TableStore(connection)
    return FileStore(data_dir)
