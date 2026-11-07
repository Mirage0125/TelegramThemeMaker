import os
import subprocess
import sys
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import BackgroundRunner
import tempfile
import unittest
from pathlib import Path

from BackgroundRunner import AlreadyRunningError, acquire_instance_lock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstanceLockTests(unittest.TestCase):
    def test_early_lock_messages_are_written_to_the_log_file(self):
        scenarios = (
            (AlreadyRunningError("already running"), 0, "Запуск пропущен"),
            (PermissionError("access denied"), 1, "Не удалось получить блокировку запуска"),
        )

        for failure, expected_code, expected_message in scenarios:
            with self.subTest(failure=type(failure).__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    log_dir = root / "logs"
                    log_file = log_dir / "bot.log"
                    output = io.StringIO()

                    with (
                        patch.object(BackgroundRunner, "ROOT", root),
                        patch.object(BackgroundRunner, "LOG_DIR", log_dir),
                        patch.object(BackgroundRunner, "LOG_FILE", log_file),
                        patch.object(
                            BackgroundRunner,
                            "acquire_instance_lock",
                            side_effect=failure,
                        ),
                    ):
                        with redirect_stdout(output):
                            exit_code = BackgroundRunner.main()

                    self.assertEqual(exit_code, expected_code)
                    self.assertIn(expected_message, log_file.read_text(encoding="utf-8"))
                    self.assertEqual(output.getvalue(), "")

    def test_dependency_overlay_is_loaded_before_base_venv_packages(self):
        from UpdateManager import enable_dependency_overlay

        original_path = sys.path.copy()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            overlay = root / ".update-packages"
            overlay.mkdir()

            try:
                self.assertTrue(enable_dependency_overlay(root))
                self.assertEqual(Path(sys.path[0]), overlay.resolve())

                # Repeated activation must not add duplicate path entries.
                self.assertTrue(enable_dependency_overlay(root))
                self.assertEqual(Path(sys.path[0]).resolve(), overlay.resolve())
                occurrences = [
                    entry for entry in sys.path
                    if entry and os.path.samefile(entry, overlay)
                ]
                self.assertEqual(len(occurrences), 1)

                shutil = __import__("shutil")
                shutil.rmtree(overlay)
                self.assertFalse(enable_dependency_overlay(root))
            finally:
                sys.path[:] = original_path

    def test_second_process_cannot_acquire_lock_until_first_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / ".bot.lock"
            first_handle = acquire_instance_lock(lock_path)
            blocked_code = """
import sys
from pathlib import Path
from BackgroundRunner import AlreadyRunningError, acquire_instance_lock
try:
    handle = acquire_instance_lock(Path(sys.argv[1]))
except AlreadyRunningError:
    raise SystemExit(0)
handle.close()
raise SystemExit(1)
"""
            released_code = """
import sys
from pathlib import Path
from BackgroundRunner import AlreadyRunningError, acquire_instance_lock
try:
    handle = acquire_instance_lock(Path(sys.argv[1]))
except AlreadyRunningError:
    raise SystemExit(1)
handle.close()
raise SystemExit(0)
"""
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(PROJECT_ROOT)
            try:
                blocked = subprocess.run(
                    [sys.executable, "-c", blocked_code, str(lock_path)],
                    cwd=PROJECT_ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(
                    blocked.returncode,
                    0,
                    msg=f"Second process unexpectedly acquired the lock: {blocked.stderr}",
                )
            finally:
                first_handle.close()

            released = subprocess.run(
                [sys.executable, "-c", released_code, str(lock_path)],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(
                released.returncode,
                0,
                msg=f"Lock did not become available after release: {released.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
