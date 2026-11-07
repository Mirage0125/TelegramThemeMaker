import json
import tempfile
import unittest
from pathlib import Path

from aiogram.fsm.storage.base import StorageKey

from SQLiteStorage import SQLiteStorage


class SQLiteStorageSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_all_data_returns_session_data_across_storage_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "fsm.sqlite3")
            try:
                first = StorageKey(bot_id=1, chat_id=10, user_id=10)
                second = StorageKey(bot_id=1, chat_id=20, user_id=20)
                await storage.set_data(first, {"wallpaper_path": "user_data/10/wallpaper_aaaaaaaaaaaa.jpg"})
                await storage.set_data(second, {"theme": {"name": "second"}})

                sessions = await storage.get_all_data()

                self.assertEqual(len(sessions), 2)
                self.assertIn(
                    {"wallpaper_path": "user_data/10/wallpaper_aaaaaaaaaaaa.jpg"},
                    sessions,
                )
                self.assertIn({"theme": {"name": "second"}}, sessions)
            finally:
                await storage.close()

    async def test_get_all_data_fails_closed_when_a_session_row_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "fsm.sqlite3")
            try:
                key = StorageKey(bot_id=1, chat_id=10, user_id=10)
                await storage.set_data(key, {"theme": {"name": "valid"}})
                with storage._db():
                    storage._db().execute(
                        "INSERT INTO fsm_sessions (storage_key, state, data_json) VALUES (?, NULL, ?)",
                        ("corrupt-session", "{broken"),
                    )

                with self.assertRaisesRegex(RuntimeError, "safely enumerate"):
                    await storage.get_all_data()
            finally:
                await storage.close()


if __name__ == "__main__":
    unittest.main()
