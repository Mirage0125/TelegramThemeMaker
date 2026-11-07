"""Run the Telegram bot in the background and keep a local diagnostic log."""
from __future__ import annotations

import os
import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "bot.log"
OLD_LOG_FILE = LOG_DIR / "bot.previous.log"
LOCK_ENVIRONMENT_FLAG = "THEME_MAKER_RUNNER_LOCK_HELD"


class AlreadyRunningError(RuntimeError):
    """Raised when another process already owns this installation's lock."""


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def acquire_instance_lock(lock_path: Path):
    """Acquire an OS-level lock and return the open handle that keeps it alive."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)

    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise AlreadyRunningError(
            "This installation is already running in another process."
        ) from exc
    return handle


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    try:
        lock_handle = acquire_instance_lock(ROOT / ".bot.lock")
    except AlreadyRunningError as exc:
        with LOG_FILE.open("a", encoding="utf-8", buffering=1) as log:
            print(f"\n[{timestamp()}] Запуск пропущен: {exc}", file=log)
        return 0
    except Exception:
        with LOG_FILE.open("a", encoding="utf-8", buffering=1) as log:
            print(f"\n[{timestamp()}] Не удалось получить блокировку запуска:", file=log)
            traceback.print_exc(file=log)
        return 1

    try:
        # Keep the most recent log bounded so unattended operation cannot fill the disk.
        try:
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2 * 1024 * 1024:
                OLD_LOG_FILE.unlink(missing_ok=True)
                LOG_FILE.replace(OLD_LOG_FILE)
        except OSError:
            pass

        with LOG_FILE.open("a", encoding="utf-8", buffering=1) as log:
            sys.stdout = log
            sys.stderr = log
            print(f"\n[{timestamp()}] Запуск фонового процесса Theme Maker")
            try:
                # Make the already-held lock visible to UpdateManager and bot.py.
                os.environ[LOCK_ENVIRONMENT_FLAG] = "1"

                # Updating is best-effort, but the instance lock is already held:
                # two launches can never replace project files at the same time.
                try:
                    from UpdateManager import apply_update_if_available

                    apply_update_if_available(
                        ROOT, lambda message: print(f"[{timestamp()}] {message}")
                    )
                except Exception as exc:
                    print(
                        f"[{timestamp()}] Не удалось проверить или установить обновление; "
                        f"запускаю текущую версию: {exc}"
                    )
                    traceback.print_exc()

                from UpdateManager import enable_dependency_overlay

                if enable_dependency_overlay(ROOT):
                    print("[Updater] Используется изолированный набор обновлённых библиотек.")

                runpy.run_path(str(ROOT / "bot.py"), run_name="__main__")
                print(f"[{timestamp()}] Процесс бота завершился.")
                return 0
            except BaseException:
                print(f"[{timestamp()}] Бот завершился с ошибкой:")
                traceback.print_exc()
                return 1
    finally:
        os.environ.pop(LOCK_ENVIRONMENT_FLAG, None)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
