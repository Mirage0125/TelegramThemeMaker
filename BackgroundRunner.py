"""Run the Telegram bot in the background and keep a local diagnostic log."""
from __future__ import annotations

import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "bot.log"
OLD_LOG_FILE = LOG_DIR / "bot.previous.log"


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)

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
            # Updating is best-effort: a temporary GitHub/network failure must
            # never prevent the already installed bot from starting.
            try:
                from UpdateManager import apply_update_if_available

                apply_update_if_available(ROOT, lambda message: print(f"[{timestamp()}] {message}"))
            except Exception as exc:
                print(
                    f"[{timestamp()}] Не удалось проверить или установить обновление; "
                    f"запускаю текущую версию: {exc}"
                )
                traceback.print_exc()

            runpy.run_path(str(ROOT / "bot.py"), run_name="__main__")
            print(f"[{timestamp()}] Процесс бота завершился.")
            return 0
        except BaseException:
            print(f"[{timestamp()}] Бот завершился с ошибкой:")
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
