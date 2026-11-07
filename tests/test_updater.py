import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from UpdateManager import PRESERVED_ROOT_ITEMS, _safe_member_path, _save_update_state, _stage_archive


class UpdaterSafetyTests(unittest.TestCase):
    def test_assets_are_preserved_by_updater(self):
        self.assertIn("assets", PRESERVED_ROOT_ITEMS)

    def test_archive_staging_skips_assets_but_keeps_application_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "release.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("TelegramThemeMaker/bot.py", "# bot")
                archive.writestr("TelegramThemeMaker/BackgroundRunner.py", "# runner")
                archive.writestr("TelegramThemeMaker/UpdateManager.py", "# updater")
                archive.writestr("TelegramThemeMaker/SQLiteStorage.py", "# storage")
                archive.writestr("TelegramThemeMaker/Localization.py", "# language preferences")
                archive.writestr("TelegramThemeMaker/VERSION.txt", "3.9.0")
                archive.writestr("TelegramThemeMaker/requirements.txt", "aiogram>=3.13,<4.0")
                archive.writestr("TelegramThemeMaker/defaults/welcome.png", b"default image")
                archive.writestr("TelegramThemeMaker/assets/welcome.png", b"replacement image")

            staged = _stage_archive(archive_path, root / "stage", "3.9.0")
            self.assertTrue((staged / "bot.py").exists())
            self.assertEqual((staged / "defaults" / "welcome.png").read_bytes(), b"default image")
            self.assertFalse((staged / "assets" / "welcome.png").exists())

    def test_update_state_write_failure_does_not_raise_or_leave_partial_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / ".update-state.json"
            temporary_path = root / ".update-state.json.tmp"
            messages = []

            self.assertTrue(_save_update_state(state_path, 123456, messages.append))
            self.assertEqual(
                __import__("json").loads(state_path.read_text(encoding="utf-8")),
                {"last_successful_check": 123456},
            )

            state_path.unlink()
            with patch("UpdateManager.os.replace", side_effect=OSError("disk full")):
                self.assertFalse(_save_update_state(state_path, 123457, messages.append))

            self.assertFalse(state_path.exists())
            self.assertFalse(temporary_path.exists())
            self.assertTrue(any("обновление не будет отменено" in item for item in messages))

    def test_unsafe_archive_paths_are_rejected(self):
        for path in ("../outside.txt", "/absolute.txt", "TelegramThemeMaker/../../outside.txt"):
            with self.subTest(path=path):
                with self.assertRaises(Exception):
                    _safe_member_path(path)


if __name__ == "__main__":
    unittest.main()
