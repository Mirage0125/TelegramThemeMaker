import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path
from types import SimpleNamespace

from UpdateManager import (
    PRESERVED_ROOT_ITEMS,
    UpdateError,
    _install_requirements,
    _safe_member_path,
    _save_update_state,
    _stage_archive,
    recover_dependency_overlay,
    recover_update_transaction,
    _begin_update_transaction,
    _write_transaction_journal,
)


class UpdaterSafetyTests(unittest.TestCase):
    def test_assets_and_dependency_overlay_are_preserved_by_updater(self):
        self.assertIn("assets", PRESERVED_ROOT_ITEMS)
        self.assertIn(".update-packages", PRESERVED_ROOT_ITEMS)
        self.assertIn(".update-packages.rollback", PRESERVED_ROOT_ITEMS)
        self.assertIn(".update-transaction", PRESERVED_ROOT_ITEMS)

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
                archive.writestr("TelegramThemeMaker/.update-packages/old_package.py", "OLD = True")
                archive.writestr("TelegramThemeMaker/.update-packages.rollback/backup.py", "BACKUP = True")
                archive.writestr("TelegramThemeMaker/.update-packages-stage-abandoned/partial.py", "BROKEN = True")

            staged = _stage_archive(archive_path, root / "stage", "3.9.0")
            self.assertTrue((staged / "bot.py").exists())
            self.assertEqual((staged / "defaults" / "welcome.png").read_bytes(), b"default image")
            self.assertFalse((staged / "assets" / "welcome.png").exists())
            self.assertFalse((staged / ".update-packages").exists())
            self.assertFalse((staged / ".update-packages.rollback").exists())
            self.assertFalse((staged / ".update-packages-stage-abandoned").exists())

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

    def test_failed_pip_install_keeps_previous_dependency_overlay_and_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("example-package==1.0\n", encoding="utf-8")
            active = root / ".update-packages"
            active.mkdir()
            (active / "previous_package.py").write_text("VERSION = 'old'\n", encoding="utf-8")
            venv_package = root / ".venv" / "Lib" / "site-packages"
            venv_package.mkdir(parents=True)
            (venv_package / "keep.txt").write_text("base environment", encoding="utf-8")
            messages = []

            def fail_after_partial_install(command, **kwargs):
                target = Path(command[command.index("--target") + 1])
                (target / "partially_installed.py").write_text("BROKEN = True\n", encoding="utf-8")
                self.assertIn("--ignore-installed", command)
                self.assertIn(str(root / "requirements.txt"), command)
                return SimpleNamespace(returncode=1, stderr="simulated pip failure", stdout="")

            with patch("UpdateManager.subprocess.run", side_effect=fail_after_partial_install):
                with self.assertRaisesRegex(UpdateError, "текущий сохранён"):
                    _install_requirements(root, messages.append)

            self.assertEqual(
                (active / "previous_package.py").read_text(encoding="utf-8"),
                "VERSION = 'old'\n",
            )
            self.assertFalse((active / "partially_installed.py").exists())
            self.assertEqual(
                (venv_package / "keep.txt").read_text(encoding="utf-8"),
                "base environment",
            )
            self.assertEqual(list(root.glob(".update-packages-stage-*")), [])
            self.assertTrue(any("отдельный временный каталог" in item for item in messages))

    def test_successful_pip_install_atomically_replaces_dependency_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("example-package==2.0\n", encoding="utf-8")
            active = root / ".update-packages"
            active.mkdir()
            (active / "previous_package.py").write_text("VERSION = 'old'\n", encoding="utf-8")

            def successful_install(command, **kwargs):
                target = Path(command[command.index("--target") + 1])
                (target / "new_package.py").write_text("VERSION = 'new'\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with patch("UpdateManager.subprocess.run", side_effect=successful_install):
                _install_requirements(root, lambda message: None)

            self.assertTrue((active / "new_package.py").is_file())
            self.assertFalse((active / "previous_package.py").exists())
            self.assertFalse((root / ".update-packages.rollback").exists())
            self.assertEqual(list(root.glob(".update-packages-stage-*")), [])

    def test_failed_overlay_switch_restores_the_previous_dependency_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("example-package==2.0\n", encoding="utf-8")
            active = root / ".update-packages"
            active.mkdir()
            (active / "previous_package.py").write_text("VERSION = 'old'\n", encoding="utf-8")
            original_replace = __import__("os").replace
            replace_calls = 0

            def fail_second_replace(source, destination):
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 2:
                    raise OSError("simulated activation failure")
                return original_replace(source, destination)

            def successful_install(command, **kwargs):
                target = Path(command[command.index("--target") + 1])
                (target / "new_package.py").write_text("VERSION = 'new'\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with (
                patch("UpdateManager.subprocess.run", side_effect=successful_install),
                patch("UpdateManager.os.replace", side_effect=fail_second_replace),
            ):
                with self.assertRaisesRegex(UpdateError, "прежний набор сохранён"):
                    _install_requirements(root, lambda message: None)

            self.assertEqual(replace_calls, 3)
            self.assertEqual(
                (active / "previous_package.py").read_text(encoding="utf-8"),
                "VERSION = 'old'\n",
            )
            self.assertFalse((active / "new_package.py").exists())
            self.assertFalse((root / ".update-packages.rollback").exists())
            self.assertEqual(list(root.glob(".update-packages-stage-*")), [])

    def test_interrupted_overlay_switch_recovers_previous_set_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / ".update-packages.rollback"
            backup.mkdir()
            (backup / "previous_package.py").write_text("VERSION = 'old'\n", encoding="utf-8")
            abandoned = root / ".update-packages-stage-abandoned"
            abandoned.mkdir()
            (abandoned / "partial.py").write_text("BROKEN = True\n", encoding="utf-8")

            recover_dependency_overlay(root, lambda message: None)

            active = root / ".update-packages"
            self.assertTrue((active / "previous_package.py").is_file())
            self.assertFalse(backup.exists())
            self.assertFalse(abandoned.exists())



    def test_interrupted_project_and_dependency_update_rolls_back_as_one_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "new-release"
            staged.mkdir()
            (staged / "bot.py").write_text("NEW_BOT = True\n", encoding="utf-8")
            (staged / "VERSION.txt").write_text("3.10.0\n", encoding="utf-8")
            (staged / "requirements.txt").write_text("example-package==2.0\n", encoding="utf-8")

            (root / "bot.py").write_text("OLD_BOT = True\n", encoding="utf-8")
            (root / "VERSION.txt").write_text("3.9.0\n", encoding="utf-8")
            (root / "requirements.txt").write_text("example-package==1.0\n", encoding="utf-8")
            active = root / ".update-packages"
            active.mkdir()
            (active / "previous.py").write_text("OLD_DEPENDENCY = True\n", encoding="utf-8")

            transaction = _begin_update_transaction(root, staged)
            journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
            journal["overlay_update"] = True
            _write_transaction_journal(transaction, journal)

            # Simulate a crash after new dependencies and some project files became active.
            backup_overlay = transaction / "dependency-overlay-backup"
            active.rename(backup_overlay)
            active.mkdir()
            (active / "new.py").write_text("NEW_DEPENDENCY = True\n", encoding="utf-8")
            (root / "bot.py").write_text("NEW_BOT = True\n", encoding="utf-8")
            (root / "VERSION.txt").write_text("3.10.0\n", encoding="utf-8")
            (root / "requirements.txt").write_text("example-package==2.0\n", encoding="utf-8")

            self.assertTrue(recover_update_transaction(root))

            self.assertEqual((root / "bot.py").read_text(encoding="utf-8"), "OLD_BOT = True\n")
            self.assertEqual((root / "VERSION.txt").read_text(encoding="utf-8"), "3.9.0\n")
            self.assertEqual(
                (root / "requirements.txt").read_text(encoding="utf-8"),
                "example-package==1.0\n",
            )
            self.assertTrue((active / "previous.py").is_file())
            self.assertFalse((active / "new.py").exists())
            self.assertFalse(transaction.exists())

    def test_interrupted_update_without_previous_overlay_removes_partial_new_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "new-release"
            staged.mkdir()
            (staged / "bot.py").write_text("NEW_BOT = True\n", encoding="utf-8")
            (root / "bot.py").write_text("OLD_BOT = True\n", encoding="utf-8")

            transaction = _begin_update_transaction(root, staged)
            journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
            journal["overlay_update"] = True
            journal["overlay_existed"] = False
            _write_transaction_journal(transaction, journal)

            active = root / ".update-packages"
            active.mkdir()
            (active / "partial.py").write_text("PARTIAL = True\n", encoding="utf-8")
            (root / "bot.py").write_text("NEW_BOT = True\n", encoding="utf-8")

            recover_update_transaction(root)

            self.assertEqual((root / "bot.py").read_text(encoding="utf-8"), "OLD_BOT = True\n")
            self.assertFalse(active.exists())
            self.assertFalse(transaction.exists())

    def test_committed_transaction_keeps_new_files_and_only_cleans_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "new-release"
            staged.mkdir()
            (staged / "bot.py").write_text("NEW_BOT = True\n", encoding="utf-8")
            (root / "bot.py").write_text("NEW_BOT = True\n", encoding="utf-8")

            transaction = _begin_update_transaction(root, staged)
            journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
            journal["phase"] = "committed"
            _write_transaction_journal(transaction, journal)

            self.assertFalse(recover_update_transaction(root))
            self.assertEqual((root / "bot.py").read_text(encoding="utf-8"), "NEW_BOT = True\n")
            self.assertFalse(transaction.exists())

    def test_pending_transaction_with_missing_backup_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transaction = root / ".update-transaction"
            (transaction / "files").mkdir(parents=True)
            _write_transaction_journal(
                transaction,
                {
                    "format": 1,
                    "phase": "pending",
                    "files": [{"path": "bot.py", "existed": True}],
                    "overlay_existed": False,
                    "overlay_update": False,
                },
            )

            with self.assertRaisesRegex(UpdateError, "резервная копия"):
                recover_update_transaction(root)
            self.assertTrue(transaction.exists())

    def test_unsafe_archive_paths_are_rejected(self):
        for path in ("../outside.txt", "/absolute.txt", "TelegramThemeMaker/../../outside.txt"):
            with self.subTest(path=path):
                with self.assertRaises(Exception):
                    _safe_member_path(path)


if __name__ == "__main__":
    unittest.main()
