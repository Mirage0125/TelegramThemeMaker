import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import UpdateManager
from UpdateManager import (
    PRESERVED_ROOT_ITEMS,
    _restore_backup_file,
    _safe_member_path,
    _stage_archive,
)


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

    def test_backup_restore_replaces_from_a_temp_file_beside_the_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "install"
            backup_dir = root / "system-temp" / "backup"
            install_dir.mkdir()
            backup_dir.mkdir(parents=True)
            target = install_dir / "bot.py"
            backup = backup_dir / "bot.py"
            target.write_text("new version", encoding="utf-8")
            backup.write_text("previous version", encoding="utf-8")

            original_replace = os.replace
            replacements = []

            def assert_same_parent(source, destination):
                source_path = Path(source)
                destination_path = Path(destination)
                replacements.append((source_path, destination_path))
                self.assertEqual(source_path.parent, destination_path.parent)
                return original_replace(source, destination)

            with patch("UpdateManager.os.replace", side_effect=assert_same_parent):
                _restore_backup_file(target, backup)

            self.assertEqual(target.read_text(encoding="utf-8"), "previous version")
            self.assertEqual(len(replacements), 1)
            self.assertTrue(replacements[0][0].name.endswith(".restore-tmp"))
            self.assertTrue(backup.exists())

    def test_unsafe_archive_paths_are_rejected(self):
        for path in ("../outside.txt", "/absolute.txt", "TelegramThemeMaker/../../outside.txt"):
            with self.subTest(path=path):
                with self.assertRaises(Exception):
                    _safe_member_path(path)


if __name__ == "__main__":
    unittest.main()
