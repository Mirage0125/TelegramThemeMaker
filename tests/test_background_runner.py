import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from BackgroundRunner import acquire_instance_lock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstanceLockTests(unittest.TestCase):
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
