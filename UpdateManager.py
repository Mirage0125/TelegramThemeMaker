"""Download and safely apply published GitHub releases for Telegram Theme Maker.

The updater runs before bot.py starts. It uses only the Python standard library,
keeps local secrets/data intact, verifies the release checksum, and rolls back
project-file changes if applying the update fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

GITHUB_REPOSITORY = "Mirage0125/TelegramThemeMaker"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
USER_AGENT = "TelegramThemeMaker-Updater/1.0"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 2_000
MAX_UNPACKED_BYTES = 250 * 1024 * 1024
PRESERVED_ROOT_ITEMS = {
    ".env",
    ".venv",
    "venv",
    "env",
    "logs",
    "user_data",
    ".bot.lock",
    ".update-state.json",
    "__pycache__",
}
REQUIRED_FILES = {"bot.py", "BackgroundRunner.py", "UpdateManager.py", "VERSION.txt", "requirements.txt"}
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class UpdateError(RuntimeError):
    """Raised when a release cannot be validated or safely installed."""


def _log(log, message: str) -> None:
    log(f"[Updater] {message}")


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").strip()


def _request(url: str, *, timeout: int = 20, max_bytes: int | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/octet-stream, text/plain",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if max_bytes is not None and length and int(length) > max_bytes:
            raise UpdateError("Размер загружаемого файла превышает допустимый лимит.")
        data = response.read((max_bytes + 1) if max_bytes is not None else -1)
    if max_bytes is not None and len(data) > max_bytes:
        raise UpdateError("Размер загружаемого файла превышает допустимый лимит.")
    return data


def _latest_release(log) -> dict | None:
    try:
        raw = _request(LATEST_RELEASE_API, timeout=15, max_bytes=2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _log(log, "На GitHub пока нет опубликованных релизов. Автообновление ожидает первый релиз.")
            return None
        raise UpdateError(f"GitHub вернул HTTP {exc.code} при проверке релизов.") from exc
    except (OSError, TimeoutError) as exc:
        raise UpdateError(f"Не удалось проверить GitHub: {exc}") from exc
    try:
        release = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub вернул некорректные данные релиза.") from exc
    if release.get("draft") or release.get("prerelease"):
        return None
    return release


def _asset(assets: list[dict], name: str) -> dict | None:
    return next((item for item in assets if item.get("name") == name), None)


def _checksum_value(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace").strip()
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise UpdateError("Файл контрольной суммы релиза имеет неверный формат.")
    return match.group(1).lower()


def _safe_member_path(name: str) -> tuple[str, ...]:
    if "\\" in name:
        raise UpdateError("В архиве обнаружен недопустимый путь.")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise UpdateError("В архиве обнаружен небезопасный путь.")
    if path.parts[0] != "TelegramThemeMaker":
        raise UpdateError("Структура ZIP не соответствует формату релиза.")
    return path.parts[1:]


def _stage_archive(archive_path: Path, destination: Path, expected_version: str) -> Path:
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile as exc:
        raise UpdateError("Скачанный ZIP-архив повреждён.") from exc

    staged_root = destination / "new-files"
    staged_root.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, ...]] = set()
    total_unpacked = 0
    written_files: set[str] = set()

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise UpdateError("В архиве слишком много файлов.")
        for info in infos:
            relative_parts = _safe_member_path(info.filename)
            if not relative_parts:
                continue
            normalized = tuple(part.casefold() for part in relative_parts)
            if normalized in seen:
                raise UpdateError("В архиве есть повторяющиеся пути.")
            seen.add(normalized)

            if relative_parts[0].casefold() in PRESERVED_ROOT_ITEMS:
                continue
            if relative_parts[0].startswith(".env"):
                continue

            # Reject symlinks and other special files instead of extracting them.
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = mode & 0o170000
            if file_type not in (0, 0o100000, 0o040000):
                raise UpdateError("В архиве обнаружен специальный или ссылочный файл.")

            target = staged_root.joinpath(*relative_parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            total_unpacked += info.file_size
            if total_unpacked > MAX_UNPACKED_BYTES:
                raise UpdateError("Распакованный релиз превышает допустимый размер.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            written_files.add(PurePosixPath(*relative_parts).as_posix())

    missing = REQUIRED_FILES - written_files
    if missing:
        raise UpdateError("В архиве отсутствуют обязательные файлы: " + ", ".join(sorted(missing)))

    packaged_version = _read_text(staged_root / "VERSION.txt")
    if packaged_version != expected_version:
        raise UpdateError("Версия внутри ZIP не совпадает с версией GitHub-релиза.")
    return staged_root


def _apply_staged_files(root: Path, staged_root: Path, backup_root: Path) -> tuple[list[tuple[Path, Path | None]], bool]:
    changed: list[tuple[Path, Path | None]] = []
    requirements_path = root / "requirements.txt"
    old_requirements = requirements_path.read_bytes() if requirements_path.exists() else b""
    new_requirements = (staged_root / "requirements.txt").read_bytes()
    requirements_changed = old_requirements != new_requirements

    files = sorted(path for path in staged_root.rglob("*") if path.is_file())
    try:
        for staged_file in files:
            relative = staged_file.relative_to(staged_root)
            if relative.parts[0].casefold() in PRESERVED_ROOT_ITEMS or relative.parts[0].casefold().startswith(".env"):
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = backup_root / relative
            backup_path: Path | None = None
            if target.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                backup_path = backup
            temporary_target = target.with_name(target.name + ".update-tmp")
            shutil.copy2(staged_file, temporary_target)
            os.replace(temporary_target, target)
            changed.append((target, backup_path))
    except Exception:
        for target, backup_path in reversed(changed):
            try:
                if backup_path and backup_path.exists():
                    os.replace(backup_path, target)
                else:
                    target.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return changed, requirements_changed


def _install_requirements(root: Path, log) -> None:
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(root / "requirements.txt")]
    _log(log, "Обновился список библиотек; устанавливаю зависимости в локальное виртуальное окружение…")
    result = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "pip завершился с ошибкой").strip()[-1800:]
        raise UpdateError("Не удалось обновить библиотеки: " + detail)


def apply_update_if_available(root: Path, log) -> bool:
    """Check for a newer stable release and install it. Return True if updated."""
    root = root.resolve()
    state_path = root / ".update-state.json"
    now = int(time.time())
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        last_check = int(state.get("last_successful_check", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        last_check = 0

    if now - last_check < CHECK_INTERVAL_SECONDS:
        _log(log, "Проверка обновлений уже выполнялась недавно; пропускаю повторный запрос.")
        return False

    current_text = _read_text(root / "VERSION.txt") if (root / "VERSION.txt").exists() else "0.0.0"
    current_version = _version_tuple(current_text)
    if current_version is None:
        _log(log, f"Не удалось распознать локальную версию {current_text!r}; обновление пропущено.")
        return False

    release = _latest_release(log)
    if not release:
        return False

    tag = str(release.get("tag_name", ""))
    release_version = _version_tuple(tag)
    if release_version is None:
        _log(log, f"Тег релиза {tag!r} не соответствует формату vX.Y.Z; обновление пропущено.")
        return False

    if release_version <= current_version:
        _log(log, f"Установлена актуальная версия {current_text}.")
        state_path.write_text(json.dumps({"last_successful_check": now}, ensure_ascii=False), encoding="utf-8")
        return False

    version_label = ".".join(str(part) for part in release_version)
    zip_name = f"TelegramThemeMaker_v{version_label}_Windows.zip"
    checksum_name = zip_name + ".sha256"
    assets = release.get("assets") or []
    zip_asset = _asset(assets, zip_name)
    checksum_asset = _asset(assets, checksum_name)
    if zip_asset and int(zip_asset.get("size") or 0) > MAX_ARCHIVE_BYTES:
        _log(log, "ZIP релиза превышает допустимый размер; обновление пропущено.")
        return False
    if not zip_asset or not checksum_asset:
        _log(log, f"Релиз {tag} найден, но в нём пока нет ZIP и SHA256-файла. Повторю проверку позже.")
        return False

    temp_dir = Path(tempfile.mkdtemp(prefix="theme-maker-update-"))
    changed: list[Path] = []
    try:
        archive_path = temp_dir / zip_name
        checksum_payload = _request(checksum_asset["browser_download_url"], max_bytes=16 * 1024)
        expected_hash = _checksum_value(checksum_payload)
        archive_payload = _request(zip_asset["browser_download_url"], timeout=60, max_bytes=MAX_ARCHIVE_BYTES)
        actual_hash = hashlib.sha256(archive_payload).hexdigest()
        if actual_hash != expected_hash:
            raise UpdateError("Контрольная сумма ZIP не совпала. Файлы проекта не изменены.")
        archive_path.write_bytes(archive_payload)

        staged_root = _stage_archive(archive_path, temp_dir, version_label)
        backup_root = temp_dir / "backup"
        backup_root.mkdir()
        changed, requirements_changed = _apply_staged_files(root, staged_root, backup_root)
        if requirements_changed:
            try:
                _install_requirements(root, log)
            except Exception:
                # Restore project files if dependency installation failed.
                for target, backup in reversed(changed):
                    try:
                        if backup and backup.exists():
                            os.replace(backup, target)
                        else:
                            target.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise

        state_path.write_text(json.dumps({"last_successful_check": now}, ensure_ascii=False), encoding="utf-8")
        _log(log, f"Обновление установлено: {current_text} → {version_label}.")
        return True
    except Exception as exc:
        _log(log, f"Обновление не установлено; запуск продолжится на текущих файлах: {exc}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
