import tempfile
import unittest
import zipfile
from pathlib import Path

from UpdateManager import PRESERVED_ROOT_ITEMS, _safe_member_path, _stage_archive


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
                archive.writestr("TelegramThemeMaker/VERSION.txt", "3.8.0")
                archive.writestr("TelegramThemeMaker/requirements.txt", "aiogram>=3.13,<4.0")
                archive.writestr("TelegramThemeMaker/assets/welcome.png", b"replacement image")

            staged = _stage_archive(archive_path, root / "stage", "3.8.0")
            self.assertTrue((staged / "bot.py").exists())
            self.assertFalse((staged / "assets" / "welcome.png").exists())

    def test_unsafe_archive_paths_are_rejected(self):
        for path in ("../outside.txt", "/absolute.txt", "TelegramThemeMaker/../../outside.txt"):
            with self.subTest(path=path):
                with self.assertRaises(Exception):
                    _safe_member_path(path)


if __name__ == "__main__":
    unittest.main()
