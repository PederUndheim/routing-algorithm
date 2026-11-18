"""The experts' verdicts from the validation app, read-only and live.

This is the one place the consensus app touches the validation app's data,
and it can only read:

    In Azure   the validation storage account's `valcurrent` table, through a
               table SAS with read permission only (deploy/consensus.sh makes
               it). No key or connection string to that account is given to
               this app, so it cannot write there even by mistake.
    Locally    a dump file from `python -m validation_app.admin backup` - by
               default the newest one in data/validation/backup.

Verdicts change while the meeting is on only if an expert edits theirs, so
a fetch is cached for CACHE_S: a room of pages polling at once is one query.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Protocol

CACHE_S = 20
FIELDS = ("kast", "sub", "size", "note", "doubt", "problematic", "updatedAt")


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    v = {k: row.get(k) for k in FIELDS}
    v["kast"] = v["kast"] or None          # Table Storage stores an unset class as ""
    v["sub"] = v["sub"] or 0
    v["size"] = v["size"] or 0
    v["note"] = v["note"] or ""
    v["doubt"] = bool(v["doubt"])
    v["problematic"] = bool(v["problematic"])
    return v


class Experts(Protocol):
    name: str

    def verdicts(self, experts: list[str]) -> dict[str, dict[int, dict[str, Any]]]: ...


class _Cached:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, ...], tuple[float, Any]] = {}

    def verdicts(self, experts: list[str]) -> dict[str, dict[int, dict[str, Any]]]:
        key = tuple(sorted(experts))
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_S:
                return hit[1]
        fresh = self._fetch(list(key))
        with self._lock:
            self._cache[key] = (time.monotonic(), fresh)
        return fresh

    def _fetch(self, experts: list[str]) -> dict[str, dict[int, dict[str, Any]]]:
        raise NotImplementedError


class TableExperts(_Cached):
    """valcurrent, through a read-only SAS."""

    name = "validation-tables"

    def __init__(self, endpoint: str, sas: str, table: str = "valcurrent") -> None:
        super().__init__()
        from azure.core.credentials import AzureSasCredential
        from azure.data.tables import TableClient

        self._client = TableClient(endpoint=endpoint, table_name=table,
                                   credential=AzureSasCredential(sas.lstrip("?")))
        self._client_lock = threading.Lock()

    def _fetch(self, experts: list[str]) -> dict[str, dict[int, dict[str, Any]]]:
        query = " or ".join(f"PartitionKey eq @u{i}" for i in range(len(experts)))
        params = {f"u{i}": e for i, e in enumerate(experts)}
        out: dict[str, dict[int, dict[str, Any]]] = {e: {} for e in experts}
        with self._client_lock:
            for e in self._client.query_entities(query, parameters=params):
                out[e["PartitionKey"]][int(e["RowKey"])] = _clean(e)
        return out


class FileExperts(_Cached):
    """A validation dump on disk, re-read when it changes."""

    name = "validation-file"

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = Path(path)

    def verdicts(self, experts: list[str]) -> dict[str, dict[int, dict[str, Any]]]:
        return self._fetch(experts)

    def _fetch(self, experts: list[str]) -> dict[str, dict[int, dict[str, Any]]]:
        dump = json.loads(self.path.read_text(encoding="utf-8"))
        out: dict[str, dict[int, dict[str, Any]]] = {e: {} for e in experts}
        for row in dump["current"]:
            if row["user"] in out:
                out[row["user"]][int(row["corridor"])] = _clean(row)
        return out


def newest_backup(folder: Path) -> Path | None:
    files = sorted(folder.glob("validering_*.json"))
    return files[-1] if files else None
