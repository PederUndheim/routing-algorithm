"""Where the verdicts live: Azure Table Storage, or a local file log.

Both keep the same two things:

    current   one row per (user, corridor): the verdict as it stands
    history   one row per write, never changed or removed: the patch, who
              sent it and when

History is written first. A write that dies between the two leaves a
history row and a stale current row, and the client - which retries until
it hears success - sends the same patch again. The retry carries the same
`op_id`, so it lands on the same history row rather than a second one, and
then brings `current` up to date. Nothing a reviewer saw as saved can be
missing from history, and current can always be rebuilt from it.

`TableStore` is production: three synchronous copies in the storage account
before Azure acknowledges a write, and partitioned by user so four people
writing at once never touch the same partition. `FileStore` is for running
locally and for the tests: an append-only JSON-lines log, fsynced per write,
replayed on start.

## Assignments

Which corridors each user is to review, as explicit id lists. The admin
script resolves regions to ids before upload (see validation_app/admin.py),
so the API knows nothing about regions. A user with no assignment row sees
every corridor; the test user always does.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from .verdicts import TEST_USER, complete


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store(Protocol):
    name: str

    def state(self, user: str) -> dict[int, dict[str, Any]]: ...
    def apply(self, user: str, corridor: int, patch: dict[str, Any],
              op_id: str, client_ts: str) -> dict[str, Any]: ...
    def reset(self, user: str) -> int: ...
    def assignment(self, user: str) -> Optional[list[int]]: ...
    def set_assignments(self, assignments: dict[str, list[int]]) -> None: ...
    def dump(self) -> dict[str, Any]: ...


# --- local ---------------------------------------------------------------

class FileStore:
    """An append-only log in `root/log.jsonl`, replayed into memory on start."""

    name = "file"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "log.jsonl"
        self.assignments_path = self.root / "assignments.json"
        self._lock = threading.Lock()
        self._current: dict[str, dict[int, dict[str, Any]]] = {}
        self._history: list[dict[str, Any]] = []
        self._ops: set[tuple[str, str]] = set()
        if self.log.exists():
            for line in self.log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._replay(json.loads(line))

    def _replay(self, event: dict[str, Any]) -> None:
        user = event["user"]
        if event["type"] == "reset":
            self._current.pop(user, None)
            self._history = [h for h in self._history if h["user"] != user]
            self._ops = {op for op in self._ops if op[0] != user}
            return
        self._history.append(event)
        self._ops.add((user, event["opId"]))
        verdict = self._current.setdefault(user, {}).setdefault(event["corridor"], {})
        verdict.update(event["patch"])
        verdict["updatedAt"] = event["serverTs"]

    def _append(self, event: dict[str, Any]) -> None:
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def state(self, user: str) -> dict[int, dict[str, Any]]:
        with self._lock:
            return {cid: complete(v) for cid, v in self._current.get(user, {}).items()}

    def apply(self, user: str, corridor: int, patch: dict[str, Any],
              op_id: str, client_ts: str) -> dict[str, Any]:
        with self._lock:
            if (user, op_id) not in self._ops:
                event = {"type": "patch", "user": user, "corridor": corridor, "patch": patch,
                         "opId": op_id, "clientTs": client_ts, "serverTs": _now()}
                self._append(event)
                self._replay(event)
            return complete(self._current[user][corridor])

    def reset(self, user: str) -> int:
        with self._lock:
            count = len(self._current.get(user, {}))
            event = {"type": "reset", "user": user, "serverTs": _now()}
            self._append(event)
            self._replay(event)
            return count

    def _assignments(self) -> dict[str, list[int]]:
        if not self.assignments_path.exists():
            return {}
        return json.loads(self.assignments_path.read_text(encoding="utf-8"))

    def assignment(self, user: str) -> Optional[list[int]]:
        if user == TEST_USER:
            return None
        return self._assignments().get(user)

    def set_assignments(self, assignments: dict[str, list[int]]) -> None:
        tmp = self.assignments_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(assignments), encoding="utf-8")
        os.replace(tmp, self.assignments_path)

    def dump(self) -> dict[str, Any]:
        with self._lock:
            current = [{"user": u, "corridor": cid, **complete(v)}
                       for u, rows in self._current.items() for cid, v in rows.items()]
            return {"current": current, "history": list(self._history),
                    "assignments": self._assignments(), "dumpedAt": _now()}


# --- Azure ---------------------------------------------------------------

CURRENT_TABLE = "current"
HISTORY_TABLE = "history"
CONFIG_TABLE = "config"


def _row(corridor: int) -> str:
    return f"{corridor:04d}"


class TableStore:
    """Azure Table Storage. PartitionKey is always the user."""

    name = "azure-tables"

    def __init__(self, connection_string: str, prefix: str = "val") -> None:
        from azure.data.tables import TableServiceClient

        self._service = TableServiceClient.from_connection_string(connection_string)
        self._prefix = prefix   # tables are valcurrent, valhistory, valconfig
        for table in (CURRENT_TABLE, HISTORY_TABLE, CONFIG_TABLE):
            self._service.create_table_if_not_exists(prefix + table)
        # A TableClient per thread: the server answers each request on its
        # own thread, and the SDK does not promise a shared client is safe.
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
        verdict = {k: v for k, v in entity.items() if k not in ("PartitionKey", "RowKey")}
        if verdict.get("kast") == "":
            verdict["kast"] = None
        return complete(verdict)

    def state(self, user: str) -> dict[int, dict[str, Any]]:
        rows = self._table(CURRENT_TABLE).query_entities(
            "PartitionKey eq @user", parameters={"user": user})
        return {int(e["RowKey"]): self._from_entity(e) for e in rows}

    def apply(self, user: str, corridor: int, patch: dict[str, Any],
              op_id: str, client_ts: str) -> dict[str, Any]:
        from azure.core.exceptions import ResourceExistsError
        from azure.data.tables import UpdateMode

        server_ts = _now()
        try:
            self._table(HISTORY_TABLE).create_entity({
                "PartitionKey": user,
                "RowKey": f"{_row(corridor)}_{op_id}",
                "corridor": corridor,
                "patch": json.dumps(patch, ensure_ascii=False),
                "clientTs": client_ts,
                "serverTs": server_ts,
            })
        except ResourceExistsError:
            pass   # a retry of a write whose history row already landed
        self._table(CURRENT_TABLE).upsert_entity(
            {"PartitionKey": user, "RowKey": _row(corridor),
             **self._to_entity(patch), "updatedAt": server_ts},
            mode=UpdateMode.MERGE)
        entity = self._table(CURRENT_TABLE).get_entity(user, _row(corridor))
        return self._from_entity(entity)

    def reset(self, user: str) -> int:
        count = 0
        for name in (CURRENT_TABLE, HISTORY_TABLE):
            table = self._table(name)
            for entity in list(table.query_entities(
                    "PartitionKey eq @user", parameters={"user": user},
                    select=["PartitionKey", "RowKey"])):
                table.delete_entity(entity["PartitionKey"], entity["RowKey"])
                count += name == CURRENT_TABLE
        return count

    def assignment(self, user: str) -> Optional[list[int]]:
        from azure.core.exceptions import ResourceNotFoundError

        if user == TEST_USER:
            return None
        try:
            entity = self._table(CONFIG_TABLE).get_entity("assignment", user)
        except ResourceNotFoundError:
            return None
        return json.loads(entity["ids"])

    def set_assignments(self, assignments: dict[str, list[int]]) -> None:
        table = self._table(CONFIG_TABLE)
        existing = {e["RowKey"] for e in table.query_entities(
            "PartitionKey eq 'assignment'", select=["RowKey"])}
        for user, ids in assignments.items():
            table.upsert_entity({"PartitionKey": "assignment", "RowKey": user,
                                 "ids": json.dumps(ids), "updatedAt": _now()})
        for user in existing - set(assignments):
            table.delete_entity("assignment", user)

    def dump(self) -> dict[str, Any]:
        current = [{"user": e["PartitionKey"], "corridor": int(e["RowKey"]),
                    **self._from_entity(e)}
                   for e in self._table(CURRENT_TABLE).list_entities()]
        history = [{"user": e["PartitionKey"], "corridor": e["corridor"],
                    "patch": json.loads(e["patch"]), "opId": e["RowKey"].split("_", 1)[1],
                    "clientTs": e["clientTs"], "serverTs": e["serverTs"]}
                   for e in self._table(HISTORY_TABLE).list_entities()]
        history.sort(key=lambda h: h["serverTs"])
        assignments = {e["RowKey"]: json.loads(e["ids"]) for e in
                       self._table(CONFIG_TABLE).query_entities("PartitionKey eq 'assignment'")}
        return {"current": current, "history": history,
                "assignments": assignments, "dumpedAt": _now()}


def open_store(data_dir: Path) -> Store:
    """TableStore when a connection string is set, else a FileStore in `data_dir`."""
    connection = os.environ.get("VALIDATION_TABLES_CONNECTION")
    if connection:
        return TableStore(connection)
    return FileStore(data_dir)
