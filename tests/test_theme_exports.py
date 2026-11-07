import asyncio
import io
import os
import tempfile
import time
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image, ImageDraw

# These tests exercise the real project code without reading a developer's .env
# or writing test sessions into the user's data directory.
_TEST_DATA = tempfile.TemporaryDirectory(prefix="theme-maker-tests-")
os.environ["BOT_TOKEN"] = "123456789:TEST_ONLY_NOT_A_REAL_TOKEN"
os.environ["THEME_MAKER_USER_DATA_DIR"] = _TEST_DATA.name

import bot  # noqa: E402


def tearDownModule():
    asyncio.run(bot.dp.storage.close())
    _TEST_DATA.cleanup()


class ThemeExportTests(unittest.TestCase):
    def setUp(self):
        self.theme = bot.DEFAULT_THEME.copy()
        bot.ensure_text_colors(self.theme)

    def test_all_exporters_return_nonempty_bytes(self):
        outputs = {
            "desktop": bot.create_desktop_theme(self.theme, None),
            "desktop_palette": bot.desktop_palette_text(self.theme),
            "android": bot.create_android_theme(self.theme, None),
            "ios": bot.create_ios_theme(self.theme),
            "macos": bot.create_macos_palette(self.theme),
            "telegram_x": bot.create_tgx_theme(self.theme),
        }
        for name, payload in outputs.items():
            with self.subTest(format=name):
                self.assertIsInstance(payload, bytes)
                self.assertGreater(len(payload), 20)

        self.assertIn(b"windowBg:", outputs["desktop_palette"])
        self.assertIn(b"windowBackgroundWhite=", outputs["android"])
        self.assertIn(b"basedOn:", outputs["ios"])
        self.assertIn(b"isDark =", outputs["macos"])
        self.assertIn(b"bubbleIn_background", outputs["telegram_x"])

    def test_wallpaper_is_embedded_only_in_supported_formats(self):
        image_stream = io.BytesIO()
        Image.new("RGB", (8, 8), (25, 80, 140)).save(image_stream, format="JPEG")
        image_path = Path(_TEST_DATA.name) / "wallpaper.jpg"
        image_path.write_bytes(image_stream.getvalue())

        desktop = bot.create_desktop_theme(self.theme, image_path)
        with zipfile.ZipFile(io.BytesIO(desktop)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"colors.tdesktop-theme", "background.jpg"},
            )
            self.assertTrue(archive.read("background.jpg").startswith(b"\xff\xd8"))

        android = bot.create_android_theme(self.theme, image_path)
        self.assertIn(b"WPS\n", android)
        self.assertIn(b"WPE\n", android)

        ios = bot.create_ios_theme(self.theme)
        macos = bot.create_macos_palette(self.theme)
        tgx = bot.create_tgx_theme(self.theme)
        self.assertNotIn(b"WPS\n", ios)
        self.assertNotIn(b"WPS\n", macos)
        self.assertNotIn(b"WPS\n", tgx)

    def test_welcome_cover_prefers_local_override_then_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "assets" / "welcome.png"
            bundled = root / "defaults" / "welcome.png"
            local.parent.mkdir()
            bundled.parent.mkdir()
            local.write_bytes(b"local cover")
            bundled.write_bytes(b"default cover")

            original_local = bot.COVER_PATH
            original_default = bot.DEFAULT_COVER_PATH
            try:
                bot.COVER_PATH = local
                bot.DEFAULT_COVER_PATH = bundled
                self.assertEqual(bot.welcome_cover_path(), local)

                local.unlink()
                self.assertEqual(bot.welcome_cover_path(), bundled)
            finally:
                bot.COVER_PATH = original_local
                bot.DEFAULT_COVER_PATH = original_default

    def test_photo_palette_and_color_parsing(self):
        self.assertEqual(bot.parse_color("#abc"), "#AABBCC")
        self.assertEqual(bot.parse_color("255, 0, 128"), "#FF0080")
        palette = ["#112233", "#445566", "#778899", "#AABBCC"]
        photo_theme = bot.create_photo_theme(palette)
        self.assertEqual(photo_theme["accent"], photo_theme["accent"].upper())
        self.assertIn(photo_theme["accent"], palette)
        self.assertIn(photo_theme["outgoing"], palette)
        self.assertIn(photo_theme["incoming"], palette)

    def test_photo_extraction_handles_valid_png(self):
        stream = io.BytesIO()
        Image.new("RGB", (20, 20), (45, 90, 135)).save(stream, format="PNG")
        palette = bot.extract_palette(stream.getvalue())
        self.assertTrue(palette)
        self.assertTrue(all(bot.parse_color(color) for color in palette))

    def test_photo_palette_uses_legacy_lanczos_mediancut_sampling(self):
        stream = io.BytesIO()
        image = Image.new("RGB", (1000, 500), "#223344")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 249, 499), fill="#CC5577")
        draw.rectangle((250, 0, 499, 499), fill="#55AA77")
        draw.rectangle((500, 0, 749, 499), fill="#DDBB44")
        image.save(stream, format="PNG")

        original_quantize = Image.Image.quantize
        observed = {}

        def inspect_quantize(source, *args, **kwargs):
            observed["size"] = source.size
            observed["method"] = kwargs.get("method")
            observed["colors"] = kwargs.get("colors")
            return original_quantize(source, *args, **kwargs)

        with patch.object(Image.Image, "quantize", new=inspect_quantize):
            palette = bot.extract_palette(stream.getvalue())

        self.assertEqual(observed["size"], (500, 250))
        self.assertEqual(observed["method"], Image.Quantize.MEDIANCUT)
        self.assertEqual(observed["colors"], 8)
        self.assertTrue(palette)


    def test_language_picker_and_english_menus(self):
        picker = bot.language_keyboard()
        self.assertEqual(
            [button.callback_data for button in picker.inline_keyboard[0]],
            ["lang:ru", "lang:en"],
        )

        menu = bot.main_menu("en")
        menu_labels = [button.text for row in menu.inline_keyboard for button in row]
        self.assertIn("🖼 Create from a photo", menu_labels)
        self.assertIn("🌐 Language", menu_labels)

        editor = bot.theme_keyboard("en")
        editor_labels = [button.text for row in editor.inline_keyboard for button in row]
        self.assertIn("Main background", editor_labels)
        self.assertIn("📦 Export theme", editor_labels)

        self.assertEqual(bot.default_theme("en")["name"], "My theme")
        self.assertEqual(bot.default_theme("ru")["name"], "Моя тема")

    def test_photo_progress_text_has_a_real_line_break_in_both_languages(self):
        ru = bot.tr("ru", "photo_progress", percent=45, stage="Подбираю цвета…")
        en = bot.tr("en", "photo_progress", percent=45, stage="Picking colours…")
        self.assertIn("\n", ru)
        self.assertIn("\n", en)
        self.assertIn("45%", ru)
        self.assertIn("45%", en)

    def test_telegram_photo_download_retries_gateway_and_network_timeouts(self):
        class FakeBot:
            def __init__(self):
                self.get_file_timeout = None
                self.download_timeout = None
                self.get_file_calls = 0
                self.download_calls = 0

            async def get_file(self, file_id, request_timeout=None):
                self.get_file_calls += 1
                self.get_file_timeout = request_timeout
                if self.get_file_calls == 1:
                    raise bot.TelegramServerError(
                        method=SimpleNamespace(),
                        message="Gateway Timeout",
                    )
                return SimpleNamespace(file_path="photos/test.jpg", file_size=10)

            async def download_file(self, file_path, destination, timeout=30):
                self.download_calls += 1
                self.download_timeout = timeout
                if self.download_calls == 1:
                    raise bot.TelegramNetworkError(
                        method=SimpleNamespace(),
                        message="Request timeout error",
                    )
                destination.write(b"0123456789")

        async def exercise():
            fake_bot = FakeBot()
            fake_message = SimpleNamespace(
                photo=[SimpleNamespace(file_id="photo-id", file_size=10)],
                document=None,
            )
            with patch("bot.asyncio.sleep", new=AsyncMock()):
                payload = await bot.download_telegram_image(fake_message, fake_bot)
            return fake_bot, payload

        fake_bot, payload = asyncio.run(exercise())
        self.assertEqual(payload, b"0123456789")
        self.assertEqual(fake_bot.get_file_timeout, 120)
        self.assertEqual(fake_bot.download_timeout, 180)
        self.assertEqual(fake_bot.get_file_calls, 2)
        self.assertEqual(fake_bot.download_calls, 2)

    def test_photo_download_progress_buffer_reports_real_percentages(self):
        updates = []
        buffer = bot.ProgressBytesIO(100, updates.append)
        for _ in range(10):
            buffer.write(b"x" * 10)

        self.assertEqual(updates, [20, 40, 60, 80, 100])
        self.assertEqual(len(buffer.getvalue()), 100)

    def test_photo_preparation_restores_legacy_palette_and_wallpaper_pipeline(self):
        stream = io.BytesIO()
        image = Image.new("RGB", (900, 600), "#223344")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 299, 599), fill="#CC5577")
        draw.rectangle((300, 0, 599, 599), fill="#55AA77")
        draw.rectangle((600, 0, 899, 599), fill="#DDBB44")
        image.save(stream, format="PNG")

        with tempfile.TemporaryDirectory() as directory:
            original_user_data = bot.USER_DATA
            bot.USER_DATA = Path(directory)
            updates = []
            try:
                palette, wallpaper = bot.prepare_photo_assets(
                    404,
                    stream.getvalue(),
                    progress_callback=lambda percent, stage: updates.append((percent, stage)),
                )
                self.assertTrue(palette)
                self.assertLessEqual(len(palette), 8)
                self.assertTrue(wallpaper.is_file())
                with Image.open(wallpaper) as saved:
                    self.assertLessEqual(max(saved.size), bot.MAX_IMAGE_SIDE)
                self.assertEqual(
                    [percent for percent, _ in updates],
                    [42, 64, 76],
                )
            finally:
                bot.USER_DATA = original_user_data

    def test_download_progress_updates_during_transfer(self):
        class FakeMessage:
            def __init__(self):
                self.edits = []

            async def edit_text(self, text, **kwargs):
                self.edits.append(text)

        async def exercise():
            progress_message = FakeMessage()

            async def fake_download(report):
                for percent in (20, 40, 60, 80, 100):
                    report(percent)
                    await asyncio.sleep(0)
                return b"photo-bytes"

            result = await bot.download_with_progress(progress_message, "en", fake_download)
            return result, progress_message.edits

        result, edits = asyncio.run(exercise())
        self.assertEqual(result, b"photo-bytes")
        self.assertTrue(any("Loading: 9%" in item for item in edits))
        self.assertTrue(any("Loading: 27%" in item for item in edits))
        self.assertTrue(any("Loading: 30%" in item for item in edits))


    def test_photo_preparation_progress_is_relayed_from_worker(self):
        stream = io.BytesIO()
        Image.new("RGB", (640, 480), "#456789").save(stream, format="PNG")

        class FakeMessage:
            def __init__(self):
                self.edits = []

            async def edit_text(self, text, **kwargs):
                self.edits.append(text)

        async def exercise(directory):
            original_user_data = bot.USER_DATA
            bot.USER_DATA = Path(directory)
            progress_message = FakeMessage()
            try:
                palette, wallpaper = await bot.prepare_photo_assets_with_progress(
                    505,
                    stream.getvalue(),
                    progress_message,
                    "en",
                )
                return palette, wallpaper, progress_message.edits
            finally:
                bot.USER_DATA = original_user_data

        with tempfile.TemporaryDirectory() as directory:
            palette, wallpaper, edits = asyncio.run(exercise(directory))
            self.assertTrue(palette)
            self.assertTrue(wallpaper.is_file())
            self.assertTrue(any("42%" in item for item in edits))
            self.assertTrue(any("64%" in item for item in edits))
            self.assertTrue(any("76%" in item for item in edits))


    def test_android_contact_text_and_shadow_roles_are_mapped_correctly(self):
        theme = self.theme.copy()
        theme["text"] = "#112233"
        theme["message_text"] = "#AABBCC"

        for key in (
            "chat_inContactNameText",
            "chat_outContactNameText",
            "chat_inContactPhoneText",
            "chat_outContactPhoneText",
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    bot.android_color_for_key(key, theme),
                    bot.signed_argb(theme["message_text"]),
                )

        expected_shadow = bot.signed_argb("#000000", 20)
        for key in (
            "chat_messagePanelShadow",
            "chat_inBubbleShadow",
            "chat_outBubbleShadow",
        ):
            with self.subTest(key=key):
                self.assertEqual(bot.android_color_for_key(key, theme), expected_shadow)

    def test_telegram_x_export_does_not_emit_invalid_hard_coded_author(self):
        exported = bot.create_tgx_theme(self.theme).decode("utf-8")
        self.assertNotIn("author:", exported)
        self.assertIn("bubbleIn_background", exported)

    def test_telegram_photo_download_buffer_enforces_limit_without_file_size(self):
        buffer = bot.ProgressBytesIO(None, max_bytes=5)
        self.assertEqual(buffer.write(b"12345"), 5)
        with self.assertRaisesRegex(ValueError, "12 МБ"):
            buffer.write(b"6")
        self.assertEqual(buffer.getvalue(), b"12345")

    def test_macos_palette_encodes_alpha_as_fractional_opacity(self):
        theme = self.theme.copy()
        theme["text"] = "#123456"
        theme["text_auto"] = False
        theme["accent"] = "#ABCDEF"
        exported = bot.create_macos_palette(theme).decode("utf-8")
        values = dict(
            line.split(" = ", 1)
            for line in exported.splitlines()
            if " = " in line
        )

        self.assertEqual(values["blackTransparent"], "#000000: 0.42")
        self.assertEqual(values["grayTransparent"], "#123456: 0.18")
        self.assertEqual(values["waveformBackground"], "#ABCDEF: 0.35")
        self.assertEqual(values["waveformBackgroundBubble_incoming"], "#ABCDEF: 0.35")
        self.assertEqual(values["waveformBackgroundBubble_outgoing"], "#ABCDEF: 0.35")

    def test_desktop_export_uses_the_muted_text_color(self):
        theme = self.theme.copy()
        theme["text"] = "#112233"
        theme["muted"] = "#778899"
        theme["muted_auto"] = False

        colors = bot.create_desktop_colors(theme)
        self.assertEqual(colors["windowSubTextFg"], "#778899")
        self.assertEqual(colors["dialogsDateFg"], "#778899")

        palette = bot.desktop_palette_text(theme).decode("utf-8")
        self.assertIn("windowSubTextFg: #778899;", palette)
        self.assertIn("dialogsDateFg: #778899;", palette)

    def test_macos_incoming_and_outgoing_bubble_opacity_is_exported(self):
        theme = self.theme.copy()
        theme["incoming"] = "#112233"
        theme["incoming_opacity"] = 40
        theme["outgoing"] = "#445566"
        theme["outgoing_opacity"] = 60

        exported = bot.create_macos_palette(theme).decode("utf-8")
        values = dict(
            line.split(" = ", 1)
            for line in exported.splitlines()
            if " = " in line
        )

        # The native macOS importer uses different alpha syntax for the two fields.
        self.assertEqual(values["bubbleBackground_incoming"], "#112233: 0.40")
        self.assertEqual(
            values["bubbleBackground_outgoing"],
            bot.alpha_hex("#445566", 60),
        )

    def test_start_uses_saved_language_after_first_selection(self):
        async def exercise(has_saved_language):
            state = AsyncMock()
            message = SimpleNamespace(from_user=SimpleNamespace(id=8080))
            with (
                patch.object(
                    bot.LANGUAGE_PREFERENCES,
                    "has_language",
                    return_value=has_saved_language,
                ),
                patch.object(bot, "user_language", return_value="en"),
                patch.object(bot, "send_welcome", new_callable=AsyncMock) as welcome,
                patch.object(bot, "send_language_prompt", new_callable=AsyncMock) as prompt,
            ):
                await bot.start(message, state)
                state.clear.assert_awaited_once()
                state.update_data.assert_awaited_once()
                if has_saved_language:
                    welcome.assert_awaited_once_with(message, "en")
                    prompt.assert_not_awaited()
                else:
                    prompt.assert_awaited_once_with(message)
                    welcome.assert_not_awaited()

        asyncio.run(exercise(False))
        asyncio.run(exercise(True))

    def test_photo_upload_errors_are_localized_and_keep_size_detail(self):
        too_large = bot.ImageTooLargeError("Изображение больше 12 МБ.")
        self.assertEqual(
            bot.photo_error_text("en", too_large, "upload"),
            bot.tr("en", "image_too_large"),
        )
        self.assertEqual(
            bot.photo_error_text("en", too_large, "url"),
            bot.tr("en", "image_too_large"),
        )
        self.assertEqual(
            bot.photo_error_text("en", ValueError("Нужна публичная ссылка"), "upload"),
            bot.tr("en", "image_error"),
        )
        self.assertEqual(
            bot.photo_error_text("en", ValueError("HTTP 403"), "url"),
            bot.tr("en", "image_url_error"),
        )

        russian_error = bot.photo_error_text("ru", ValueError("Ошибка: <bad>"), "url")
        self.assertIn("Ошибка:", russian_error)
        self.assertIn("&lt;bad&gt;", russian_error)

    def test_macos_palette_name_is_not_wrapped_in_json_quotes(self):
        theme = self.theme.copy()
        theme["name"] = "Sakura Evening"
        exported = bot.create_macos_palette(theme).decode("utf-8")

        self.assertIn("name = Sakura Evening", exported.splitlines())
        self.assertNotIn('name = "Sakura Evening"', exported.splitlines())

    def test_image_pixel_limit_is_enforced_before_processing(self):
        class FakeImage:
            def __init__(self, size):
                self.size = size

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback_value):
                return False

        with patch.object(bot, "MAX_IMAGE_PIXELS", 10):
            bot.validate_image_dimensions(FakeImage((5, 2)))
            with self.assertRaisesRegex(ValueError, "25 мегапикселей"):
                bot.validate_image_dimensions(FakeImage((11, 1)))

        with tempfile.TemporaryDirectory() as directory:
            oversized_image = FakeImage((11, 1))
            with (
                patch.object(bot, "MAX_IMAGE_PIXELS", 10),
                patch.object(bot.Image, "open", return_value=oversized_image),
                patch.object(bot, "USER_DATA", Path(directory)),
            ):
                with self.assertRaisesRegex(ValueError, "25 мегапикселей"):
                    bot.extract_palette(b"fake-image-data")
                with self.assertRaisesRegex(ValueError, "25 мегапикселей"):
                    bot.save_user_wallpaper(606, b"fake-image-data")



    def test_wallpaper_cleanup_keeps_all_session_references_and_recent_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_dir = root / "606"
            user_dir.mkdir()
            active = user_dir / "wallpaper_aaaaaaaaaaaa.jpg"
            stale = user_dir / "wallpaper_bbbbbbbbbbbb.jpg"
            recent = user_dir / "wallpaper_cccccccccccc.jpg"
            invalid_name = user_dir / "wallpaper-not-generated.jpg"
            for path in (active, stale, recent, invalid_name):
                path.write_bytes(b"image")

            now = 2_000_000_000.0
            old_time = now - 7200
            recent_time = now - 120
            os.utime(active, (old_time, old_time))
            os.utime(stale, (old_time, old_time))
            os.utime(recent, (recent_time, recent_time))
            os.utime(invalid_name, (old_time, old_time))

            removed = bot.cleanup_orphaned_wallpapers(
                root,
                [str(active)],
                grace_seconds=3600,
                now=now,
            )

            self.assertEqual(removed, 1)
            self.assertTrue(active.exists(), "a wallpaper referenced by a saved session must survive")
            self.assertFalse(stale.exists(), "an old unreferenced generated wallpaper should be removed")
            self.assertTrue(recent.exists(), "recent files need a grace period for in-flight uploads")
            self.assertTrue(invalid_name.exists(), "unrelated user files must never be removed")

    def test_wallpaper_cleanup_does_not_touch_outside_paths_or_non_user_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "user_data"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            outside_file = outside / "wallpaper_dddddddddddd.jpg"
            outside_file.write_bytes(b"keep")
            non_user_dir = root / "temporary"
            non_user_dir.mkdir()
            unrelated = non_user_dir / "wallpaper_eeeeeeeeeeee.jpg"
            unrelated.write_bytes(b"keep")
            now = 2_000_000_000.0
            os.utime(outside_file, (now - 7200, now - 7200))
            os.utime(unrelated, (now - 7200, now - 7200))

            removed = bot.cleanup_orphaned_wallpapers(
                root,
                [str(outside_file)],
                grace_seconds=3600,
                now=now,
            )

            self.assertEqual(removed, 0)
            self.assertTrue(outside_file.exists())
            self.assertTrue(unrelated.exists())

    def test_async_cleanup_reads_wallpapers_from_all_saved_sessions(self):
        async def exercise(user_data):
            user_one = user_data / "606"
            user_two = user_data / "707"
            user_one.mkdir(parents=True)
            user_two.mkdir(parents=True)
            active_one = user_one / "wallpaper_aaaaaaaaaaaa.jpg"
            active_two = user_two / "wallpaper_bbbbbbbbbbbb.jpg"
            orphan = user_one / "wallpaper_cccccccccccc.jpg"
            for path in (active_one, active_two, orphan):
                path.write_bytes(b"image")
                os.utime(path, (time.time() - 7200, time.time() - 7200))

            sessions = [
                {"wallpaper_path": str(active_one)},
                {"wallpaper_path": str(active_two)},
                {"theme": {"name": "no wallpaper"}},
            ]
            with (
                patch.object(bot, "USER_DATA", user_data),
                patch.object(bot.dp.storage, "get_all_data", new=AsyncMock(return_value=sessions)),
            ):
                removed = await bot.cleanup_unused_wallpapers()

            self.assertEqual(removed, 1)
            self.assertTrue(active_one.exists())
            self.assertTrue(active_two.exists())
            self.assertFalse(orphan.exists())

        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(exercise(Path(directory)))

    def test_save_wallpaper_removes_partial_file_when_image_save_fails(self):
        image_stream = io.BytesIO()
        Image.new("RGB", (8, 8), (25, 80, 140)).save(image_stream, format="JPEG")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_data = bot.USER_DATA

            def write_partial_then_fail(image, path, *args, **kwargs):
                Path(path).write_bytes(b"partial")
                raise OSError("simulated disk write failure")

            try:
                bot.USER_DATA = root
                with patch.object(Image.Image, "save", new=write_partial_then_fail):
                    with self.assertRaisesRegex(OSError, "simulated disk write failure"):
                        bot.save_user_wallpaper(606, image_stream.getvalue())
            finally:
                bot.USER_DATA = original_data

            self.assertEqual(list((root / "606").glob("wallpaper_*.jpg")), [])

    def test_android_message_timestamps_are_exported_as_muted_text(self):
        theme = self.theme.copy()
        theme["muted"] = "#778899"
        theme["text"] = "#112233"
        theme["message_text"] = "#AABBCC"

        keys = bot.load_android_theme_keys()
        for key in ("chat_inTimeText", "chat_outTimeText"):
            with self.subTest(key=key):
                self.assertIn(key, keys)
                self.assertEqual(
                    bot.android_color_for_key(key, theme),
                    bot.signed_argb(theme["muted"]),
                )


    def test_background_photo_task_releases_fsm_lock_for_cancel(self):
        async def exercise():
            key = object()
            state = SimpleNamespace(
                key=key,
                set_state=AsyncMock(),
                get_state=AsyncMock(return_value=bot.ThemeStates.processing_image.state),
            )
            message = SimpleNamespace(from_user=SimpleNamespace(id=8080))
            progress = SimpleNamespace(edit_text=AsyncMock())
            download_started = asyncio.Event()
            download_cancelled = asyncio.Event()

            async def blocked_downloader(report):
                download_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    download_cancelled.set()
                    raise

            isolation = bot.SimpleEventIsolation()
            async with isolation.lock(key):
                started = await bot.start_photo_processing(
                    message,
                    state,
                    progress,
                    "en",
                    blocked_downloader,
                    "upload",
                )
            self.assertTrue(started)
            await asyncio.wait_for(download_started.wait(), timeout=1)
            self.assertIn(key, bot.PHOTO_PROCESSING_TASKS)

            async def cancel_under_same_fsm_lock():
                async with isolation.lock(key):
                    await bot.cancel_photo_processing(state)

            await asyncio.wait_for(cancel_under_same_fsm_lock(), timeout=1)
            self.assertTrue(download_cancelled.is_set())
            self.assertNotIn(key, bot.PHOTO_PROCESSING_TASKS)

        asyncio.run(exercise())

    def test_cancel_command_stops_the_active_photo_task_and_clears_state(self):
        async def exercise():
            key = object()
            started = asyncio.Event()
            cancelled = asyncio.Event()

            async def worker():
                started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

            task = asyncio.create_task(worker())
            await started.wait()
            previous = bot.PHOTO_PROCESSING_TASKS.copy()
            bot.PHOTO_PROCESSING_TASKS.clear()
            bot.PHOTO_PROCESSING_TASKS[key] = task
            state = SimpleNamespace(key=key, clear=AsyncMock())
            message = SimpleNamespace(
                from_user=SimpleNamespace(id=8181),
                answer=AsyncMock(),
            )
            try:
                with patch.object(bot, "cleanup_unused_wallpapers", new=AsyncMock()):
                    await bot.cancel_command(message, state)
                self.assertTrue(cancelled.is_set())
                self.assertTrue(task.done())
                state.clear.assert_awaited_once()
                message.answer.assert_awaited_once()
                self.assertNotIn(key, bot.PHOTO_PROCESSING_TASKS)
            finally:
                bot.PHOTO_PROCESSING_TASKS.clear()
                bot.PHOTO_PROCESSING_TASKS.update(previous)

        asyncio.run(exercise())

    def test_download_progress_cancels_its_nested_downloader(self):
        async def exercise():
            started = asyncio.Event()
            cancelled = asyncio.Event()
            progress = SimpleNamespace(edit_text=AsyncMock())

            async def downloader(report):
                started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

            task = asyncio.create_task(
                bot.download_with_progress(progress, "en", downloader)
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cancelled.is_set())

        asyncio.run(exercise())

    def test_cancelled_photo_worker_removes_wallpaper_after_thread_finishes(self):
        async def exercise(directory):
            root = Path(directory)
            started = threading.Event()
            release = threading.Event()
            wallpaper = root / "606" / "wallpaper_aaaaaaaaaaaa.jpg"
            progress = SimpleNamespace(edit_text=AsyncMock())

            def slow_prepare(user_id, raw, progress_callback=None):
                started.set()
                release.wait(timeout=5)
                wallpaper.parent.mkdir(parents=True, exist_ok=True)
                wallpaper.write_bytes(b"temporary wallpaper")
                return ["#112233"], wallpaper

            with patch.object(bot, "prepare_photo_assets", new=slow_prepare):
                task = asyncio.create_task(
                    bot.prepare_photo_assets_with_progress(
                        606, b"image", progress, "en"
                    )
                )
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

                workers = list(bot.PHOTO_PREPARATION_WORKERS)
                self.assertTrue(workers, "the worker thread must remain tracked after cancellation")
                release.set()
                await asyncio.gather(*workers, return_exceptions=True)
                await asyncio.sleep(0)
                self.assertFalse(wallpaper.exists())

        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(exercise(directory))


if __name__ == "__main__":
    unittest.main()
