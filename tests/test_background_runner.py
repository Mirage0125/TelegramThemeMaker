import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import BackgroundRunner as runner
from BackgroundRunner import acquire_instance_lock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstanceLockTests(unittest.TestCase):
    def test_lock_conflict_is_logged_when_stdout_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "logs"
            log_file = log_dir / "bot.log"
            with patch.object(runner, "ROOT", root), \
                 patch.object(runner, "LOG_DIR", log_dir), \
                 patch.object(runner, "LOG_FILE", log_file), \
                 patch.object(
                     runner, "acquire_instance_lock",
                     side_effect=runner.AlreadyRunningError("already running"),
                 ), \
                 patch("sys.stdout", None), patch("sys.stderr", None):
                self.assertEqual(runner.main(), 0)

            contents = log_file.read_text(encoding="utf-8")
            self.assertIn("Запуск пропущен", contents)
            self.assertIn("already running", contents)

    def test_lock_failure_traceback_is_logged_when_stdout_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "logs"
            log_file = log_dir / "bot.log"
            with patch.object(runner, "ROOT", root), \
                 patch.object(runner, "LOG_DIR", log_dir), \
                 patch.object(runner, "LOG_FILE", log_file), \
                 patch.object(
                     runner, "acquire_instance_lock",
                     side_effect=OSError("simulated lock failure"),
                 ), \
                 patch("sys.stdout", None), patch("sys.stderr", None):
                self.assertEqual(runner.main(), 1)

            contents = log_file.read_text(encoding="utf-8")
            self.assertIn("Не удалось получить блокировку запуска", contents)
            self.assertIn("simulated lock failure", contents)
            self.assertIn("Traceback", contents)

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
