import asyncio
import io
import os
import tempfile
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


if __name__ == "__main__":
    unittest.main()
