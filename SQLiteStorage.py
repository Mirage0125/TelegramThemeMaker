"""Small persistent FSM storage for aiogram, backed by the Python standard library."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey


class SQLiteStorage(BaseStorage):
    """Persist aiogram FSM state/data locally without an external database service."""

    def __init__(self, database: str | Path) -> None:
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = sqlite3.connect(
            self.path, timeout=10, check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA busy_timeout=10000")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fsm_sessions (
                storage_key TEXT PRIMARY KEY,
                state TEXT,
                data_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._connection.commit()

    @staticmethod
    def _key(key: StorageKey) -> str:
        # Include every StorageKey field so topics, business chats and bots
        # cannot accidentally share a session.
        return json.dumps(
            [
                key.bot_id,
                key.chat_id,
                key.user_id,
                key.thread_id,
                key.business_connection_id,
                key.destiny,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SQLiteStorage is already closed.")
        return self._connection

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        value = state.state if isinstance(state, State) else state
        db = self._db()
        with db:
            db.execute(
                """
                INSERT INTO fsm_sessions (storage_key, state, data_json)
                VALUES (?, ?, '{}')
                ON CONFLICT(storage_key) DO UPDATE SET state = excluded.state
                """,
                (self._key(key), value),
            )

    async def get_state(self, key: StorageKey) -> str | None:
        row = self._db().execute(
            "SELECT state FROM fsm_sessions WHERE storage_key = ?",
            (self._key(key),),
        ).fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            raise TypeError(f"FSM data must be mapping-like, got {type(data).__name__}.")
        payload = json.dumps(
            dict(data),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        db = self._db()
        with db:
            db.execute(
                """
                INSERT INTO fsm_sessions (storage_key, state, data_json)
                VALUES (?, NULL, ?)
                ON CONFLICT(storage_key) DO UPDATE SET data_json = excluded.data_json
                """,
                (self._key(key), payload),
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = self._db().execute(
            "SELECT data_json FROM fsm_sessions WHERE storage_key = ?",
            (self._key(key),),
        ).fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    async def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
