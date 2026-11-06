import tempfile
import unittest
from pathlib import Path

from aiogram.fsm.storage.base import StorageKey

from SQLiteStorage import SQLiteStorage


class SQLiteStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_and_data_survive_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "state.sqlite3"
            key = StorageKey(bot_id=1, chat_id=100, user_id=100)
            first = SQLiteStorage(database)
            await first.set_state(key, "ThemeStates:waiting_image")
            await first.set_data(
                key,
                {
                    "theme": {"background": "#112233", "accent": "#AABBCC"},
                    "image_palette": ["#112233", "#AABBCC"],
                    "wallpaper_path": "user_data/100/wallpaper.jpg",
                },
            )
            await first.close()

            second = SQLiteStorage(database)
            self.assertEqual(await second.get_state(key), "ThemeStates:waiting_image")
            self.assertEqual(
                await second.get_data(key),
                {
                    "theme": {"background": "#112233", "accent": "#AABBCC"},
                    "image_palette": ["#112233", "#AABBCC"],
                    "wallpaper_path": "user_data/100/wallpaper.jpg",
                },
            )
            await second.close()

    async def test_storage_keys_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "state.sqlite3")
            first = StorageKey(bot_id=1, chat_id=100, user_id=100)
            second = StorageKey(bot_id=1, chat_id=200, user_id=200)
            await storage.set_data(first, {"theme": "first"})
            await storage.set_data(second, {"theme": "second"})
            self.assertEqual(await storage.get_data(first), {"theme": "first"})
            self.assertEqual(await storage.get_data(second), {"theme": "second"})
            await storage.close()

    async def test_empty_values_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "state.sqlite3")
            key = StorageKey(bot_id=1, chat_id=100, user_id=100)
            await storage.set_state(key, "editing")
            await storage.set_state(key, None)
            await storage.set_data(key, {})
            self.assertIsNone(await storage.get_state(key))
            self.assertEqual(await storage.get_data(key), {})
            await storage.close()


if __name__ == "__main__":
    unittest.main()
