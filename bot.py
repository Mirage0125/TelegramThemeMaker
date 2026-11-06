import asyncio
import html
import io
import ipaddress
import json
import os
import re
import random
import socket
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    BufferedInputFile,
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from dotenv import load_dotenv

from SQLiteStorage import SQLiteStorage
from Localization import LanguagePreferences, text as tr

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
TOKEN = os.getenv("BOT_TOKEN", "").strip()
CATALOG_PATH = ROOT / "themes" / "catalog.json"
USER_DATA = Path(os.getenv("THEME_MAKER_USER_DATA_DIR", str(ROOT / "user_data"))).expanduser()
COVER_PATH = ROOT / "assets" / "welcome.png"  # User-owned override; never replaced by releases.
DEFAULT_COVER_PATH = ROOT / "defaults" / "welcome.png"
VERSION_PATH = ROOT / "VERSION.txt"
try:
    APP_VERSION = VERSION_PATH.read_text(encoding="utf-8-sig").strip()
except OSError:
    APP_VERSION = "unknown"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_SIDE = 1920
PALETTE_IMAGE_SIDE = 320
Image.MAX_IMAGE_PIXELS = 25_000_000


class ProgressBytesIO(io.BytesIO):
    """A BytesIO download target that reports real byte-based progress."""

    def __init__(self, total_size: int | None, progress_callback=None):
        super().__init__()
        self.total_size = max(0, int(total_size or 0))
        self.progress_callback = progress_callback
        self.last_reported_step = 0

    def write(self, data: bytes) -> int:
        written = super().write(data)
        if self.total_size and self.progress_callback:
            percent = min(100, int(self.tell() * 100 / self.total_size))
            step = percent // 20
            if step > self.last_reported_step or percent == 100:
                self.last_reported_step = step
                self.progress_callback(percent)
        return written

if not TOKEN or TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    raise SystemExit("Не найден токен. Открой .env, вставь токен от @BotFather и перезапусти Start.bat.")

LANGUAGE_PREFERENCES = LanguagePreferences(USER_DATA / "languages.sqlite3")

def user_language(user_id: int) -> str:
    return LANGUAGE_PREFERENCES.get_language(user_id)

def default_theme(language: str = "ru") -> dict:
    theme = DEFAULT_THEME.copy()
    theme["name"] = tr(language, "default_theme_name")
    return theme

dp = Dispatcher(
    storage=SQLiteStorage(USER_DATA / "fsm.sqlite3"),
    events_isolation=SimpleEventIsolation(),
)

DEFAULT_THEME = {
    "name": "Моя тема",
    "background": "#222B36",
    "accent": "#55A9E8",
    "outgoing": "#315F88",
    "incoming": "#35404D",
    "text": "#FFFFFF",
    "message_text": "#FFFFFF",
    "muted": "#FFFFFF",
    "text_auto": True,
    "message_text_auto": True,
    "muted_auto": True,
    "outgoing_opacity": 100,
    "incoming_opacity": 100,
}

FIELD_LABELS = {
    "background": "Основной цвет интерфейса",
    "accent": "Акцентный цвет",
    "outgoing": "Мои сообщения",
    "incoming": "Входящие сообщения",
    "text": "Основной текст интерфейса",
    "message_text": "Текст сообщений",
}

FIELD_HELP = {
    "background": "Фон окон, списка чатов, вкладок и панелей. Это не фотография-обои.",
    "accent": "Кнопки, ссылки, команды, галочки, иконки файлов, голосовые индикаторы, выделение и активные элементы.",
    "outgoing": "Заливка пузырей сообщений, которые отправляешь ты.",
    "incoming": "Заливка пузырей сообщений собеседников.",
    "text": "Обычный текст интерфейса: заголовки, названия чатов, папок и разделов. По умолчанию автоматически выбирается чёрный или белый.",
    "message_text": "Текст внутри сообщений. По умолчанию автоматически выбирается чёрный или белый; при желании можно задать свой цвет.",
}

NAMED_COLORS = {
    "black": "#000000", "черный": "#000000", "чёрный": "#000000",
    "white": "#FFFFFF", "белый": "#FFFFFF",
    "gray": "#808080", "grey": "#808080", "серый": "#808080",
    "darkgray": "#404040", "darkgrey": "#404040", "темно-серый": "#404040", "тёмно-серый": "#404040",
    "lightgray": "#D3D3D3", "lightgrey": "#D3D3D3", "светло-серый": "#D3D3D3",
    "red": "#FF0000", "красный": "#FF0000",
    "orange": "#FFA500", "оранжевый": "#FFA500",
    "yellow": "#FFFF00", "желтый": "#FFFF00", "жёлтый": "#FFFF00",
    "green": "#008000", "зеленый": "#008000", "зелёный": "#008000",
    "lime": "#00FF00", "лаймовый": "#00FF00",
    "blue": "#0000FF", "синий": "#0000FF",
    "navy": "#000080", "темно-синий": "#000080", "тёмно-синий": "#000080",
    "lightblue": "#ADD8E6", "голубой": "#87CEEB", "светло-синий": "#ADD8E6",
    "cyan": "#00FFFF", "бирюзовый": "#00CED1", "циан": "#00FFFF",
    "teal": "#008080", "морской": "#008080",
    "purple": "#800080", "фиолетовый": "#800080",
    "violet": "#8A2BE2", "сиреневый": "#C8A2C8",
    "pink": "#FFC0CB", "розовый": "#FFC0CB",
    "magenta": "#FF00FF", "маджента": "#FF00FF",
    "brown": "#8B4513", "коричневый": "#8B4513",
    "beige": "#F5F5DC", "бежевый": "#F5F5DC",
    "coral": "#FF7F50", "коралловый": "#FF7F50",
    "gold": "#FFD700", "золотой": "#FFD700",
}

COLOR_BUTTONS = [
    ("⚫ Чёрный", "black"), ("⚪ Белый", "white"), ("🩶 Серый", "gray"),
    ("🔴 Красный", "red"), ("🟠 Оранжевый", "orange"), ("🟡 Жёлтый", "yellow"),
    ("🟢 Зелёный", "green"), ("🔵 Синий", "blue"), ("🩵 Голубой", "lightblue"),
    ("🩵 Бирюзовый", "cyan"), ("🟣 Фиолетовый", "purple"), ("🩷 Розовый", "pink"),
]

class ThemeStates(StatesGroup):
    waiting_color = State()
    waiting_image = State()
    waiting_name = State()


def load_catalog():
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
    ]])


def main_menu(language: str = "ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(language, "menu_photo"), callback_data="image")],
        [InlineKeyboardButton(text=tr(language, "menu_manual"), callback_data="create")],
        [InlineKeyboardButton(text=tr(language, "menu_catalog"), callback_data="catalog")],
        [InlineKeyboardButton(text=tr(language, "menu_help"), callback_data="help")],
        [InlineKeyboardButton(text=tr(language, "language_button"), callback_data="language")],
    ])


def field_label(language: str, field: str) -> str:
    return tr(language, f"field_{field}")


def field_help(language: str, field: str) -> str:
    return tr(language, f"field_{field}_help")


def color_button_labels(language: str):
    if language == "en":
        keys = [
            ("color_black", "black"), ("color_white", "white"), ("color_gray", "gray"),
            ("color_red", "red"), ("color_orange", "orange"), ("color_yellow", "yellow"),
            ("color_green", "green"), ("color_blue", "blue"), ("color_lightblue", "lightblue"),
            ("color_cyan", "cyan"), ("color_purple", "purple"), ("color_pink", "pink"),
        ]
        return [(tr(language, key), value) for key, value in keys]
    return COLOR_BUTTONS


def theme_keyboard(language: str = "ru", has_image_palette: bool = False):
    rows = [
        [InlineKeyboardButton(text=field_label(language, "background"), callback_data="field:background"),
         InlineKeyboardButton(text=field_label(language, "accent"), callback_data="field:accent")],
        [InlineKeyboardButton(text=field_label(language, "outgoing"), callback_data="field:outgoing"),
         InlineKeyboardButton(text=field_label(language, "incoming"), callback_data="field:incoming")],
        [InlineKeyboardButton(text=field_label(language, "text"), callback_data="field:text"),
         InlineKeyboardButton(text=field_label(language, "message_text"), callback_data="field:message_text")],
        [InlineKeyboardButton(text=tr(language, "opacity_outgoing"), callback_data="opacity:outgoing"),
         InlineKeyboardButton(text=tr(language, "opacity_incoming"), callback_data="opacity:incoming")],
        [InlineKeyboardButton(text=tr(language, "rename"), callback_data="rename"),
         InlineKeyboardButton(text=tr(language, "reset"), callback_data="reset")],
    ]
    if has_image_palette:
        rows.append([InlineKeyboardButton(text=tr(language, "shuffle"), callback_data="shuffle_palette")])
    rows.extend([
        [InlineKeyboardButton(text=tr(language, "export"), callback_data="export_menu")],
        [InlineKeyboardButton(text=tr(language, "home"), callback_data="home")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def color_choice_keyboard(language: str, field: str, image_palette: list[str] | None = None):
    rows = []
    if image_palette:
        palette = list(dict.fromkeys(color for color in image_palette if parse_color(color)))[:8]
        for i in range(0, len(palette), 2):
            rows.append([
                InlineKeyboardButton(text=color, callback_data=f"csethex:{field}:{color.lstrip('#')}")
                for color in palette[i:i + 2]
            ])
        rows.append([InlineKeyboardButton(text=tr(language, "shuffle"), callback_data="shuffle_palette")])
        rows.append([InlineKeyboardButton(text=tr(language, "custom_hex"), callback_data=f"custom:{field}")])
    else:
        buttons = color_button_labels(language)
        for i in range(0, len(buttons), 3):
            rows.append([
                InlineKeyboardButton(text=label, callback_data=f"cset:{field}:{key}")
                for label, key in buttons[i:i + 3]
            ])
        rows.append([InlineKeyboardButton(text=tr(language, "custom_color"), callback_data=f"custom:{field}")])
    rows.append([InlineKeyboardButton(text=tr(language, "back"), callback_data="back_theme")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def opacity_keyboard(language: str, field: str):
    rows = []
    for pair in ((100, 90, 80), (70, 60, 50), (40, 30, 20)):
        rows.append([InlineKeyboardButton(text=f"{value}%", callback_data=f"opset:{field}:{value}") for value in pair])
    rows.append([InlineKeyboardButton(text=tr(language, "back"), callback_data="back_theme")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def export_keyboard(language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖥 Windows — .tdesktop-theme", callback_data="export:windows")],
        [InlineKeyboardButton(text="🤖 Android — .attheme", callback_data="export:android")],
        [InlineKeyboardButton(text="📱 iPhone — .tgios-theme", callback_data="export:ios")],
        [InlineKeyboardButton(text="🍎 macOS — .palette", callback_data="export:macos")],
        [InlineKeyboardButton(text=tr(language, "export_other"), callback_data="export:other")],
        [InlineKeyboardButton(text=tr(language, "back_export"), callback_data="back_theme")],
    ])


def other_export_keyboard(language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram X — .tgx-theme", callback_data="export:tgx")],
        [InlineKeyboardButton(text="Desktop Editor — .tdesktop-palette", callback_data="export:desktop_palette")],
        [InlineKeyboardButton(text=tr(language, "back"), callback_data="export_menu")],
    ])


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return (cleaned or "TelegramTheme")[:48]


def parse_color(value: str) -> str | None:
    raw = (value or "").strip().lower().replace("ё", "е")
    if raw in NAMED_COLORS:
        return NAMED_COLORS[raw]
    raw = raw.replace(" ", "")
    if raw.startswith("#"):
        raw = raw[1:]
    if re.fullmatch(r"[0-9a-f]{6}", raw):
        return "#" + raw.upper()
    if re.fullmatch(r"[0-9a-f]{3}", raw):
        return "#" + "".join(ch * 2 for ch in raw).upper()
    rgb_match = re.fullmatch(r"(\d{1,3})[,; ]+(\d{1,3})[,; ]+(\d{1,3})", (value or "").strip())
    if rgb_match:
        channels = [int(part) for part in rgb_match.groups()]
        if all(0 <= channel <= 255 for channel in channels):
            return "#{:02X}{:02X}{:02X}".format(*channels)
    return None


def hex_rgb(value: str):
    value = value.lstrip("#")[:6]
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def alpha_hex(color: str, opacity: int = 100) -> str:
    alpha = max(0, min(100, int(opacity))) * 255 // 100
    return color.upper() + f"{alpha:02X}"


def signed_argb(hex_color: str, opacity: int = 100) -> int:
    r, g, b = hex_rgb(hex_color)
    a = max(0, min(100, int(opacity))) * 255 // 100
    value = (a << 24) | (r << 16) | (g << 8) | b
    return value if value < 2**31 else value - 2**32


def mix(c1: str, c2: str, amount: float) -> str:
    a, b = hex_rgb(c1), hex_rgb(c2)
    return rgb_hex(tuple(round(a[i] * (1 - amount) + b[i] * amount) for i in range(3)))


def luminance(hex_color: str) -> float:
    """Return WCAG relative luminance for an sRGB hex color."""
    channels = []
    for value in hex_rgb(hex_color):
        component = value / 255.0
        channels.append(component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def auto_text_color(background: str) -> str:
    """Choose whichever of black/white gives the stronger WCAG contrast."""
    light = luminance(background)
    contrast_white = 1.05 / (light + 0.05)
    contrast_black = (light + 0.05) / 0.05
    return "#FFFFFF" if contrast_white >= contrast_black else "#000000"


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def best_message_text_color(theme: dict) -> str:
    """Choose black or white to maximize the worst contrast across both bubbles."""
    background = theme["background"]
    incoming = mix(background, theme.get("incoming", background), theme.get("incoming_opacity", 100) / 100)
    outgoing = mix(background, theme.get("outgoing", background), theme.get("outgoing_opacity", 100) / 100)
    candidates = ("#FFFFFF", "#000000")
    return max(
        candidates,
        key=lambda candidate: min(
            contrast_ratio(candidate, incoming),
            contrast_ratio(candidate, outgoing),
        ),
    )


def ensure_text_colors(theme: dict):
    # Keep auto-selected colors synchronized with every surface that affects them.
    if theme.get("text_auto", True) or not theme.get("text"):
        theme["text"] = auto_text_color(theme["background"])
        theme["text_auto"] = True
    if theme.get("message_text_auto", True) or not theme.get("message_text"):
        theme["message_text"] = best_message_text_color(theme)
        theme["message_text_auto"] = True
    if theme.get("muted_auto", True) or not theme.get("muted"):
        # Keep secondary text quieter while retaining at least 4.5:1 contrast where possible.
        base = theme["text"]
        background = theme["background"]
        if contrast_ratio(base, background) >= 4.5:
            low, high = 0.0, 1.0
            for _ in range(18):
                middle = (low + high) / 2
                candidate = mix(base, background, middle)
                if contrast_ratio(candidate, background) >= 4.5:
                    low = middle
                else:
                    high = middle
            theme["muted"] = mix(base, background, low)
        else:
            theme["muted"] = base
        theme["muted_auto"] = True
    return theme


def contrast_color(background: str) -> str:
    return auto_text_color(background)


def _save_user_wallpaper_image(user_id: int, image: Image.Image) -> Path:
    user_dir = USER_DATA / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    # Each theme gets its own file: a later upload must not mutate an older active theme.
    dest = user_dir / f"wallpaper_{uuid.uuid4().hex[:12]}.jpg"
    image.save(dest, "JPEG", quality=87, progressive=True)
    return dest


def save_user_wallpaper(user_id: int, raw: bytes) -> Path:
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.BICUBIC)
        return _save_user_wallpaper_image(user_id, image)


def _extract_palette_from_image(image: Image.Image) -> list[str]:
    # A 320 px sample is enough for a small theme palette and is much cheaper to quantize.
    sample = image.copy()
    sample.thumbnail((PALETTE_IMAGE_SIDE, PALETTE_IMAGE_SIDE), Image.Resampling.BILINEAR)
    quantized = sample.quantize(
        colors=8,
        method=Image.Quantize.FASTOCTREE,
    ).convert("RGB")
    colors = sorted(
        quantized.getcolors(PALETTE_IMAGE_SIDE * PALETTE_IMAGE_SIDE) or [],
        reverse=True,
    )
    result = []
    for _, rgb in colors:
        value = rgb_hex(rgb)
        if value not in result:
            result.append(value)
        if len(result) == 8:
            break
    return result


def extract_palette(raw: bytes):
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        return _extract_palette_from_image(image)


def prepare_photo_assets(user_id: int, raw: bytes, progress_callback=None) -> tuple[list[str], Path]:
    """Decode an uploaded image once, then make both the palette and wallpaper from it."""
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.BICUBIC)
        if progress_callback:
            progress_callback(42, "photo_stage_analyzing")

        palette = _extract_palette_from_image(image)
        if progress_callback:
            progress_callback(64, "photo_stage_palette")

        wallpaper = _save_user_wallpaper_image(user_id, image)
        if progress_callback:
            progress_callback(76, "photo_stage_saving")

    return palette, wallpaper


def create_photo_theme(image_palette: list[str], previous_theme: dict | None = None) -> dict:
    """Build a new theme variant using colors extracted from the uploaded image."""
    palette = list(dict.fromkeys(color for color in (parse_color(c) for c in image_palette) if color))
    if not palette:
        raise ValueError("В палитре фотографии нет подходящих цветов.")

    # Prefer only exact colors extracted from the image. If the photo is
    # monochrome and yields fewer than four distinct colors, add a few
    # restrained tints only to fill the missing semantic roles.
    candidates = list(palette)
    if len(candidates) < 4:
        for color in palette:
            for tint in (mix(color, "#FFFFFF", 0.16), mix(color, "#101820", 0.16), mix(color, "#7B8794", 0.12)):
                if tint not in candidates:
                    candidates.append(tint)
                if len(candidates) >= 4:
                    break
            if len(candidates) >= 4:
                break
    while len(candidates) < 4:
        base = candidates[0]
        tint = mix(base, "#FFFFFF" if len(candidates) % 2 else "#101820", 0.24)
        if tint not in candidates:
            candidates.append(tint)
        else:
            candidates.append(mix(base, "#B7C4D0", 0.32))

    rng = random.SystemRandom()
    previous_signature = None
    if previous_theme:
        previous_signature = tuple(previous_theme.get(key) for key in ("background", "accent", "outgoing", "incoming"))

    selected_theme = None
    for _ in range(80):
        background_source, accent, outgoing, incoming = rng.sample(candidates, 4)
        background = mix(background_source, "#101820" if luminance(background_source) < 0.46 else "#FFFFFF", 0.16)
        theme = {
            "name": (previous_theme or {}).get("name", "Тема из фото"),
            "background": background,
            "accent": accent,
            "outgoing": outgoing,
            "incoming": incoming,
            "text": auto_text_color(background),
            "message_text": "#FFFFFF",
            "muted": auto_text_color(background),
            "text_auto": True,
            "message_text_auto": True,
            "muted_auto": True,
            "outgoing_opacity": (previous_theme or {}).get("outgoing_opacity", 92),
            "incoming_opacity": (previous_theme or {}).get("incoming_opacity", 92),
        }
        ensure_text_colors(theme)
        signature = tuple(theme.get(key) for key in ("background", "accent", "outgoing", "incoming"))
        selected_theme = theme
        if signature != previous_signature:
            break
    return selected_theme


def draw_font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rgba_tuple(color: str, opacity: int = 100):
    return (*hex_rgb(color), max(0, min(100, opacity)) * 255 // 100)


def draw_round_alpha(base: Image.Image, xy, radius: int, color: str, opacity: int):
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(xy, radius=radius, fill=rgba_tuple(color, opacity))
    base.alpha_composite(overlay)


def render_preview(theme: dict, wallpaper_path: str | None = None, image_palette: list[str] | None = None) -> bytes:
    """Render a Telegram Desktop-style mock preview; this is a visual mock-up, not a client screenshot."""
    width, height = 1180, 760
    bg = theme["background"]
    accent = theme["accent"]
    fg = theme["text"]
    message_fg = theme.get("message_text", fg)
    muted = theme["muted"]
    incoming = theme["incoming"]
    outgoing = theme["outgoing"]
    out_alpha = int(theme.get("outgoing_opacity", 100))
    in_alpha = int(theme.get("incoming_opacity", 100))

    canvas = Image.new("RGBA", (width, height), (*hex_rgb(bg), 255))
    d = ImageDraw.Draw(canvas)
    title_font = draw_font(24, True)
    body_font = draw_font(19)
    small_font = draw_font(15)
    bold_font = draw_font(18, True)

    sidebar_w = 340
    header_h = 84
    # Sidebar and header.
    d.rectangle((0, 0, sidebar_w, height), fill=(*hex_rgb(bg), 255))
    d.rectangle((sidebar_w, 0, width, header_h), fill=(*hex_rgb(mix(bg, fg, 0.025)), 255))
    d.line((sidebar_w, 0, sidebar_w, height), fill=(*hex_rgb(mix(bg, fg, 0.13)), 255), width=2)
    d.text((28, 25), "Telegram", fill=fg, font=title_font)
    d.rounded_rectangle((22, 88, 318, 132), radius=20, fill=(*hex_rgb(mix(bg, fg, 0.09)), 255))
    d.text((42, 100), "Поиск", fill=mix(fg, bg, 0.28), font=body_font)

    chats = [
        ("И", "Избранное", "Сохранённые сообщения", "12:42"),
        ("М", "Мира", "Хорошо, отправлю позже", "12:37"),
        ("Д", "Дизайн", "Новый макет готов", "12:21"),
        ("К", "Колледж", "Файл отправлен", "11:58"),
        ("А", "Арт-идеи", "Посмотри на эту палитру", "11:42"),
    ]
    row_y = 150
    active_bg = mix(bg, accent, 0.28)
    for index, (letter, name, last, stamp) in enumerate(chats):
        top = row_y + index * 92
        if index == 1:
            d.rounded_rectangle((10, top, sidebar_w - 10, top + 82), radius=13, fill=(*hex_rgb(active_bg), 255))
        avatar_color = accent if index in (0, 1, 3, 4) else mix(accent, fg, 0.18)
        d.ellipse((23, top + 12, 78, top + 67), fill=(*hex_rgb(avatar_color), 255))
        d.text((42, top + 25), letter, fill=contrast_color(avatar_color), font=bold_font)
        d.text((92, top + 13), name, fill=fg, font=bold_font)
        d.text((92, top + 43), last, fill=mix(fg, bg, 0.16), font=small_font)
        d.text((266, top + 15), stamp, fill=mix(fg, bg, 0.2), font=small_font)
        if index == 1:
            d.ellipse((297, top + 54, 308, top + 65), fill=(*hex_rgb(accent), 255))

    # Chat background: selected wallpaper if present, otherwise the main background.
    chat_box = (sidebar_w + 1, header_h, width, height - 78)
    if wallpaper_path and Path(wallpaper_path).exists():
        try:
            with Image.open(wallpaper_path) as wp:
                wp = ImageOps.exif_transpose(wp).convert("RGB")
                wp = ImageOps.fit(wp, (width - sidebar_w, height - header_h - 78), method=Image.Resampling.LANCZOS)
                canvas.paste(wp.convert("RGBA"), (sidebar_w, header_h))
                overlay = Image.new("RGBA", (width - sidebar_w, height - header_h - 78), (*hex_rgb(bg), 54))
                canvas.alpha_composite(overlay, (sidebar_w, header_h))
        except Exception:
            d.rectangle(chat_box, fill=(*hex_rgb(bg), 255))
    else:
        d.rectangle(chat_box, fill=(*hex_rgb(bg), 255))

    # Repaint top header to stay solid over wallpaper.
    d.rectangle((sidebar_w + 2, 0, width, header_h), fill=(*hex_rgb(bg), 255))
    d.ellipse((sidebar_w + 25, 17, sidebar_w + 72, 64), fill=(*hex_rgb(accent), 255))
    d.text((sidebar_w + 43, 28), "М", fill=contrast_color(accent), font=bold_font)
    d.text((sidebar_w + 88, 17), "Мира", fill=fg, font=bold_font)
    d.text((sidebar_w + 88, 47), "в сети", fill=accent, font=small_font)
    d.ellipse((width - 60, 33, width - 47, 46), fill=(*hex_rgb(accent), 255))

    # Date separator.
    d.rounded_rectangle((sidebar_w + 420, 105, sidebar_w + 515, 137), radius=15, fill=(*hex_rgb(mix(bg, fg, 0.15)), 235))
    d.text((sidebar_w + 443, 112), "Сегодня", fill=fg, font=small_font)

    # Message bubbles with requested transparency.
    draw_round_alpha(canvas, (sidebar_w + 32, 180, sidebar_w + 500, 272), 19, incoming, in_alpha)
    d = ImageDraw.Draw(canvas)
    d.text((sidebar_w + 55, 199), "Привет! Как тебе новая тема?", fill=message_fg, font=body_font)
    d.text((sidebar_w + 55, 235), "Подобрала несколько цветов.", fill=message_fg, font=body_font)
    d.text((sidebar_w + 427, 246), "12:35", fill=mix(fg, incoming, 0.22), font=small_font)

    draw_round_alpha(canvas, (sidebar_w + 330, 300, width - 28, 390), 19, outgoing, out_alpha)
    d = ImageDraw.Draw(canvas)
    d.text((sidebar_w + 355, 320), "Мне нравится этот вариант!", fill=message_fg, font=body_font)
    d.text((sidebar_w + 355, 354), "Акцент хорошо выделяется.", fill=message_fg, font=body_font)
    d.text((width - 126, 365), "12:36  ✓✓", fill=accent, font=small_font)

    draw_round_alpha(canvas, (sidebar_w + 32, 418, sidebar_w + 540, 502), 19, incoming, in_alpha)
    d = ImageDraw.Draw(canvas)
    d.text((sidebar_w + 55, 440), "Ссылки, файлы и значки тоже", fill=message_fg, font=body_font)
    d.text((sidebar_w + 55, 472), "подстроятся под акцентный цвет.", fill=message_fg, font=body_font)

    # A link sample and file/voice message affordances.
    d.text((sidebar_w + 54, 528), "example.com/theme", fill=accent, font=body_font)
    d.rounded_rectangle((sidebar_w + 32, 567, sidebar_w + 485, 630), radius=16, fill=(*hex_rgb(mix(bg, fg, 0.10)), 245))
    d.ellipse((sidebar_w + 48, 578, sidebar_w + 91, 621), fill=(*hex_rgb(accent), 255))
    d.text((sidebar_w + 62, 587), "▶", fill=contrast_color(accent), font=small_font)
    d.text((sidebar_w + 108, 578), "Голосовое сообщение", fill=fg, font=small_font)
    d.line((sidebar_w + 108, 609, sidebar_w + 428, 609), fill=(*hex_rgb(accent), 255), width=4)
    d.text((sidebar_w + 435, 595), "0:18", fill=fg, font=small_font)

    # Bottom input panel.
    d.rectangle((sidebar_w + 1, height - 78, width, height), fill=(*hex_rgb(bg), 255))
    d.line((sidebar_w + 1, height - 78, width, height - 78), fill=(*hex_rgb(mix(bg, fg, 0.12)), 255), width=2)
    d.text((sidebar_w + 30, height - 53), "＋", fill=accent, font=title_font)
    d.rounded_rectangle((sidebar_w + 78, height - 64, width - 94, height - 16), radius=22, fill=(*hex_rgb(mix(bg, fg, 0.07)), 255))
    d.text((sidebar_w + 100, height - 52), "Сообщение…", fill=mix(fg, bg, 0.35), font=small_font)
    d.text((width - 67, height - 54), "➤", fill=accent, font=title_font)

    # In photo mode, show a compact visual swatch grid in the unused lower
    # part of the sidebar so the user can see the extracted colors while
    # choosing their HEX values from the Telegram buttons.
    if image_palette:
        d.text((22, 620), "ЦВЕТА ИЗ ФОТО", fill=muted, font=small_font)
        swatch_font = draw_font(10, True)
        for index, color in enumerate(image_palette[:8]):
            col, row = index % 4, index // 4
            x = 22 + col * 74
            y = 650 + row * 34
            d.rounded_rectangle((x, y, x + 68, y + 28), radius=6, fill=(*hex_rgb(color), 255))
            d.text((x + 4, y + 8), color, fill=contrast_color(color), font=swatch_font)

    # Tiny color strip, no hex values.
    strip_y = height - 7
    for i, col in enumerate((bg, accent, incoming, outgoing)):
        d.rectangle((sidebar_w + i * ((width - sidebar_w) // 4), strip_y, sidebar_w + (i + 1) * ((width - sidebar_w) // 4), height), fill=col)

    out = io.BytesIO()
    # Skipping the slow Huffman optimisation noticeably reduces preview encoding time.
    canvas.convert("RGB").save(out, format="JPEG", quality=85)
    return out.getvalue()


def create_desktop_colors(theme: dict) -> dict:
    bg, accent, fg = theme["background"], theme["accent"], theme["text"]
    message_fg = theme.get("message_text", fg)
    incoming = alpha_hex(theme["incoming"], theme.get("incoming_opacity", 100))
    outgoing = alpha_hex(theme["outgoing"], theme.get("outgoing_opacity", 100))
    muted = fg
    soft_bg = mix(bg, fg, 0.08)
    active_bg = mix(bg, accent, 0.28)
    soft_accent = mix(accent, bg, 0.22)
    accent_alpha = alpha_hex(accent, 38)
    accent_alpha_strong = alpha_hex(accent, 58)
    text_on_accent = contrast_color(accent)
    selected_in_bg = mix(theme["incoming"], accent, 0.52)
    selected_out_bg = mix(theme["outgoing"], accent, 0.52)
    selected_in_fg = contrast_color(selected_in_bg)
    selected_out_fg = contrast_color(selected_out_bg)
    selected_search_bg = mix(bg, accent, 0.58)
    selected_search_fg = contrast_color(selected_search_bg)

    colors = {
        # Base and universal text.
        "windowBg": bg, "windowFg": fg, "windowBgOver": soft_bg,
        "windowBgRipple": mix(bg, fg, 0.15), "windowFgOver": fg,
        "windowSubTextFg": muted, "windowSubTextFgOver": fg,
        "windowBoldFg": fg, "windowBoldFgOver": fg,
        "windowBgActive": accent, "windowFgActive": text_on_accent,
        "windowActiveTextFg": accent, "windowShadowFg": "#000000",
        "windowShadowFgFallback": bg, "shadowFg": alpha_hex(fg, 10),
        "slideFadeOutBg": alpha_hex(bg, 85), "slideFadeOutShadowFg": "windowShadowFg",
        "imageBg": bg, "imageBgTransparent": "#FFFFFF",
        # Buttons, menus, inputs and panels.
        "activeButtonBg": accent, "activeButtonBgOver": mix(accent, fg, 0.12),
        "activeButtonBgRipple": alpha_hex(accent, 48), "activeButtonFg": text_on_accent,
        "activeButtonFgOver": text_on_accent, "activeButtonSecondaryFg": text_on_accent,
        "activeButtonSecondaryFgOver": text_on_accent,
        "activeLineFg": accent, "activeLineFgError": "#D84D4D",
        "lightButtonBg": bg, "lightButtonBgOver": soft_bg,
        "lightButtonBgRipple": alpha_hex(accent, 25), "lightButtonFg": accent,
        "lightButtonFgOver": accent,
        "attentionButtonFg": accent, "attentionButtonFgOver": accent,
        "attentionButtonBgOver": alpha_hex(accent, 18), "attentionButtonBgRipple": alpha_hex(accent, 24),
        "outlineButtonBg": bg, "outlineButtonBgOver": soft_bg,
        "outlineButtonOutlineFg": alpha_hex(fg, 38), "outlineButtonBgRipple": alpha_hex(accent, 25),
        "menuBg": bg, "menuBgOver": soft_bg, "menuBgRipple": alpha_hex(accent, 22),
        "menuIconFg": accent, "menuIconFgOver": accent, "menuSubmenuArrowFg": fg,
        "menuFgDisabled": muted, "menuSeparatorFg": alpha_hex(fg, 18),
        "scrollBarBg": alpha_hex(accent, 38), "scrollBarBgOver": alpha_hex(accent, 65),
        "scrollBg": alpha_hex(bg, 20), "scrollBgOver": alpha_hex(accent, 14),
        "smallCloseIconFg": fg, "smallCloseIconFgOver": accent,
        "radialFg": accent, "radialBg": alpha_hex(bg, 65),
        "placeholderFg": muted, "placeholderFgActive": fg,
        "inputBorderFg": accent, "filterInputBorderFg": accent,
        "filterInputActiveBg": bg, "filterInputInactiveBg": soft_bg,
        "checkboxFg": accent, "sliderBgInactive": alpha_hex(fg, 28), "sliderBgActive": accent,
        "tooltipBg": mix(bg, fg, 0.16), "tooltipFg": fg, "tooltipBorderFg": accent,
        # Window title and system tray.
        "titleShadow": alpha_hex(fg, 8), "titleBg": bg, "titleBgActive": bg,
        "titleButtonBg": bg, "titleButtonFg": muted, "titleButtonBgOver": soft_bg,
        "titleButtonFgOver": accent, "titleButtonBgActive": bg, "titleButtonFgActive": muted,
        "titleButtonBgActiveOver": soft_bg, "titleButtonFgActiveOver": accent,
        "titleButtonCloseBg": bg, "titleButtonCloseFg": muted,
        "titleButtonCloseBgOver": "#E81123", "titleButtonCloseFgOver": "#FFFFFF",
        "titleButtonCloseBgActive": bg, "titleButtonCloseFgActive": muted,
        "titleButtonCloseBgActiveOver": "#E81123", "titleButtonCloseFgActiveOver": "#FFFFFF",
        "titleFg": muted, "titleFgActive": fg,
        "trayCounterBg": accent, "trayCounterBgMute": soft_bg, "trayCounterFg": text_on_accent,
        "trayCounterBgMacInvert": accent, "trayCounterFgMacInvert": text_on_accent,
        "layerBg": alpha_hex(bg, 75),
        # Dialogs and sidebar folders.
        "dialogsMenuIconFg": accent, "dialogsMenuIconFgOver": accent,
        "dialogsBg": bg, "dialogsNameFg": fg, "dialogsChatIconFg": accent,
        "dialogsDateFg": muted, "dialogsTextFg": fg, "dialogsTextFgService": accent,
        "dialogsDraftFg": accent, "dialogsVerifiedIconBg": accent,
        "dialogsVerifiedIconFg": text_on_accent, "dialogsSendingIconFg": accent,
        "dialogsSentIconFg": accent, "dialogsUnreadBg": accent,
        "dialogsUnreadBgMuted": soft_accent, "dialogsUnreadFg": text_on_accent,
        "dialogsArchiveFg": fg, "dialogsOnlineBadgeFg": accent, "dialogsScamFg": accent,
        "dialogsBgOver": soft_bg, "dialogsNameFgOver": fg, "dialogsChatIconFgOver": accent,
        "dialogsDateFgOver": fg, "dialogsTextFgOver": fg, "dialogsTextFgServiceOver": accent,
        "dialogsDraftFgOver": accent, "dialogsVerifiedIconBgOver": accent,
        "dialogsVerifiedIconFgOver": text_on_accent, "dialogsSendingIconFgOver": accent,
        "dialogsSentIconFgOver": accent, "dialogsUnreadBgOver": accent,
        "dialogsUnreadBgMutedOver": soft_accent, "dialogsUnreadFgOver": text_on_accent,
        "dialogsArchiveFgOver": fg, "dialogsScamFgOver": accent,
        "dialogsBgActive": active_bg, "dialogsNameFgActive": fg,
        "dialogsChatIconFgActive": accent, "dialogsDateFgActive": fg,
        "dialogsTextFgActive": fg, "dialogsTextFgServiceActive": accent,
        "dialogsDraftFgActive": accent, "dialogsVerifiedIconBgActive": accent,
        "dialogsVerifiedIconFgActive": text_on_accent, "dialogsSendingIconFgActive": accent,
        "dialogsSentIconFgActive": accent, "dialogsUnreadBgActive": accent,
        "dialogsUnreadBgMutedActive": soft_accent, "dialogsUnreadFgActive": text_on_accent,
        "dialogsOnlineBadgeFgActive": accent, "dialogsScamFgActive": accent,
        "dialogsRippleBg": alpha_hex(fg, 12), "dialogsRippleBgActive": alpha_hex(accent, 32),
        "dialogsMentionIconFg": accent, "dialogsReactionIconFg": accent, "dialogsPollIconFg": accent,
        "searchedBarBg": soft_bg, "searchedBarFg": accent,
        "searchedTextMatchBg": alpha_hex(accent, 62), "searchedTextMatchFg": selected_search_fg,
        "searchedTextCurrentMatchBg": accent, "searchedTextCurrentMatchFg": text_on_accent,
        # Sidebar folder panel: explicit keys that were previously missing.
        "sideBarBg": bg, "sideBarBgActive": active_bg, "sideBarBgRipple": alpha_hex(accent, 34),
        "sideBarTextFg": fg, "sideBarTextFgActive": accent,
        "sideBarIconFg": accent, "sideBarIconFgActive": accent,
        "sideBarIconFgOver": accent, "sideBarTextFgOver": accent,
        "sideBarBadgeBg": accent, "sideBarBadgeBgActive": accent,
        "sideBarBadgeBgMuted": soft_accent, "sideBarBadgeBgMutedActive": accent,
        "sideBarBadgeFg": text_on_accent,
        "sideBarBadgeFgActive": text_on_accent, "sideBarBadgeFgOver": text_on_accent,
        "sideBarBadgeBgOver": accent, "sideBarBadgeBgMutedOver": accent,
        "sideBarSeparatorFg": alpha_hex(fg, 16), "sideBarItemBgOver": soft_bg,
        "sideBarItemBgActive": active_bg, "sideBarItemRippleBg": alpha_hex(accent, 28),
        # Panels, stickers and premium gradients.
        "topBarBg": bg, "emojiPanBg": bg, "emojiPanCategories": bg,
        "emojiPanHeaderFg": fg, "emojiPanHeaderBg": bg,
        "emojiIconFg": accent, "emojiSubIconFgActive": accent,
        "stickerPanDeleteBg": alpha_hex(accent, 32), "stickerPanDeleteFg": accent,
        "stickerPreviewBg": alpha_hex(bg, 70),
        "stickerPanPremium1": accent, "stickerPanPremium2": mix(accent, fg, 0.28),
        # Message text, text selection, links and bubbles.
        "historyTextInFg": message_fg, "historyTextInFgSelected": selected_in_fg,
        "historyTextOutFg": message_fg, "historyTextOutFgSelected": selected_out_fg,
        "historyLinkInFg": accent, "historyLinkInFgSelected": selected_in_fg,
        "historyLinkOutFg": accent, "historyLinkOutFgSelected": selected_out_fg,
        "historyFileNameInFg": message_fg, "historyFileNameInFgSelected": selected_in_fg,
        "historyFileNameOutFg": message_fg, "historyFileNameOutFgSelected": selected_out_fg,
        "historyOutIconFg": accent, "historyOutIconFgSelected": selected_out_fg,
        "historyIconFgInverted": text_on_accent, "historySendingOutIconFg": accent,
        "historySendingInIconFg": accent, "historySendingInvertedIconFg": text_on_accent,
        "historyCallArrowInFg": accent, "historyCallArrowInFgSelected": selected_in_fg,
        "historyCallArrowMissedInFg": accent, "historyCallArrowMissedInFgSelected": selected_in_fg,
        "historyCallArrowOutFg": accent, "historyCallArrowOutFgSelected": selected_out_fg,
        "historyUnreadBarBg": soft_bg, "historyUnreadBarBorder": alpha_hex(fg, 16),
        "historyUnreadBarFg": accent, "historyForwardChooseBg": alpha_hex(bg, 72),
        "historyForwardChooseFg": fg,
        # Supported chat-list mention/reaction/poll markers use the chosen accent.
        "dialogsMentionIconFg": accent, "dialogsReactionIconFg": accent, "dialogsPollIconFg": accent,
        # Selection overlays are strong enough to remain visible; foreground is
        # calculated against the resulting selected bubble, not the full accent.
        "msgInBg": incoming, "msgInBgSelected": selected_in_bg,
        "msgOutBg": outgoing, "msgOutBgSelected": selected_out_bg,
        "msgSelectOverlay": alpha_hex(accent, 52), "msgStickerOverlay": alpha_hex(accent, 58),
        "msgInServiceFg": accent, "msgInServiceFgSelected": selected_in_fg,
        "msgOutServiceFg": accent, "msgOutServiceFgSelected": selected_out_fg,
        "msgInShadow": alpha_hex(bg, 10), "msgInShadowSelected": alpha_hex(accent, 14),
        "msgOutShadow": alpha_hex(bg, 10), "msgOutShadowSelected": alpha_hex(accent, 14),
        "msgInDateFg": message_fg, "msgInDateFgSelected": selected_in_fg,
        "msgOutDateFg": accent, "msgOutDateFgSelected": selected_out_fg,
        "msgServiceFg": accent, "msgServiceBg": alpha_hex(bg, 75),
        "msgServiceBgSelected": alpha_hex(accent, 35),
        "msgInReplyBarColor": accent, "msgInReplyBarSelColor": selected_in_fg,
        "msgOutReplyBarColor": accent, "msgOutReplyBarSelColor": selected_out_fg,
        "msgImgReplyBarColor": accent, "msgInMonoFg": accent, "msgOutMonoFg": accent,
        "msgInMonoFgSelected": selected_in_fg, "msgOutMonoFgSelected": selected_out_fg,
        "msgDateImgFg": fg, "msgDateImgFgSelected": text_on_accent,
        # No-icon avatars / saved messages / initials use accent.
        "historyPeerUserpicFg": text_on_accent, "historyPeerSavedMessagesBg": accent,
        "historyPeerArchiveUserpicBg": accent,
        "historyPeer1NameFg": accent, "historyPeer1NameFgSelected": selected_in_fg,
        "historyPeer1UserpicBg": accent, "historyPeer1UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer2NameFg": accent, "historyPeer2NameFgSelected": selected_in_fg,
        "historyPeer2UserpicBg": accent, "historyPeer2UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer3NameFg": accent, "historyPeer3NameFgSelected": selected_in_fg,
        "historyPeer3UserpicBg": accent, "historyPeer3UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer4NameFg": accent, "historyPeer4NameFgSelected": selected_in_fg,
        "historyPeer4UserpicBg": accent, "historyPeer4UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer5NameFg": accent, "historyPeer5NameFgSelected": selected_in_fg,
        "historyPeer5UserpicBg": accent, "historyPeer5UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer6NameFg": accent, "historyPeer6NameFgSelected": selected_in_fg,
        "historyPeer6UserpicBg": accent, "historyPeer6UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer7NameFg": accent, "historyPeer7NameFgSelected": selected_in_fg,
        "historyPeer7UserpicBg": accent, "historyPeer7UserpicBg2": mix(accent, fg, 0.18),
        "historyPeer8NameFg": accent, "historyPeer8NameFgSelected": selected_in_fg,
        "historyPeer8UserpicBg": accent, "historyPeer8UserpicBg2": mix(accent, fg, 0.18),
        "historyPeerSavedMessagesBg2": mix(accent, fg, 0.18),
        "settingsIconBg1": accent, "settingsIconBg2": accent,
        "settingsIconBg3": accent, "settingsIconBg4": accent,
        "settingsIconBg5": accent, "settingsIconBg6": accent,
        "settingsIconBg8": accent, "settingsIconBgArchive": accent,
        "settingsIconFg": text_on_accent,
        # Voice, files, media, checkmarks and action icons: no inherited green/cyan.
        "historyFileInIconFg": accent, "historyFileInIconFgSelected": selected_in_fg,
        "historyFileInRadialFg": accent, "historyFileOutIconFg": accent,
        "historyFileOutIconFgSelected": selected_out_fg, "historyFileOutRadialFg": accent,
        "historyFileOutRadialFgSelected": selected_out_fg, "historyFileThumbIconFg": accent,
        "historyFileThumbIconFgSelected": selected_in_fg, "historyFileThumbRadialFg": accent,
        "historyFileThumbRadialFgSelected": selected_in_fg, "historyVideoMessageProgressFg": accent,
        "historyFileInRadialFgSelected": selected_in_fg,
        "msgFileThumbLinkInFg": accent, "msgFileThumbLinkInFgSelected": selected_in_fg,
        "msgFileThumbLinkOutFg": accent, "msgFileThumbLinkOutFgSelected": selected_out_fg,
        "msgFileInBg": accent, "msgFileInBgOver": accent, "msgFileInBgSelected": accent,
        "msgFileOutBg": accent, "msgFileOutBgSelected": accent,
        "msgFile1Bg": accent, "msgFile1BgDark": accent, "msgFile1BgOver": accent, "msgFile1BgSelected": accent,
        "msgFile2Bg": accent, "msgFile2BgDark": accent, "msgFile2BgOver": accent, "msgFile2BgSelected": accent,
        "msgFile3Bg": accent, "msgFile3BgDark": accent, "msgFile3BgOver": accent, "msgFile3BgSelected": accent,
        "msgFile4Bg": accent, "msgFile4BgDark": accent, "msgFile4BgOver": accent, "msgFile4BgSelected": accent,
        "msgDateImgBg": alpha_hex(accent, 78), "msgDateImgBgOver": alpha_hex(accent, 90),
        "msgDateImgBgSelected": alpha_hex(accent, 85),
        "historyScrollBarBg": alpha_hex(accent, 48), "historyScrollBarBgOver": alpha_hex(accent, 72),
        "historyScrollBg": alpha_hex(accent, 20), "historyScrollBgOver": alpha_hex(accent, 32),
        "msgBotKbIconFg": accent, "msgBotKbOverBgAdd": alpha_hex(accent, 15),
        "msgBotKbRippleBg": alpha_hex(accent, 22),
        "msgWaveformInActive": accent, "msgWaveformInActiveSelected": selected_in_fg,
        "msgWaveformInInactive": alpha_hex(accent, 34), "msgWaveformInInactiveSelected": alpha_hex(selected_in_fg, 50),
        "msgWaveformOutActive": accent, "msgWaveformOutActiveSelected": selected_out_fg,
        "msgWaveformOutInactive": alpha_hex(accent, 34), "msgWaveformOutInactiveSelected": alpha_hex(selected_out_fg, 50),
        "mediaInFg": accent, "mediaInFgSelected": selected_in_fg,
        "mediaOutFg": accent, "mediaOutFgSelected": selected_out_fg,
        "historyComposeAreaBg": bg, "historyComposeAreaFg": accent,
        "historyComposeAreaFgService": accent, "historyComposeIconFg": accent,
        "historyComposeIconFgOver": accent, "historySendIconFg": accent,
        "historySendIconFgOver": accent, "historyPinnedBg": bg,
        "historyReplyBg": bg, "historyReplyIconFg": accent,
        "historyReplyCancelFg": accent, "historyReplyCancelFgOver": accent,
        "historyComposeButtonBg": bg, "historyComposeButtonBgOver": soft_bg,
        "historyComposeButtonBgRipple": alpha_hex(accent, 26),
        "mediaviewFileBg": bg, "mediaviewFileNameFg": fg,
        "mediaviewFileSizeFg": accent, "mediaviewFileRedCornerFg": accent,
        "mediaviewFileYellowCornerFg": accent, "mediaviewFileGreenCornerFg": accent,
        "mediaviewFileBlueCornerFg": accent, "mediaviewFileExtFg": accent,
        "mediaviewMenuBg": bg, "mediaviewMenuBgOver": soft_bg,
        "mediaviewMenuBgRipple": alpha_hex(accent, 24), "mediaviewMenuFg": accent,
        "mediaviewBg": alpha_hex(bg, 92), "mediaviewVideoBg": bg,
        "mediaviewControlBg": alpha_hex(bg, 55), "mediaviewControlFg": accent,
        "mediaviewCaptionBg": alpha_hex(bg, 75), "mediaviewCaptionFg": fg,
        "mediaviewTextLinkFg": accent, "mediaviewSaveMsgBg": bg,
        "mediaviewSaveMsgFg": fg, "mediaviewPlaybackActive": accent,
        "mediaviewPlaybackInactive": alpha_hex(accent, 25),
        "mediaviewPlaybackActiveOver": accent, "mediaviewPlaybackInactiveOver": alpha_hex(accent, 35),
        "mediaviewPlaybackProgressFg": fg, "mediaviewPlaybackIconFg": accent,
        "mediaviewPlaybackIconFgOver": accent, "mediaviewPipControlsFg": accent,
        "mediaviewPipControlsFgOver": accent, "mediaviewPipPlaybackActive": accent,
        "mediaviewPipPlaybackInactive": alpha_hex(accent, 25),
        "mediaviewTransparentBg": bg, "mediaviewTransparentFg": fg,
        "historyToDownBg": bg, "historyToDownBgOver": soft_bg,
        "historyToDownBgRipple": alpha_hex(accent, 24),
        "historyToDownFg": accent, "historyToDownFgOver": accent,
        "historyToDownShadow": alpha_hex(bg, 25),
        "overviewCheckBg": alpha_hex(accent, 22), "overviewCheckBgActive": accent,
        "overviewCheckBorder": bg, "overviewCheckFgActive": text_on_accent,
        "overviewPhotoSelectOverlay": alpha_hex(accent, 30),
        "profileStatusFgOver": accent, "profileVerifiedCheckBg": accent,
        "profileVerifiedCheckFg": text_on_accent, "profileAdminStartFg": accent,
        "contactsBg": bg, "contactsBgOver": soft_bg, "contactsNameFg": fg,
        "contactsStatusFg": fg, "contactsStatusFgOver": fg, "contactsStatusFgOnline": accent,
        "notificationBg": bg, "notificationsBoxMonitorFg": fg,
        "notificationsBoxScreenBg": active_bg, "notificationSampleUserpicFg": accent,
        "notificationSampleCloseFg": fg, "notificationSampleTextFg": fg,
        "notificationSampleNameFg": fg, "mainMenuBg": bg,
        "mainMenuCoverBg": accent, "mainMenuCoverFg": text_on_accent,
        "mainMenuCloudFg": text_on_accent, "mainMenuCloudBg": accent,
        "mediaPlayerBg": bg, "mediaPlayerActiveFg": accent,
        "mediaPlayerInactiveFg": alpha_hex(accent, 35), "mediaPlayerDisabledFg": alpha_hex(accent, 22),
        "toastBg": mix(bg, fg, 0.15), "toastFg": fg,
        # Premium button gradients are deliberately tied to the chosen accent.
        "premiumButtonBg1": accent, "premiumButtonBg2": mix(accent, fg, 0.25),
        "premiumButtonBg3": mix(accent, bg, 0.20), "premiumButtonFg": text_on_accent,
        "premiumIconBg1": accent, "premiumIconBg2": mix(accent, fg, 0.20),
        "premiumIconBg3": mix(accent, bg, 0.20),
    }
    return colors


def desktop_palette_text(theme: dict) -> bytes:
    colors = create_desktop_colors(theme)
    header = [
        "// Theme Maker — Telegram Desktop palette",
        "// Colors use RGB/RGBA hexadecimal notation. Alpha is the last byte.",
        "// Text foregrounds are automatically chosen for the main background.",
        "",
    ]
    body = [f"{key}: {value};" for key, value in colors.items()]
    return ("\n".join(header + body) + "\n").encode("utf-8")


def create_desktop_theme(theme: dict, wallpaper_path: Path | None) -> bytes:
    """Create Telegram Desktop .tdesktop-theme; wallpaper is embedded in ZIP when provided."""
    color_scheme = desktop_palette_text(theme)
    if not wallpaper_path or not wallpaper_path.exists():
        return color_scheme
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("colors.tdesktop-theme", color_scheme)
        archive.write(wallpaper_path, "background.jpg")
    return stream.getvalue()


def load_android_theme_keys() -> list[str]:
    """Known Android theme keys bundled from Telegram's shipped theme plus compatibility keys."""
    path = ROOT / "themes" / "android_keys.txt"
    keys = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    keys.update("dialogBackground dialogTextBlack dialogLinkSelection dialogTextBlue2 dialogTextBlue4 dialogTextGray dialogTextGray2 dialogTextGray3 dialogTextGray4 dialogTextHint dialogInputField dialogInputFieldActivated dialogCheckboxSquareCheck dialogCheckboxSquareUnchecked dialogCheckboxSquareDisabled dialogScrollGlow dialogRoundCheckBoxCheck dialogRadioBackground dialogLineProgressBackground dialogButtonSelector dialogIcon dialogGrayLine windowBackgroundWhiteInputField windowBackgroundWhiteInputFieldActivated windowBackgroundWhiteBlueText2 windowBackgroundWhiteBlueText3 windowBackgroundWhiteBlueText4 windowBackgroundWhiteBlueText5 windowBackgroundWhiteBlueText6 windowBackgroundWhiteGrayText2 windowBackgroundWhiteGrayText3 windowBackgroundWhiteGrayText4 windowBackgroundWhiteGrayText5 windowBackgroundWhiteGrayText6 windowBackgroundWhiteGrayText7 windowBackgroundWhiteGrayText8 windowBackgroundWhiteHintText windowBackgroundWhiteLinkSelection windowBackgroundGrayShadow emptyListPlaceholder fastScrollInactive fastScrollText inappPlayerPerformer inappPlayerTitle inappPlayerBackground inappPlayerClose returnToCallText contextProgressInner1 contextProgressOuter1 contextProgressInner3 contextProgressOuter3 avatar_text avatar_backgroundArchived avatar_backgroundRed avatar_backgroundOrange avatar_backgroundViolet avatar_backgroundGreen avatar_backgroundCyan avatar_backgroundPink actionBarActionModeDefault actionBarActionModeDefaultTop actionBarActionModeDefaultIcon actionBarActionModeDefaultSelector chats_unreadCounterMuted chats_pinnedIcon chats_archivePinBackground chats_archiveText chats_menuItemText chats_menuItemIcon chats_sentErrorIcon chats_verifiedCheck chats_muteIcon chats_actionIcon chats_actionPressedBackground chat_outSentClock chat_outSentClockSelected chat_outReplyMessageText chat_outReplyMediaMessageText chat_outReplyMediaMessageSelectedText chat_outSiteNameText chat_inBubbleShadow chat_outBubbleShadow chat_inBubbleSelected chat_outBubbleSelected chat_outMenu chat_outMenuSelected chat_outForwardedNameText chat_inForwardedNameText chat_outViaBotNameText chat_inViaBotNameText chat_outReplyLine chat_inReplyLine chat_outReplyNameText chat_inReplyNameText chat_inReplyMessageText chat_inReplyMediaMessageText chat_inReplyMediaMessageSelectedText chat_inSiteNameText chat_inContactNameText chat_inContactPhoneText chat_outContactNameText chat_outContactPhoneText chat_outAudioPerfomerText chat_inAudioPerfomerText chat_outAudioDurationText chat_inAudioDurationText chat_inAudioSeekbar chat_inAudioSeekbarSelected chat_inAudioSeekbarFill chat_outAudioSeekbar chat_outAudioSeekbarSelected chat_outAudioSeekbarFill chat_inVoiceSeekbar chat_inVoiceSeekbarSelected chat_inVoiceSeekbarFill chat_outVoiceSeekbar chat_outVoiceSeekbarSelected chat_outVoiceSeekbarFill chat_inFileProgress chat_outFileProgress chat_inFileNameText chat_outFileNameText chat_inFileInfoText chat_outFileInfoText chat_inFileBackground chat_outFileBackground chat_inFileBackgroundSelected chat_outFileBackgroundSelected chat_serviceText chat_serviceLink chat_serviceIcon chat_serviceBackground chat_serviceBackgroundSelected chat_messagePanelBackground chat_messagePanelShadow chat_messagePanelText chat_messagePanelHint chat_messagePanelIcons chat_messagePanelSend key_chat_messagePanelVoiceLock key_chat_messagePanelVoiceLockBackground key_chat_messagePanelVoiceLockShadow chat_topPanelBackground chat_topPanelClose chat_topPanelLine chat_topPanelTitle chat_topPanelMessage chat_addContact chat_inLoader chat_inLoaderSelected chat_inLoaderPhoto chat_mediaLoaderPhoto chat_mediaLoaderPhotoSelected chat_mediaLoaderPhotoIcon chat_mediaLoaderPhotoIconSelected chat_inLocationBackground chat_inLocationIcon chat_inContactBackground chat_inContactIcon chat_replyPanelIcons chat_replyPanelClose chat_replyPanelName chat_replyPanelLine chat_searchPanelIcons chat_searchPanelText chat_secretChatStatusText chat_fieldOverlayText chat_stickersHintPanel chat_botSwitchToInlineText chat_unreadMessagesStartArrowIcon chat_unreadMessagesStartBackground chat_inlineResultIcon chat_emojiPanelBackground chat_emojiPanelShadowLine chat_emojiPanelEmptyText chat_emojiPanelIcon chat_emojiPanelIconSelected chat_emojiPanelStickerPackSelector chat_emojiPanelBackspace chat_emojiPanelTrendingTitle chat_emojiPanelTrendingDescription chat_botKeyboardButtonText chat_botKeyboardButtonBackground chat_botKeyboardButtonBackgroundPressed chat_messagePanelVoicePressed chat_messagePanelVoiceDelete chat_messagePanelVoiceDuration chat_recordedVoicePlayPause chat_recordedVoiceProgress chat_recordedVoiceProgressInner chat_recordVoiceCancel chat_recordTime chat_messagePanelCancelInlineBot chat_gifSaveHintText chat_gifSaveHintBackground chat_goDownButton chat_goDownButtonIcon chat_goDownButtonCounter chat_goDownButtonCounterBackground profile_verifiedBackground profile_verifiedCheck sharedMedia_startStopLoadIcon sharedMedia_linkPlaceholder sharedMedia_linkPlaceholderText featuredStickers_addedIcon featuredStickers_buttonProgress featuredStickers_addButton featuredStickers_addButtonPressed featuredStickers_buttonText featuredStickers_unread stickers_menu stickers_menuSelector groupcreate_hintText groupcreate_cursor groupcreate_sectionShadow groupcreate_sectionText groupcreate_spanText groupcreate_spanBackground login_progressInner login_progressOuter picker_disabledButton picker_badgeText location_sendLocationIcon files_folderIcon files_folderIconBackground files_iconText sessions_devicesImage calls_callReceivedRedIcon player_actionBarSelector player_actionBarTitle player_actionBarSubtitle player_actionBarItems player_background player_progressBackground player_button".split())
    # Core surfaces and section keys missing from the previous bundled baseline.
    # These are especially important: Telegram may fall back to a white default
    # when windowBackgroundWhite is absent from the exported .attheme file.
    keys.update({
        "windowBackgroundWhite", "windowBackgroundGray", "windowBackgroundWhiteBlackText",
        "windowBackgroundWhiteGrayText", "windowBackgroundWhiteBlueText",
        "windowBackgroundWhiteGreenText", "windowBackgroundWhiteRedText",
        "windowBackgroundWhiteValueText", "windowBackgroundWhiteLinkText",
        "windowBackgroundWhiteHintText", "windowBackgroundWhiteInputField",
        "windowBackgroundWhiteInputFieldActivated", "windowBackgroundWhiteLinkSelection",
        "dialogBackground", "dialogInputField", "dialogInputFieldActivated",
        "graySection", "graySectionText", "graySectionShadow",
    })
    # Additional aliases found in different Android builds/theme editor exports.
    keys.update({
        "telegram_color_text", "chats_secreticon", "chat_messageLinkIn", "chat_messageLinkOut",
        "chat_inQuote", "chat_outQuote", "chat_inQuoteSelected", "chat_outQuoteSelected",
        "chat_inTextSelectionHighlight", "chat_outTextSelectionHighlight",
        "chat_inSentCheck", "chat_outSentCheckRead", "chat_outSentCheckSelected",
        "chat_inVoiceSeekbarSelected", "chat_outVoiceSeekbarSelected",
        "chat_inFileIcon", "chat_outFileIcon", "chat_messagePanelVoiceIcon",
        "chats_tabUnreadActiveBackground", "chats_tabUnreadUnactiveBackground",
        "chats_secretIcon", "chats_secretName", "chats_draft", "chats_actionMessage",
        "chats_sentCheck", "chats_sentClock", "chats_verifiedBackground",
        "chats_archiveBackground", "chats_archivePinBackground", "chats_archiveText",
        "chats_unreadCounterText", "chats_actionIcon", "chats_verifiedCheck", "profile_actionIcon",
        "profile_verifiedCheck", "files_folderIcon", "files_iconText",
        "chat_botKeyboardButtonText", "chat_goDownButtonIcon", "chat_goDownButtonCounter",
        "chat_messagePanelVoiceDuration", "chat_recordedVoicePlayPause", "picker_badgeText",
        "featuredStickers_buttonText", "profile_actionIconText", "chat_serviceIcon",
        "chat_msgIvButtonPrimaryOut", "chat_msgIvButtonPrimaryOutPressed", "chat_msgIvButtonPrimaryOutText",
        "chat_msgIvButtonPrimaryIn", "chat_msgIvButtonPrimaryInPressed", "chat_msgIvButtonPrimaryInText",
        "chat_messageTextIn", "chat_messageTextOut", "chat_messageTextInSelected", "chat_messageTextOutSelected",
        "chat_textSelectionBackground", "chat_textSelectionForeground", "chat_linkSelectionBackground",
        "chat_inlineButtonBackground", "chat_inlineButtonText", "chat_miniAppButtonBackground",
        "chat_miniAppButtonText", "chat_webAppButtonBackground", "chat_webAppButtonText",
        "chat_inFileThumbLink", "chat_outFileThumbLink", "chat_openWith", "files_openWith",
        "profile_addStory", "profile_storyAdd", "stories_add", "stories_addButton", "storyAdd",
        "chats_onlineCircle", "chats_nameMessage_threeLines", "chats_nameMessageArchived_threeLines",
        "chats_actionPressedBackground", "chats_verifiedCheck", "chats_archiveText",
        "key_telegram_color_text", "avatar_backgroundArchivedHidden", "avatar_backgroundInProfileBlue",
        "chats_sentReadCheck", "chats_menuPhone", "chats_menuPhoneCats", "chat_outSentClockSelected",
        "chat_messagePanelVoiceBackground", "chat_messagePanelVoicePressed", "chat_messagePanelVoiceDelete",
        "chat_messagePanelVoiceDuration", "chat_recordedVoiceBackground", "chat_outUpCall",
    })
    return sorted(keys)


def android_color_for_key(key: str, theme: dict) -> int:
    """Map Telegram Android theme slots to the current semantic palette.

    The bundled list includes the keys from Telegram's shipped arctic.attheme plus
    commonly used legacy/community slots. Every emitted key receives an explicit
    role or a conservative category fallback, so Android's stock green/blue values
    are not accidentally retained in those slots.
    """
    bg = theme["background"]
    accent = theme["accent"]
    fg = theme["text"]
    msg_fg = theme.get("message_text", fg)
    incoming = theme["incoming"]
    outgoing = theme["outgoing"]
    muted = theme.get("muted", mix(fg, bg, 0.28))
    on_accent = contrast_color(accent)
    key_l = key.lower()

    # Non-color metadata in .attheme files.
    if key_l == "wallpaperfileoffset":
        return -1
    if key_l in {"version", "name"}:
        return -1 if key_l == "version" else 0

    # Main text and secondary text in menus, folders, tabs and settings.
    primary_text = {
        "telegram_color_text", "key_telegram_color_text", "windowbackgroundwhiteblacktext",
        "dialogtextblack", "actionbardefaulttitle", "actionbardefaultsubmenuitem",
        "actionbardefaultarchivedtitle", "chats_name", "chats_secretname", "chats_menuname",
        "chats_menuitemtext", "profile_title", "profile_name", "chat_messagepaneltext",
        "chat_topPanelTitle".lower(), "chat_outcontactnametext", "chat_incontactnametext",
        "chat_outcontactphonetext", "chat_incontactphonetext", "chats_menuitemtext",
        "actionbarTabunactivetext".lower(),
    }
    muted_text = {
        "windowbackgroundwhitegraytext", "windowbackgroundwhitegraytext2",
        "windowbackgroundwhitegraytext3", "windowbackgroundwhitegraytext4",
        "windowbackgroundwhitegraytext5", "windowbackgroundwhitegraytext6",
        "windowbackgroundwhitegraytext7", "windowbackgroundwhitegraytext8", "graysectiontext",
        "windowbackgroundwhitehinttext", "dialogtextgray", "dialogtextgray2",
        "dialogtextgray3", "dialogtextgray4", "dialogtexthint", "actionbardefaultsubtitle",
        "actionbardefaultsearchplaceholder", "chats_date", "chat_status", "profile_status",
        "chat_recordtime", "chat_fieldoverlaytext", "chat_searchpaneltext",
        "chats_muteiconlabel", "chat_outviews", "player_time", "chat_outtimeselectedtext",
        "chat_intimeselectedtext", "chat_outaudiodurationtext", "chat_inaudiodurationtext",
        "chat_outfileinfotext", "chat_infileinfotext", "chat_outvenueinfotext",
        "chat_invenueinfotext", "chat_secretchatstatustext", "key_graysectiontext",
    }
    if key_l in primary_text:
        return signed_argb(fg)
    if key_l in muted_text:
        return signed_argb(muted)

    # Chat-list previews, drafts, secret-chat labels, action labels and tab badges.
    if key_l in {
        "chats_namemessage", "chats_namemessage_threelines", "chats_namemessagearchived",
        "chats_namemessagearchived_threelines", "chats_draft", "chats_attachmessage",
        "chats_actionmessage", "chats_sentcheck",
        "chats_sentclock", "chats_onlinecircle", "chats_secreticon", "chats_menuitemicon",
        "chats_muteicon", "chats_pinnedicon", "chats_menuphone", "chats_menuphonecats",
        "chats_verifiedbackground", "chats_sentreadcheck",
        "chats_senterroricon", "chat_botSwitchToInlineText".lower(),
        "chat_inlineresulticon", "chat_serviceLink".lower(), "chat_messageLinkIn".lower(),
        "chat_messageLinkOut".lower(), "chat_addcontact", "chat_searchpanelicons",
        "chat_replypanelicons", "chat_replypanelclose", "chat_replypanelline",
        "chat_replypanelname", "chat_inreplyline", "chat_outreplyline",
        "chat_inquote", "chat_outquote", "chat_inreplynametext", "chat_outreplynametext",
        "chat_inforwardednametext", "chat_outforwardednametext", "chat_inviabotnametext",
        "chat_outviabotnametext", "chat_insitenameText".lower(), "chat_outsitenameText".lower(),
        "profile_creatoricon", "profile_actionbackground",
        "profile_verifiedbackground", "calls_callreceivedgreenicon",
        "featuredstickers_addedicon", "featuredstickers_addbutton", "chat_muteicon", "chat_lockicon",
    }:
        return signed_argb(accent)

    # Message text, file names, contact cards and reply snippet bodies.
    if key_l in {
        "chat_messagetextout", "chat_messagetextin", "chat_messagetext",
        "chat_messagepaneltext", "chat_outreplymessagetext",
        "chat_inreplymessagetext", "chat_inreplymediamessagetext", "chat_outreplymediamessagetext",
        "chat_outreplymediamessageselectedtext", "chat_inreplymediamessageselectedtext",
        "chat_infilenameText".lower(), "chat_outfilenameText".lower(),
        "chat_incontactnametext", "chat_outcontactnametext", "chat_incontactphonetext",
        "chat_outcontactphonetext", "chat_outaudiotitletext", "chat_inaudiotitletext",
        "chat_outaudioperfomertext", "chat_inaudioperfomertext", "chat_outvenueNametext".lower(),
        "chat_invenueNametext".lower(), "chat_invenueinfoselectedtext", "chat_outvenueinfoselectedtext",
        "chat_outtimeText".lower(), "chat_intimeText".lower(), "chat_outfileNameText".lower(),
        "chat_infileNameText".lower(), "chat_outcontactphoneSelectedText".lower(),
        "chat_incontactphoneSelectedText".lower(),
    }:
        # Selected text over selected message surfaces should remain readable.
        if "selected" in key_l:
            return signed_argb(on_accent)
        return signed_argb(msg_fg)
    if key_l.startswith("chat_") and any(token in key_l for token in (
        "messagetext", "bubbletext", "messagebody", "filename", "replymessagetext",
    )):
        if "selected" in key_l:
            return signed_argb(on_accent)
        return signed_argb(msg_fg)

    # Foreground glyphs/text placed ON top of an accent-filled control need
    # contrast, not the accent itself (verified check, action button, folder tile).
    accent_foreground_keys = {
        "chats_verifiedcheck", "profile_verifiedcheck", "chats_actionicon", "profile_actionicon",
        "chats_unreadcountertext", "chats_actiontext", "files_foldericon", "files_icontext",
        "chat_messagepanelvoiceduration", "chat_botkeyboardbuttontext", "chat_godownbuttonicon",
        "chat_godownbuttoncounter", "chat_msgivbuttonprimaryintext", "chat_msgivbuttonprimaryouttext",
        "picker_badgetext", "featuredstickers_buttontext", "chat_recordedvoiceplaypause",
        "profile_actionicontext", "fastscrolltext",
        "chat_inlinebuttontext", "chat_miniappbuttontext", "chat_webappbuttontext",
    }
    if key_l in accent_foreground_keys:
        return signed_argb(on_accent)

    # Direct accent/selection/link/command/action tokens. Android keeps many
    # legacy interactive colours under names containing "Blue" or "Green".
    selection_tokens = ("selectedbackground", "textselection", "textselectbackground",
                        "linkselection", "linkselectbackground", "selectionhighlight",
                        "pressedbackground", "pressedselector")
    if any(token in key_l for token in selection_tokens):
        return signed_argb(accent, 42)
    if any(token in key_l for token in (
        "link", "url", "quote", "replyline", "replypanelname", "replypanelicons",
        "verified", "sentcheck", "sentclock", "onlinecircle", "_online", "secreticon",
        "actionicon", "actionbackground", "draft", "namemessage", "botswitchtoinline",
        "inlineresult", "seekbar", "waveform", "progress", "cursor", "addcontact",
        "featuredstickers_add", "command", "minapp", "webapp", "inlinebutton", "story",
        "openwith", "copy",
        "blueicon", "bluetext", "bluebutton", "blueheader", "textblue", "linkblue",
        "activeicon", "activebutton", "activecontrol", "activeprogress",
    )):
        return signed_argb(accent)

    # Bubbles and media cards retain their distinct incoming/outgoing base colours.
    if key_l in {"chat_inbubble", "chat_inbubbleshadow", "chat_infilebackground", "chat_incontactbackground"}:
        return signed_argb(incoming, theme.get("incoming_opacity", 100))
    if key_l in {"chat_outbubble", "chat_outbubbleshadow", "chat_outfilebackground", "chat_outcontactbackground"}:
        return signed_argb(outgoing, theme.get("outgoing_opacity", 100))
    if key_l in {"chat_inbubbleselected", "chat_outbubbleselected", "chat_infilebackgroundselected", "chat_outfilebackgroundselected", "chat_selectedbackground"}:
        return signed_argb(accent, 42)

    # App surfaces, panels, fields and chat folders.
    # Explicitly map the base window and input surfaces; falling through to the
    # generic text fallback makes some Android screens retain a white background.
    if key_l in {"graysection", "dialoginputfield", "windowbackgroundwhiteinputfield"}:
        return signed_argb(mix(bg, fg, 0.065))
    if key_l in {"windowbackgroundwhite", "dialogbackground", "actionbardefault",
        "actionbardefaultarchived", "chats_menubackground", "chat_messagepanelbackground",
        "chat_emojiPanelBackground".lower(), "chat_emojipanelbackground", "chat_emojipanelshadowline",
        "chat_servicebackground", "chat_wallpaper", "chat_toppanelbackground",
        "chats_menutopbackgroundcats", "chats_menutopbackground", "chat_topPanelBackground".lower(),
        "chat_recordedvoicebackground",
    }:
        return signed_argb(bg)
    if key_l == "windowbackgroundgray":
        return signed_argb(mix(bg, fg, 0.055))

    # Accent-filled controls and badges; text/icons placed on them use a contrasting foreground.
    if key_l in {
        "chats_tabunreadactivebackground", "chats_actionbackground", "profile_actionbackground",
        "profile_verifiedbackground", "chats_verifiedbackground", "chats_unreadcounter",
        "dialogbutton", "dialoginputfieldactivated", "dialogradioBackgroundChecked".lower(),
        "dialogroundcheckbox", "radioBackgroundChecked".lower(), "checkbox", "progresscircle",
        "fastscrollactive", "picker_badge", "picker_enabledbutton", "featuredStickers_addButton".lower(),
        "files_foldericonbackground", "chat_messagepanelsend", "chat_messagepanelvoicespressed",
        "chat_botkeyboardbuttonbackground", "chat_msgivbuttonprimaryin", "chat_msgivbuttonprimaryinpressed",
        "chat_msgivbuttonprimaryout", "chat_msgivbuttonprimaryoutpressed",
        "chat_inlinebuttonbackground", "chat_miniappbuttonbackground", "chat_webappbuttonbackground",
    }:
        return signed_argb(accent)
    if key_l in {
        "chats_unreadcountertext", "chats_verifiedcheck", "profile_verifiedcheck",
        "chats_actionicon", "profile_actionicon", "files_foldericon", "files_icontext", "chat_messagepanelvoiceduration",
        "chat_botkeyboardbuttontext", "chat_goDownButtonIcon".lower(), "chat_godownbuttonicon",
        "chat_godownbuttoncounter", "chat_msgivbuttonprimaryintext", "chat_msgivbuttonprimaryouttext",
        "picker_badgetext", "featuredstickers_buttontext", "chat_recordedvoiceplaypause",
        "profile_actionicontext", "fastscrolltext",
        "chat_inlinebuttontext", "chat_miniappbuttontext", "chat_webappbuttontext",
    }:
        return signed_argb(on_accent)

    # Unread badges and inactive tabs use muted versions of accent.
    if key_l in {"chats_tabunreadunactivebackground", "chats_archivepinbackground", "chats_unreadcountermuted"}:
        return signed_argb(mix(accent, bg, 0.35))
    if key_l in {"chats_archivebackground", "chats_menucloudbackgroundcats"}:
        return signed_argb(accent)
    if key_l in {"chats_archivetext", "chats_menuname"}:
        return signed_argb(on_accent if "archive" in key_l else fg)

    # Main tab labels: inactive tabs are main text; selected tabs are the accent.
    if key_l == "actionbartabactivetext":
        return signed_argb(accent)
    if key_l == "actionbartabunactivetext":
        return signed_argb(fg)

    # Avatar placeholders and initials all share the chosen accent, avoiding Telegram's
    # built-in rotating blue/green/pink/orange colours.
    if "avatar_background" in key_l or key_l.startswith("avatar_background") or "userpicbg" in key_l:
        return signed_argb(accent)
    if "avatar_nameinmessage" in key_l or key_l in {"avatar_text", "historypeeruserpicfg"}:
        return signed_argb(on_accent)

    # Common icon and media slots, including inherited green/blue variants.
    if key_l in {"chat_messagepanelvoicebackground", "chat_messagepanelvoicepressed", "chat_messagepanelvoicedelete", "chat_msgivbuttonprimaryin", "chat_msgivbuttonprimaryinpressed", "chat_msgivbuttonprimaryout", "chat_msgivbuttonprimaryoutpressed"}:
        return signed_argb(accent)
    if any(token in key_l for token in (
        "icon", "check", "tick", "clock", "voice", "audio", "fileprogress", "fileicon", "loader",
        "player_progress", "inappplayer", "send", "callreceived", "callarrow", "attach",
        "profile_action", "foldericon", "contextprogressinner", "dialoglineprogress",
        "chat_inloader", "chat_outloader", "chat_inmediаicon".lower(),
    )):
        if any(token in key_l for token in ("verifiedcheck", "foldericon", "icontext", "buttontext", "duration")):
            return signed_argb(on_accent)
        if "time" in key_l or "duration" in key_l:
            return signed_argb(muted)
        return signed_argb(accent)

    # Explicit green color families in Android's bundled resources are remapped, not preserved.
    if ("green" in key_l or "blue" in key_l or key_l.startswith("color_")
            or key_l.startswith("statisticchartline_")):
        return signed_argb(accent)

    # Other named backgrounds/selection states.
    if any(token in key_l for token in ("background", "_bg", "wallpaper", "shadow", "selector")):
        if "selected" in key_l or "pressed" in key_l or "selector" in key_l:
            return signed_argb(accent, 35)
        if "bubble" in key_l:
            return signed_argb(incoming if "in" in key_l else outgoing)
        return signed_argb(bg)

    # Semantic text fallback: chat text uses the message text control; labels use main text.
    if any(token in key_l for token in ("gray", "hint", "subtitle", "duration", "time", "date", "status", "info")):
        if "selected" in key_l:
            return signed_argb(on_accent)
        return signed_argb(muted)
    if any(token in key_l for token in ("text", "title", "name", "performer", "author")):
        if any(token in key_l for token in ("link", "quote", "replyname", "draft", "actionmessage", "namemessage")):
            return signed_argb(accent)
        if key_l.startswith("chat_"):
            return signed_argb(msg_fg)
        return signed_argb(fg)
    if key_l.endswith("button") or key_l.endswith("buttonbackground"):
        return signed_argb(accent)
    return signed_argb(fg)

def create_android_theme(theme: dict, wallpaper_path: Path | None) -> bytes:
    """Create a broad Android .attheme mapping covering Telegram's shipped theme slots."""
    ensure_text_colors(theme)
    keys = load_android_theme_keys()
    body_lines = [f"{key}={android_color_for_key(key, theme)}" for key in keys]
    body = ("\n".join(body_lines) + "\n").encode("utf-8")
    if wallpaper_path and wallpaper_path.exists():
        # Android .attheme stores the image after WPS; WPE is an optional end marker.
        body += b"WPS\n" + wallpaper_path.read_bytes() + b"\nWPE\n"
    return body


def ios_hex(color: str, alpha: int = 100) -> str:
    """Return a YAML-quoted RGB/ARGB hex string (quotes prevent numeric coercion)."""
    a = max(0, min(100, alpha)) * 255 // 100
    value = f"{a:02X}{color.lstrip('#').upper()}" if alpha < 100 else color.lstrip("#").upper()
    return json.dumps(value)


def create_ios_theme(theme: dict) -> bytes:
    """Create an iOS .tgios-theme YAML theme using Telegram's documented nested color schema."""
    ensure_text_colors(theme)
    bg, accent, fg = theme["background"], theme["accent"], theme["text"]
    in_bubble = ios_hex(theme["incoming"], theme.get("incoming_opacity", 100))
    out_bubble = ios_hex(theme["outgoing"], theme.get("outgoing_opacity", 100))
    muted = ios_hex(theme.get("muted") or mix(fg, bg, 0.28))
    dark = luminance(bg) < 0.179
    status = "white" if dark else "black"
    base = "night" if dark else "day"
    tint = ios_hex(accent)
    text = ios_hex(fg)
    message_text = ios_hex(theme.get("message_text", fg))
    accent_select = ios_hex(accent, 35)
    lines = [
        f"name: {json.dumps(theme.get('name', 'Theme Maker'), ensure_ascii=False)}",
        f"basedOn: {base}", f"dark: {'true' if dark else 'false'}",
        "intro:", f"  statusBar: {status}", f"  primaryText: {text}", f"  accentText: {tint}",
        f"  disabledText: {muted}", f"  startButton: {tint}", f"  dot: {tint}",
        "passcode:", "  bg:", f"    top: {ios_hex(bg)}", f"    bottom: {ios_hex(bg)}", f"  button: {tint}",
        "root:", f"  statusBar: {status}", "  tabBar:", f"    background: {ios_hex(bg)}",
        f"    separator: {ios_hex(fg, 20)}", f"    icon: {muted}", f"    selectedIcon: {tint}",
        f"    text: {muted}", f"    selectedText: {tint}", f"    badgeBackground: {tint}",
        f"    badgeStroke: {tint}", f"    badgeText: {ios_hex(contrast_color(accent))}",
        "  navBar:", f"    button: {tint}", f"    disabledButton: {muted}", f"    primaryText: {text}",
        f"    secondaryText: {muted}", f"    control: {tint}", f"    accentText: {tint}",
        f"    background: {ios_hex(bg)}", f"    opaqueBackground: {ios_hex(bg)}",
        f"    separator: {ios_hex(fg, 20)}", f"    badgeFill: {tint}", f"    badgeStroke: {tint}",
        f"    badgeText: {ios_hex(contrast_color(accent))}", f"    segmentedBg: {ios_hex(accent, 15)}",
        f"    segmentedFg: {text}", f"    segmentedText: {tint}", f"    segmentedDivider: {ios_hex(fg, 20)}",
        "  searchBar:", f"    background: {ios_hex(bg)}", f"    accent: {tint}",
        f"    inputFill: {ios_hex(fg, 10)}", f"    inputText: {text}", f"    inputPlaceholderText: {muted}",
        f"    inputIcon: {tint}", f"    inputClearButton: {tint}", f"    separator: {ios_hex(fg, 20)}",
        f"  keyboard: {'dark' if dark else 'light'}",
        "list:", f"  blocksBg: {ios_hex(mix(bg, fg, 0.04))}", f"  plainBg: {ios_hex(bg)}",
        f"  primaryText: {text}", f"  secondaryText: {muted}", f"  disabledText: {muted}",
        f"  accent: {tint}", f"  highlighted: {accent_select}", f"  destructive: {tint}",
        f"  placeholderText: {muted}", f"  itemBlocksBg: {ios_hex(bg)}",
        f"  itemHighlightedBg: {ios_hex(accent, 20)}", f"  blocksSeparator: {ios_hex(fg, 20)}",
        f"  plainSeparator: {ios_hex(fg, 20)}", f"  disclosureArrow: {tint}",
        f"  sectionHeaderText: {muted}", f"  freeText: {text}", f"  freeTextError: {tint}",
        f"  freeTextSuccess: {tint}", f"  freeMonoIcon: {tint}", "  switch:",
        f"    frame: {ios_hex(fg, 18)}", f"    handle: {text}", f"    content: {tint}",
        f"    positive: {tint}", f"    negative: {tint}", "  check:",
        f"    bg: {tint}", f"    stroke: {tint}", f"    fg: {ios_hex(contrast_color(accent))}",
        f"  controlSecondary: {ios_hex(fg, 22)}", "  freeInputField:",
        f"    bg: {ios_hex(fg, 10)}", f"    stroke: {ios_hex(accent, 45)}", f"    placeholder: {muted}",
        f"    primary: {text}", f"    control: {tint}", f"  mediaPlaceholder: {ios_hex(fg, 10)}",
        f"  scrollIndicator: {ios_hex(accent, 35)}", f"  pageIndicatorInactive: {ios_hex(fg, 22)}",
        f"  inputClearButton: {tint}", "chatList:", f"  bg: {ios_hex(bg)}",
        f"  itemSeparator: {ios_hex(fg, 18)}", f"  itemBg: {ios_hex(bg)}",
        f"  pinnedItemBg: {ios_hex(mix(bg, fg, 0.04))}", f"  itemHighlightedBg: {ios_hex(accent, 18)}",
        f"  pinnedItemHighlightedBg: {ios_hex(accent, 18)}", f"  itemSelectedBg: {ios_hex(accent, 24)}",
        f"  title: {text}", f"  secretTitle: {tint}", f"  dateText: {muted}",
        f"  authorName: {text}", f"  messageText: {message_text}", f"  messageHighlightedText: {tint}",
        f"  messageDraftText: {tint}", f"  checkmark: {tint}", f"  pendingIndicator: {tint}",
        f"  failedFill: {tint}", f"  failedFg: {ios_hex(contrast_color(accent))}", f"  muteIcon: {muted}",
        f"  unreadBadgeActiveBg: {tint}", f"  unreadBadgeActiveText: {ios_hex(contrast_color(accent))}",
        f"  unreadBadgeInactiveBg: {ios_hex(accent, 45)}", f"  unreadBadgeInactiveText: {text}",
        f"  pinnedBadge: {tint}", f"  sectionHeaderBg: {ios_hex(bg)}", f"  sectionHeaderText: {muted}",
        f"  verifiedIconBg: {tint}", f"  verifiedIconFg: {ios_hex(contrast_color(accent))}",
        f"  secretIcon: {tint}", "  pinnedArchiveAvatar:", "    background:",
        f"      top: {tint}", f"      bottom: {ios_hex(mix(accent, fg, 0.25))}",
        f"    foreground: {ios_hex(contrast_color(accent))}", "  unpinnedArchiveAvatar:",
        "    background:", f"      top: {tint}", f"      bottom: {ios_hex(mix(accent, bg, 0.25))}",
        f"    foreground: {ios_hex(contrast_color(accent))}", f"  onlineDot: {tint}",
        "  storyUnseen:", f"    top: {tint}", f"    bottom: {tint}",
        "  storyUnseenPrivate:", f"    top: {tint}", f"    bottom: {tint}",
        "  storySeen:", f"    top: {ios_hex(fg, 35)}", f"    bottom: {ios_hex(fg, 35)}",
        "chat:", f"  defaultWallpaper: {ios_hex(bg)}", "  animateMessageColors: false", "  message:",
        "    incoming:", "      bubble:", "        withWp:", f"          bg: {in_bubble}",
        f"          gradientBg: {in_bubble}", f"          highlightedBg: {accent_select}", f"          stroke: {in_bubble}",
        f"          reactionInactiveBg: {ios_hex(accent, 18)}", f"          reactionInactiveFg: {tint}",
        f"          reactionActiveBg: {tint}", f"          reactionActiveFg: {ios_hex(contrast_color(accent))}",
        "        withoutWp:", f"          bg: {in_bubble}", f"          gradientBg: {in_bubble}",
        f"          highlightedBg: {accent_select}", f"          stroke: {in_bubble}",
        f"          reactionInactiveBg: {ios_hex(accent, 18)}", f"          reactionInactiveFg: {tint}",
        f"          reactionActiveBg: {tint}", f"          reactionActiveFg: {ios_hex(contrast_color(accent))}",
        f"      primaryText: {message_text}", f"      secondaryText: {muted}", f"      linkText: {tint}",
        f"      linkHighlight: {accent_select}", f"      scam: {tint}", f"      textHighlight: {accent_select}",
        f"      accentText: {tint}", f"      accentControl: {tint}", f"      mediaActiveControl: {tint}",
        f"      mediaInactiveControl: {muted}", f"      mediaControlInnerBg: {ios_hex(bg)}",
        f"      pendingActivity: {muted}", f"      fileTitle: {text}", f"      fileDescription: {muted}",
        f"      fileDuration: {muted}", f"      mediaPlaceholder: {ios_hex(fg, 10)}", f"      textSelection: {accent_select}",
        f"      textSelectionKnob: {tint}",
        "    outgoing:", "      bubble:", "        withWp:", f"          bg: {out_bubble}",
        f"          gradientBg: {out_bubble}", f"          highlightedBg: {accent_select}", f"          stroke: {out_bubble}",
        f"          reactionInactiveBg: {ios_hex(accent, 18)}", f"          reactionInactiveFg: {tint}",
        f"          reactionActiveBg: {tint}", f"          reactionActiveFg: {ios_hex(contrast_color(accent))}",
        "        withoutWp:", f"          bg: {out_bubble}", f"          gradientBg: {out_bubble}",
        f"          highlightedBg: {accent_select}", f"          stroke: {out_bubble}",
        f"          reactionInactiveBg: {ios_hex(accent, 18)}", f"          reactionInactiveFg: {tint}",
        f"          reactionActiveBg: {tint}", f"          reactionActiveFg: {ios_hex(contrast_color(accent))}",
        f"      primaryText: {message_text}", f"      secondaryText: {muted}", f"      linkText: {tint}",
        f"      linkHighlight: {accent_select}", f"      scam: {tint}", f"      textHighlight: {accent_select}",
        f"      accentText: {tint}", f"      accentControl: {tint}", f"      mediaActiveControl: {tint}",
        f"      mediaInactiveControl: {muted}", f"      mediaControlInnerBg: {ios_hex(bg)}",
        f"      pendingActivity: {muted}", f"      fileTitle: {text}", f"      fileDescription: {muted}",
        f"      fileDuration: {muted}", f"      mediaPlaceholder: {ios_hex(fg, 10)}", f"      textSelection: {accent_select}",
        f"      textSelectionKnob: {tint}", f"    infoPrimaryText: {text}", f"    infoLinkText: {tint}",
        f"    outgoingCheck: {tint}", f"    mediaDateAndStatusBg: {ios_hex(bg, 78)}",
        f"    mediaDateAndStatusText: {text}", "  inputPanel:", f"    panelBg: {ios_hex(bg)}",
        f"    panelSeparator: {ios_hex(fg, 20)}", f"    panelControlAccent: {tint}",
        f"    panelControl_v2: {tint}", f"    panelControlDisabled: {muted}",
        f"    panelControlDestructive: {tint}", f"    inputBg: {ios_hex(fg, 10)}",
        f"    inputStroke: {ios_hex(accent, 30)}", f"    inputPlaceholder_v2: {muted}",
        f"    inputText_v2: {text}", f"    inputControl_v2: {tint}",
        f"    actionControlBg: {tint}", f"    actionControlFg: {ios_hex(contrast_color(accent))}",
        f"    primaryText: {text}", f"    secondaryText: {muted}", f"    mediaRecordDot: {tint}",
        "    mediaRecordControl:", f"      button: {tint}", f"      micLevel: {accent_select}",
        f"      activeIcon: {ios_hex(contrast_color(accent))}",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def create_macos_palette(theme: dict) -> bytes:
    """Create a native Telegram for macOS .palette key/value text file."""
    ensure_text_colors(theme)
    bg = theme["background"]
    accent = theme["accent"]
    fg = theme["text"]
    muted = theme.get("muted", mix(fg, bg, 0.28))
    msg_fg = theme.get("message_text", fg)
    incoming = theme["incoming"]
    outgoing = theme["outgoing"]
    dark = luminance(bg) < 0.179

    # Remove line breaks so a user-supplied theme name cannot add fake palette entries.
    name = str(theme.get("name", "Theme Maker")).replace(chr(13), " ").replace(chr(10), " ").strip()[:48]
    name = name or "Theme Maker"
    shortname = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-_") or "theme-maker"
    soft_bg = mix(bg, fg, 0.055)
    border = mix(bg, fg, 0.16)
    selected = mix(bg, accent, 0.36)

    values = {
        "basicAccent": accent,
        "background": bg,
        "text": fg,
        "grayText": muted,
        "link": accent,
        "accent": accent,
        "redUI": "#E35D6A",
        "greenUI": "#42A878",
        "blackTransparent": "#000000: 42",
        "grayTransparent": f"{fg}: 18",
        "grayUI": muted,
        "darkGrayText": muted,
        "accentSelect": selected,
        "selectText": contrast_color(selected),
        "border": border,
        "grayBackground": soft_bg,
        "grayForeground": muted,
        "grayIcon": muted,
        "accentIcon": accent,
        "badgeMuted": mix(accent, bg, 0.38),
        "badge": accent,
        "indicatorColor": accent,
        "selectMessage": selected,
        "monospacedPre": accent,
        "monospacedCode": accent,
        "monospacedPreBubble_incoming": msg_fg,
        "monospacedPreBubble_outgoing": msg_fg,
        "monospacedCodeBubble_incoming": accent,
        "monospacedCodeBubble_outgoing": accent,
        "selectTextBubble_incoming": contrast_color(accent),
        "selectTextBubble_outgoing": contrast_color(accent),
        "bubbleBackground_incoming": incoming,
        "bubbleBackground_outgoing": outgoing,
        "bubbleBorder_incoming": border,
        "bubbleBorder_outgoing": outgoing,
        "bubbleBackgroundHighlight_incoming": selected,
        "bubbleBackgroundHighlight_outgoing": selected,
        "textBubble_incoming": msg_fg,
        "textBubble_outgoing": msg_fg,
        "grayTextBubble_incoming": muted,
        "grayTextBubble_outgoing": muted,
        "grayIconBubble_incoming": muted,
        "grayIconBubble_outgoing": muted,
        "blueIconBubble_incoming": accent,
        "blueIconBubble_outgoing": accent,
        "accentIconBubble_incoming": accent,
        "accentIconBubble_outgoing": accent,
        "linkBubble_incoming": accent,
        "linkBubble_outgoing": accent,
        "selectMessageBubble": selected,
        "chatReplyTitle": accent,
        "chatReplyTextEnabled": fg,
        "chatReplyTextDisabled": muted,
        "chatReplyTitleBubble_incoming": accent,
        "chatReplyTitleBubble_outgoing": accent,
        "chatReplyTextEnabledBubble_incoming": msg_fg,
        "chatReplyTextEnabledBubble_outgoing": msg_fg,
        "chatReplyTextDisabledBubble_incoming": muted,
        "chatReplyTextDisabledBubble_outgoing": muted,
        "fileActivityBackground": accent,
        "fileActivityForeground": contrast_color(accent),
        "fileActivityBackgroundBubble_incoming": accent,
        "fileActivityBackgroundBubble_outgoing": accent,
        "fileActivityForegroundBubble_incoming": contrast_color(accent),
        "fileActivityForegroundBubble_outgoing": contrast_color(accent),
        "waveformBackground": f"{accent}: 35",
        "waveformForeground": accent,
        "waveformBackgroundBubble_incoming": f"{accent}: 35",
        "waveformBackgroundBubble_outgoing": f"{accent}: 35",
        "waveformForegroundBubble_incoming": accent,
        "waveformForegroundBubble_outgoing": accent,
        "chatDateActive": soft_bg,
        "chatDateText": muted,
        "peerAvatarRedTop": mix(accent, "#FFAC8E", 0.35),
        "peerAvatarRedBottom": mix(accent, "#FF8597", 0.35),
        "peerAvatarOrangeTop": mix(accent, "#FFDC97", 0.35),
        "peerAvatarOrangeBottom": mix(accent, "#FFC28D", 0.35),
        "peerAvatarVioletTop": mix(accent, "#A8C8FF", 0.35),
        "peerAvatarVioletBottom": mix(accent, "#948FFF", 0.35),
        "peerAvatarGreenTop": mix(accent, "#CDFFB2", 0.35),
        "peerAvatarGreenBottom": mix(accent, "#90F4A0", 0.35),
        "peerAvatarCyanTop": mix(accent, "#8BFFEE", 0.35),
        "peerAvatarCyanBottom": mix(accent, "#6AF1E2", 0.35),
        "peerAvatarBlueTop": mix(accent, "#9DE3FF", 0.35),
        "peerAvatarBlueBottom": mix(accent, "#6CC2FF", 0.35),
        "peerAvatarPinkTop": mix(accent, "#F1C4FF", 0.35),
        "peerAvatarPinkBottom": mix(accent, "#EE9CFF", 0.35),
        "revealAction_neutral1_background": muted,
        "revealAction_neutral1_foreground": contrast_color(muted),
        "revealAction_neutral2_background": "#CD7800",
        "revealAction_neutral2_foreground": "#FFFFFF",
        "revealAction_destructive_background": "#C70C0C",
        "revealAction_destructive_foreground": "#FFFFFF",
        "revealAction_constructive_background": "#08A723",
        "revealAction_constructive_foreground": "#FFFFFF",
        "revealAction_accent_background": accent,
        "revealAction_accent_foreground": contrast_color(accent),
        "revealAction_warning_background": "#CD7800",
        "revealAction_warning_foreground": "#FFFFFF",
        "revealAction_inactive_background": muted,
        "revealAction_inactive_foreground": contrast_color(muted),
        "chatBackground": bg,
        "listBackground": bg,
        "listGrayText": muted,
        "grayHighlight": soft_bg,
        "wallpaper": bg,
    }
    lines = [
        f"name = {json.dumps(name, ensure_ascii=False)}",
        f"shortname = {shortname}",
        f"isDark = {1 if dark else 0}",
        "tinted = 0",
        f"parent = {'Dark' if dark else 'Day'}",
        "",
    ]
    lines.extend(f"{key} = {value}" for key, value in values.items())
    return (chr(10).join(lines) + chr(10)).encode("utf-8")


def create_tgx_theme(theme: dict) -> bytes:
    """Create a Telegram X .tgx-theme key/value theme, based on documented sample syntax."""
    ensure_text_colors(theme)
    bg, accent, fg = theme["background"], theme["accent"], theme["text"]
    message_fg = theme.get("message_text", fg)
    incoming = alpha_hex(theme["incoming"], theme.get("incoming_opacity", 100))
    outgoing = alpha_hex(theme["outgoing"], theme.get("outgoing_opacity", 100))
    values = [
        "!", f"name: {json.dumps(theme.get('name', 'Theme Maker'), ensure_ascii=False)}",
        f"time: {int(time.time())}", 'author: "Theme Maker"', "@", "bubbleCorner: 19",
        "bubbleOutline: 1", "parentTheme, wallpaperUsageId: 2", "#",
        f"background, chatSeparator, fileAttach: {bg}",
        f"badge, bubbleOut_progress, chatListAction, chatSendButton, online, seekDone, ticks, ticksRead: {accent}",
        f"bubble_chatBackground, chatBackground: {bg}",
        f"bubble_mediaReply_noWallpaper, bubbleOut_background: {outgoing}",
        f"bubbleIn_background, bubbleIn_mediaReply: {incoming}",
        f"bubbleIn_textLink, bubbleOut_file, bubbleOut_textLink, file, fileGreen, fileRed, fileYellow, headerButton, iv_textLink, textLink, togglerActiveBackground: {accent}",
        f"bubbleIn_textLinkPressHighlight, textLinkPressHighlight: {alpha_hex(accent, 40)}",
        f"bubbleOut_chatVerticalLine, messageVerticalLine: {fg}",
        f"bubbleOut_inlineText, bubbleIn_inlineText: {message_fg}",
        f"bubbleOut_ticks, bubbleOut_ticksRead, fillingPositive: {accent}",
        f"bubbleOut_waveformActive, waveformActive: {accent}",
        f"bubbleOut_waveformInactive, waveformInactive: {alpha_hex(accent, 35)}",
        f"circleButtonChatIcon, playerButtonActive, textNeutral: {fg}",
        f"drawer: {alpha_hex(bg, 90)}", f"filling, fillingPressed: {mix(bg, fg, 0.06)}",
        f"iconActive, iv_pageTitle, iv_textLinkPressHighlight, messageAuthor: {accent}",
        f"iconLight, ivHeaderIcon: {fg}", f"messageSelection, bubble_messageSelection, bubble_messageSelectionNoWallpaper: {alpha_hex(accent, 40)}",
        f"playerCoverPlaceholder, headerBackground, ivHeader: {bg}",
        f"previewBackground: {alpha_hex(bg, 55)}", f"promo: {accent}",
        f"spoilerMediaOverlay: {alpha_hex(accent, 35)}", f"textSearchQueryHighlight, textSelectionHighlight: {accent}",
        f"togglerActive, togglerInactive: {fg}", f"togglerInactiveBackground: {mix(bg, fg, 0.25)}",
        f"togglerPositive, togglerPositiveBackground: {accent}",
    ]
    return ("\n".join(values) + "\n").encode("utf-8")


class PublicOnlyResolver(aiohttp.abc.AbstractResolver):
    """Resolve hostnames only to public IP addresses, including at connect time."""

    def __init__(self):
        self._delegate = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        records = await self._delegate.resolve(host, port, family)
        addresses = [record["host"] for record in records]
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise OSError("Адрес сайта не является общедоступным.")
        return records

    async def close(self):
        await self._delegate.close()


async def update_photo_progress(progress_message: Message, language: str, percent: int, stage_key: str):
    percent = max(0, min(100, int(percent)))
    progress_text = tr(
        language,
        "photo_progress",
        percent=percent,
        stage=tr(language, stage_key),
    )
    try:
        await progress_message.edit_text(progress_text, parse_mode=ParseMode.HTML)
    except Exception as exc:
        # Progress is informational; a Telegram edit error must not stop image processing.
        print(f"Не удалось обновить сообщение прогресса: {exc}")


async def download_with_progress(progress_message: Message, language: str, downloader):
    """Run an async downloader while reflecting byte-based progress in Telegram."""
    queue: asyncio.Queue[int] = asyncio.Queue()

    def report(percent: int):
        queue.put_nowait(max(0, min(100, int(percent))))

    await update_photo_progress(progress_message, language, 3, "photo_stage_downloading")
    task = asyncio.create_task(downloader(report))
    displayed_percent = 3
    while not task.done():
        try:
            downloaded_percent = await asyncio.wait_for(queue.get(), timeout=0.4)
        except asyncio.TimeoutError:
            continue
        # Reserve the first 30% for actual download progress.
        current_percent = 5 + downloaded_percent * 22 // 100
        if current_percent > displayed_percent:
            displayed_percent = current_percent
            await update_photo_progress(
                progress_message, language, displayed_percent, "photo_stage_downloading"
            )

    result = await task
    await update_photo_progress(progress_message, language, 30, "photo_stage_analyzing")
    return result


async def prepare_photo_assets_with_progress(
    user_id: int,
    raw: bytes,
    progress_message: Message,
    language: str,
) -> tuple[list[str], Path]:
    """Run Pillow work off the event loop and relay actual processing stages."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

    def report(percent: int, stage_key: str):
        loop.call_soon_threadsafe(queue.put_nowait, (percent, stage_key))

    task = asyncio.create_task(
        asyncio.to_thread(
            prepare_photo_assets,
            user_id,
            raw,
            progress_callback=report,
        )
    )
    while not task.done():
        try:
            percent, stage_key = await asyncio.wait_for(queue.get(), timeout=0.4)
        except asyncio.TimeoutError:
            continue
        await update_photo_progress(progress_message, language, percent, stage_key)

    return await task


async def safe_download_image(url: str, progress_callback=None) -> bytes:
    """Download a public image URL, validating redirects and the actual connection IP."""
    current_url = url.strip()
    timeout = aiohttp.ClientTimeout(total=25, connect=8)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ThemeMaker/3.6)"}
    connector = aiohttp.TCPConnector(resolver=PublicOnlyResolver())
    async with aiohttp.ClientSession(timeout=timeout, trust_env=False, connector=connector) as session:
        for _ in range(5):
            parsed = urlparse(current_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("Нужна публичная ссылка на изображение (http/https).")
            if parsed.username or parsed.password:
                raise ValueError("Ссылки с логином и паролем не поддерживаются.")
            host = parsed.hostname.lower()
            if host in {"localhost", "localhost.localdomain"}:
                raise ValueError("Локальные адреса не поддерживаются.")
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(
                    host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM
                )
                addresses = {item[4][0] for item in infos}
                if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                    raise ValueError("Ссылка должна вести на общедоступный сайт.")
            except socket.gaierror as exc:
                raise ValueError("Не удалось найти сайт по этой ссылке.") from exc
            async with session.get(current_url, allow_redirects=False, headers=headers) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Сайт перенаправил запрос без адреса картинки.")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status != 200:
                    raise ValueError(f"Сайт вернул HTTP {response.status}. Скачай картинку и отправь её боту файлом.")
                content_type = response.headers.get("Content-Type", "").lower()
                if not content_type.startswith("image/"):
                    raise ValueError("Это не прямая ссылка на файл картинки. Скачай изображение и отправь его файлом.")
                length = int(response.headers.get("Content-Length", "0") or 0)
                if length > MAX_IMAGE_BYTES:
                    raise ValueError("Изображение больше 12 МБ.")
                data = bytearray()
                last_reported_step = 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("Изображение больше 12 МБ.")
                    if progress_callback and length > 0:
                        percent = min(100, int(len(data) * 100 / length))
                        step = percent // 20
                        if step > last_reported_step or percent == 100:
                            last_reported_step = step
                            progress_callback(percent)
                return bytes(data)
    raise ValueError("Слишком много перенаправлений. Скачай изображение и отправь его файлом.")


async def download_telegram_image(message: Message, bot: Bot, progress_callback=None) -> bytes:
    if message.photo:
        file_obj = await bot.get_file(message.photo[-1].file_id)
    elif message.document:
        doc = message.document
        if not doc.mime_type or not doc.mime_type.startswith("image/"):
            raise ValueError("Это не изображение. Отправь JPG, PNG или WebP.")
        if doc.file_size and doc.file_size > MAX_IMAGE_BYTES:
            raise ValueError("Изображение больше 12 МБ.")
        file_obj = await bot.get_file(doc.file_id)
    else:
        raise ValueError("Отправь картинку как фото или как файл.")

    if file_obj.file_size and file_obj.file_size > MAX_IMAGE_BYTES:
        raise ValueError("Изображение больше 12 МБ.")
    buffer = ProgressBytesIO(file_obj.file_size, progress_callback)
    await bot.download_file(file_obj.file_path, destination=buffer)
    return buffer.getvalue()


async def show_theme(
    message: Message,
    theme: dict,
    wallpaper_path: str | None = None,
    prefix: str = "",
    image_palette: list[str] | None = None,
    language: str | None = None,
    progress_message: Message | None = None,
):
    ensure_text_colors(theme)
    language = language or user_language(message.from_user.id)
    if progress_message:
        await update_photo_progress(progress_message, language, 87, "photo_stage_preview")
    preview = await asyncio.to_thread(render_preview, theme, wallpaper_path, image_palette)
    title = html.escape(str(theme.get("name", tr(language, "default_theme_name"))))
    image_note = tr(language, "theme_wallpaper") if wallpaper_path else tr(language, "theme_solid")
    palette_note = ""
    if image_palette:
        palette_codes = " · ".join(f"<code>{html.escape(color)}</code>" for color in image_palette)
        palette_note = (
            f"\n\n<b>{tr(language, 'palette_note_title')}</b> {palette_codes}\n"
            f"{tr(language, 'palette_note')}"
        )
    caption = (
        f"<b>{title}</b>\n\n"
        f"{html.escape(prefix)}{image_note}{palette_note}\n\n"
        f"<b>{tr(language, 'theme_legend_title')}</b>\n"
        f"{tr(language, 'legend_background')}\n"
        f"{tr(language, 'legend_accent')}\n"
        f"{tr(language, 'legend_outgoing')}\n"
        f"{tr(language, 'legend_incoming')}\n"
        f"{tr(language, 'legend_opacity')}\n\n"
        f"{tr(language, 'theme_auto_text')}"
    )
    await message.answer_photo(
        BufferedInputFile(preview, filename="theme-preview.jpg"),
        caption=caption,
        reply_markup=theme_keyboard(language, bool(image_palette)),
        parse_mode=ParseMode.HTML,
    )
    if progress_message:
        await update_photo_progress(progress_message, language, 100, "photo_stage_done")


def welcome_cover_path() -> Path:
    """Prefer the user's local cover and fall back to the bundled default."""
    return COVER_PATH if COVER_PATH.is_file() else DEFAULT_COVER_PATH


async def send_language_prompt(message: Message):
    await message.answer(
        "<b>Добро пожаловать в Theme Maker!</b>\n\n"
        "Сначала выбери язык интерфейса / First, choose your interface language:",
        reply_markup=language_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def send_welcome(message: Message, language: str | None = None):
    language = language or user_language(message.from_user.id)
    welcome_text = tr(language, "welcome")
    cover_path = welcome_cover_path()
    if cover_path.is_file():
        await message.answer_photo(
            BufferedInputFile(cover_path.read_bytes(), filename="theme-maker-welcome.png"),
            caption=welcome_text, reply_markup=main_menu(language), parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(welcome_text, reply_markup=main_menu(language), parse_mode=ParseMode.HTML)


async def set_user_commands(bot: Bot):
    for language in ("ru", "en"):
        command_texts = tr(language, "commands")
        commands = [
            BotCommand(command="start", description=command_texts["start"]),
            BotCommand(command="create", description=command_texts["create"]),
            BotCommand(command="fromphoto", description=command_texts["fromphoto"]),
            BotCommand(command="catalog", description=command_texts["catalog"]),
            BotCommand(command="help", description=command_texts["help"]),
            BotCommand(command="cancel", description=command_texts["cancel"]),
            BotCommand(command="version", description=command_texts["version"]),
        ]
        if language == "ru":
            await bot.set_my_commands(commands)
            await bot.set_my_description(tr(language, "bot_description"))
            await bot.set_my_short_description(tr(language, "bot_short_description"))
        else:
            await bot.set_my_commands(commands, language_code="en")
            await bot.set_my_description(tr(language, "bot_description"), language_code="en")
            await bot.set_my_short_description(tr(language, "bot_short_description"), language_code="en")


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    language = user_language(message.from_user.id)
    await state.update_data(theme=default_theme(language), wallpaper_path=None)
    await send_language_prompt(message)


@dp.callback_query(F.data == "language")
async def language_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    await callback.message.answer(
        tr(language, "choose_language"),
        reply_markup=language_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("lang:"))
async def select_language(callback: CallbackQuery, state: FSMContext):
    language = callback.data.split(":", 1)[1]
    if language not in ("ru", "en"):
        await callback.answer("Unknown language", show_alert=True)
        return
    LANGUAGE_PREFERENCES.set_language(callback.from_user.id, language)
    data = await state.get_data()
    theme = data.get("theme")
    if theme is None:
        theme = default_theme(language)
    elif theme.get("name") in ("Моя тема", "My theme"):
        theme["name"] = tr(language, "default_theme_name")
    await state.update_data(theme=theme)
    await callback.message.edit_text(
        tr(language, "language_selected"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
    )
    await send_welcome(callback.message, language)
    await callback.answer(tr(language, "language_saved"))


@dp.message(Command("create"))
async def create_command(message: Message, state: FSMContext):
    await state.clear()
    language = user_language(message.from_user.id)
    theme = default_theme(language)
    await state.update_data(theme=theme, wallpaper_path=None)
    await show_theme(message, theme, prefix=tr(language, "prefix_create"))


@dp.message(Command("fromphoto"))
async def image_command(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ThemeStates.waiting_image)
    language = user_language(message.from_user.id)
    await message.answer(tr(language, "prompt_image_command"))


@dp.message(Command("catalog"))
async def catalog_command(message: Message, state: FSMContext):
    await state.set_state(None)
    await show_catalog(message)


@dp.message(Command("help"))
async def help_command(message: Message, state: FSMContext):
    await state.set_state(None)
    await send_help(message)


@dp.message(Command("version"))
async def version_command(message: Message):
    language = user_language(message.from_user.id)
    await message.answer(tr(language, "version_text", version=html.escape(APP_VERSION)), parse_mode=ParseMode.HTML)


@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    language = user_language(message.from_user.id)
    await message.answer(tr(language, "cancelled"), reply_markup=main_menu(language))


async def send_help(message: Message, language: str | None = None):
    language = language or user_language(message.from_user.id)
    await message.answer(
        tr(language, "help_title") + tr(language, "help_body"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr(language, "help_cloud_editor"), url="https://themes.telegram.org")],
            [InlineKeyboardButton(text=tr(language, "home"), callback_data="home")],
        ]),
        parse_mode=ParseMode.HTML,
    )


@dp.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    await send_help(callback.message, language)
    await callback.answer()


@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    language = user_language(callback.from_user.id)
    await state.update_data(theme=default_theme(language), wallpaper_path=None)
    await send_welcome(callback.message, language)
    await callback.answer()


@dp.callback_query(F.data == "create")
async def create_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    language = user_language(callback.from_user.id)
    theme = default_theme(language)
    await state.update_data(theme=theme, wallpaper_path=None)
    await show_theme(callback.message, theme, prefix=tr(language, "prefix_create"), language=language)
    await callback.answer()


@dp.callback_query(F.data == "image")
async def image_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ThemeStates.waiting_image)
    language = user_language(callback.from_user.id)
    await callback.message.answer(tr(language, "prompt_image"))
    await callback.answer()


@dp.message(ThemeStates.waiting_image, F.photo | F.document)
async def image_upload(message: Message, state: FSMContext, bot: Bot):
    language = user_language(message.from_user.id)
    progress_message = await message.answer(
        tr(language, "photo_progress", percent=3, stage=tr(language, "photo_stage_downloading")),
        parse_mode=ParseMode.HTML,
    )
    try:
        raw = await download_with_progress(
            progress_message,
            language,
            lambda report: download_telegram_image(message, bot, report),
        )
        await apply_image_to_theme(message, state, raw, progress_message)
    except (ValueError, UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        try:
            await progress_message.edit_text(
                tr(language, "photo_progress_error", error=html.escape(str(exc))),
                parse_mode=ParseMode.HTML,
            )
        except Exception as edit_exc:
            print(f"Не удалось показать ошибку обработки фото: {edit_exc}")


@dp.message(ThemeStates.waiting_image, F.text)
async def image_url(message: Message, state: FSMContext):
    language = user_language(message.from_user.id)
    url = (message.text or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        await message.answer(tr(language, "image_waiting"))
        return

    progress_message = await message.answer(
        tr(language, "photo_progress", percent=3, stage=tr(language, "photo_stage_downloading")),
        parse_mode=ParseMode.HTML,
    )
    try:
        raw = await download_with_progress(
            progress_message,
            language,
            lambda report: safe_download_image(url, report),
        )
        await apply_image_to_theme(message, state, raw, progress_message)
    except (ValueError, aiohttp.ClientError, asyncio.TimeoutError, UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        try:
            await progress_message.edit_text(
                tr(language, "photo_progress_error", error=html.escape(str(exc))),
                parse_mode=ParseMode.HTML,
            )
        except Exception as edit_exc:
            print(f"Не удалось показать ошибку загрузки фото: {edit_exc}")


async def apply_image_to_theme(
    message: Message,
    state: FSMContext,
    raw: bytes,
    progress_message: Message | None = None,
):
    language = user_language(message.from_user.id)
    if len(raw) > MAX_IMAGE_BYTES:
        error_text = tr(language, "image_too_large")
        if progress_message:
            await progress_message.edit_text(error_text)
        else:
            await message.answer(error_text)
        return

    if progress_message:
        await update_photo_progress(progress_message, language, 32, "photo_stage_analyzing")
        colors, wallpaper = await prepare_photo_assets_with_progress(
            message.from_user.id,
            raw,
            progress_message,
            language,
        )
    else:
        colors, wallpaper = await asyncio.to_thread(
            prepare_photo_assets,
            message.from_user.id,
            raw,
        )

    if not colors:
        error_text = tr(language, "image_no_colors")
        if progress_message:
            await progress_message.edit_text(error_text)
        else:
            await message.answer(error_text)
        return

    theme = create_photo_theme(colors)
    theme["name"] = tr(language, "default_theme_name")
    await state.clear()
    await state.update_data(
        theme=theme,
        photo_theme_original=theme.copy(),
        wallpaper_path=str(wallpaper),
        image_palette=colors,
    )
    await show_theme(
        message,
        theme,
        str(wallpaper),
        prefix=tr(language, "prefix_photo"),
        image_palette=colors,
        language=language,
        progress_message=progress_message,
    )


@dp.callback_query(F.data.startswith("field:"))
async def choose_field(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    field = callback.data.split(":", 1)[1]
    if field not in FIELD_LABELS:
        await callback.answer(tr(language, "field_unknown"), show_alert=True)
        return
    data = await state.get_data()
    image_palette = data.get("image_palette")
    await state.update_data(editing_field=field)
    instruction = tr(language, "photo_palette_prompt") if image_palette else tr(language, "color_prompt")
    await callback.message.answer(
        f"<b>{field_label(language, field)}</b>\n{field_help(language, field)}\n\n{instruction}",
        reply_markup=color_choice_keyboard(language, field, image_palette),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("csethex:"))
async def set_extracted_color(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    try:
        _, field, raw_color = callback.data.split(":", 2)
        color = parse_color(raw_color)
    except ValueError:
        field, color = None, None
    data = await state.get_data()
    palette = data.get("image_palette") or []
    if field not in FIELD_LABELS or not color or color not in palette:
        await callback.answer(tr(language, "color_not_found"), show_alert=True)
        return
    theme = data.get("theme", default_theme(language))
    theme[field] = color
    if field == "text":
        theme["text_auto"] = False
    elif field == "message_text":
        theme["message_text_auto"] = False
    ensure_text_colors(theme)
    await state.set_state(None)
    await state.update_data(theme=theme)
    await show_theme(
        callback.message,
        theme,
        data.get("wallpaper_path"),
        prefix=tr(language, "prefix_color_selected", field=field_label(language, field), color=color),
        image_palette=palette,
        language=language,
    )
    await callback.answer(tr(language, "photo_color_applied"))


@dp.callback_query(F.data == "shuffle_palette")
async def shuffle_photo_palette(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    data = await state.get_data()
    palette = data.get("image_palette") or []
    if not palette:
        await callback.answer(tr(language, "need_photo_first"), show_alert=True)
        return
    current_theme = data.get("theme", default_theme(language))
    theme = create_photo_theme(palette, previous_theme=current_theme)
    theme["name"] = current_theme.get("name", tr(language, "default_theme_name"))
    await state.set_state(None)
    await state.update_data(theme=theme)
    await show_theme(
        callback.message,
        theme,
        data.get("wallpaper_path"),
        prefix=tr(language, "prefix_palette_shuffled"),
        image_palette=palette,
        language=language,
    )
    await callback.answer(tr(language, "colors_shuffled"))




@dp.callback_query(F.data.startswith("custom:"))
async def custom_color_start(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    field = callback.data.split(":", 1)[1]
    if field not in FIELD_LABELS:
        await callback.answer(tr(language, "field_unknown"), show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(editing_field=field)
    await state.set_state(ThemeStates.waiting_color)
    label = field_label(language, field)
    if data.get("image_palette"):
        prompt = tr(language, "enter_hex_photo", field=html.escape(label))
    else:
        prompt = tr(language, "enter_color", field=html.escape(label))
    await callback.message.answer(prompt, parse_mode=ParseMode.HTML)
    await callback.answer()




@dp.callback_query(F.data.startswith("cset:"))
async def set_named_color(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    try:
        _, field, color_name = callback.data.split(":", 2)
    except ValueError:
        await callback.answer(tr(language, "color_read_error"), show_alert=True)
        return
    if field not in FIELD_LABELS or color_name not in NAMED_COLORS:
        await callback.answer(tr(language, "color_unknown"), show_alert=True)
        return
    data = await state.get_data()
    theme = data.get("theme", default_theme(language))
    theme[field] = NAMED_COLORS[color_name]
    await state.set_state(None)
    if field == "text":
        theme["text_auto"] = False
    elif field == "message_text":
        theme["message_text_auto"] = False
    ensure_text_colors(theme)
    await state.update_data(theme=theme)
    await show_theme(
        callback.message,
        theme,
        data.get("wallpaper_path"),
        prefix=tr(language, "prefix_field_changed", field=field_label(language, field)),
        image_palette=data.get("image_palette"),
        language=language,
    )
    await callback.answer()




@dp.message(ThemeStates.waiting_color)
async def set_color(message: Message, state: FSMContext):
    language = user_language(message.from_user.id)
    data = await state.get_data()
    color = parse_color(message.text or "")
    if not color:
        error_key = "hex_invalid" if data.get("image_palette") else "color_invalid"
        await message.answer(tr(language, error_key), parse_mode=ParseMode.HTML)
        return
    theme = data.get("theme", default_theme(language))
    field = data.get("editing_field")
    if field not in FIELD_LABELS:
        await state.set_state(None)
        await message.answer(tr(language, "field_not_selected"), reply_markup=main_menu(language))
        return
    theme[field] = color
    if field == "text":
        theme["text_auto"] = False
    elif field == "message_text":
        theme["message_text_auto"] = False
    ensure_text_colors(theme)
    await state.set_state(None)
    await state.update_data(theme=theme)
    await show_theme(
        message,
        theme,
        data.get("wallpaper_path"),
        prefix=tr(language, "prefix_field_changed", field=field_label(language, field)),
        image_palette=data.get("image_palette"),
    )




@dp.callback_query(F.data.startswith("opacity:"))
async def choose_opacity(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    field = callback.data.split(":", 1)[1]
    if field not in ("outgoing", "incoming"):
        await callback.answer(tr(language, "field_unknown"), show_alert=True)
        return
    prompt = tr(language, "opacity_prompt_outgoing" if field == "outgoing" else "opacity_prompt_incoming")
    prompt += " " + tr(language, "opacity_explainer")
    await callback.message.answer(prompt, reply_markup=opacity_keyboard(language, field))
    await callback.answer()




@dp.callback_query(F.data.startswith("opset:"))
async def set_opacity(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    try:
        _, field, value = callback.data.split(":", 2)
        opacity = int(value)
    except (ValueError, TypeError):
        await callback.answer(tr(language, "opacity_invalid"), show_alert=True)
        return
    if field not in ("outgoing", "incoming") or opacity not in (20, 30, 40, 50, 60, 70, 80, 90, 100):
        await callback.answer(tr(language, "opacity_invalid"), show_alert=True)
        return
    data = await state.get_data()
    theme = data.get("theme", default_theme(language))
    theme[f"{field}_opacity"] = opacity
    ensure_text_colors(theme)
    await state.set_state(None)
    await state.update_data(theme=theme)
    await show_theme(
        callback.message,
        theme,
        data.get("wallpaper_path"),
        prefix=tr(language, "prefix_opacity"),
        image_palette=data.get("image_palette"),
        language=language,
    )
    await callback.answer()




@dp.callback_query(F.data == "rename")
async def rename_start(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    await state.set_state(ThemeStates.waiting_name)
    await callback.message.answer(tr(language, "rename_prompt"))
    await callback.answer()


@dp.message(ThemeStates.waiting_name)
async def rename_theme(message: Message, state: FSMContext):
    language = user_language(message.from_user.id)
    name = (message.text or "").strip()
    if not name or len(name) > 48:
        await message.answer(tr(language, "name_invalid"))
        return
    data = await state.get_data()
    theme = data.get("theme", default_theme(language))
    theme["name"] = name
    await state.set_state(None)
    await state.update_data(theme=theme)
    await show_theme(
        message,
        theme,
        data.get("wallpaper_path"),
        prefix=tr(language, "name_saved"),
        image_palette=data.get("image_palette"),
    )




@dp.callback_query(F.data == "reset")
async def reset_theme(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    await state.set_state(None)
    data = await state.get_data()
    old_theme = data.get("theme", default_theme(language))
    original_photo_theme = data.get("photo_theme_original")
    if data.get("image_palette") and original_photo_theme:
        fresh = original_photo_theme.copy()
    else:
        fresh = default_theme(language)
    fresh["name"] = old_theme.get("name", fresh.get("name", tr(language, "default_theme_name")))
    # Resetting colours does not silently reset the opacity controls.
    fresh["outgoing_opacity"] = old_theme.get("outgoing_opacity", fresh.get("outgoing_opacity", 100))
    fresh["incoming_opacity"] = old_theme.get("incoming_opacity", fresh.get("incoming_opacity", 100))
    ensure_text_colors(fresh)
    await state.update_data(theme=fresh)
    await show_theme(
        callback.message,
        fresh,
        data.get("wallpaper_path"),
        prefix=tr(language, "prefix_reset"),
        image_palette=data.get("image_palette"),
        language=language,
    )
    await callback.answer()




async def show_catalog(message: Message, language: str | None = None):
    language = language or user_language(message.from_user.id)
    items = load_catalog()
    catalog_translations = {
        "midnight": ("Midnight", "Cool dark palette"),
        "sakura": ("Sakura", "Soft pink shades"),
        "moss": ("Moss", "Calm green shades"),
        "lavender": ("Lavender", "Light lilac palette"),
        "ember": ("Ember", "Warm dark palette"),
    }
    buttons = []
    for item in items:
        name = item["name"]
        description = item["description"]
        if language == "en":
            name, description = catalog_translations.get(
                item.get("id"), (name, description)
            )
        buttons.append([
            InlineKeyboardButton(
                text=f"{name} — {description}",
                callback_data=f"preset:{item['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text=tr(language, "home"), callback_data="home")])
    await message.answer(
        tr(language, "catalog_prompt"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )




@dp.callback_query(F.data == "catalog")
async def catalog_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    await show_catalog(callback.message, language)
    await callback.answer()


@dp.callback_query(F.data.startswith("preset:"))
async def use_preset(callback: CallbackQuery, state: FSMContext):
    language = user_language(callback.from_user.id)
    key = callback.data.split(":", 1)[1]
    preset = next((item for item in load_catalog() if item.get("id") == key), None)
    if not preset:
        await callback.answer(tr(language, "catalog_not_found"), show_alert=True)
        return
    theme = default_theme(language)
    theme.update({k: v for k, v in preset.items() if k in theme})
    if language == "en":
        preset_names = {
            "midnight": "Midnight",
            "sakura": "Sakura",
            "moss": "Moss",
            "lavender": "Lavender",
            "ember": "Ember",
        }
        theme["name"] = preset_names.get(key, theme.get("name", "My theme"))
    # Explicit palette values must not be replaced by automatic text generation.
    theme["text_auto"] = "text" not in preset
    theme["message_text_auto"] = "message_text" not in preset
    theme["muted_auto"] = "muted" not in preset
    ensure_text_colors(theme)
    await state.clear()
    await state.update_data(theme=theme, wallpaper_path=None)
    await show_theme(callback.message, theme, prefix=tr(language, "prefix_preset"), language=language)
    await callback.answer()




@dp.callback_query(F.data == "export_menu")
async def export_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    await callback.message.answer(
        tr(language, "export_prompt"),
        reply_markup=export_keyboard(language),
    )
    await callback.answer()


@dp.callback_query(F.data == "export:other")
async def export_other(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    await callback.message.answer(
        tr(language, "export_more"),
        reply_markup=other_export_keyboard(language),
    )
    await callback.answer()




@dp.callback_query(F.data == "back_theme")
async def back_theme(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    data = await state.get_data()
    theme = data.get("theme", default_theme(language))
    await show_theme(
        callback.message,
        theme,
        data.get("wallpaper_path"),
        image_palette=data.get("image_palette"),
        language=language,
    )
    await callback.answer()




@dp.callback_query(F.data.startswith("export:"))
async def export_platform(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    language = user_language(callback.from_user.id)
    data = await state.get_data()
    theme = data.get("theme", default_theme(language))
    ensure_text_colors(theme)
    wallpaper_value = data.get("wallpaper_path")
    wallpaper = Path(wallpaper_value) if wallpaper_value and Path(wallpaper_value).exists() else None
    name = safe_filename(theme.get("name", "TelegramTheme"))
    platform = callback.data.split(":", 1)[1]

    if platform == "other":
        return

    if platform == "windows":
        payload = create_desktop_theme(theme, wallpaper)
        filename = f"{name}.tdesktop-theme"
        caption = tr(language, "export_windows")
        if wallpaper:
            caption += "\n" + tr(language, "wallpaper_embedded")
    elif platform == "desktop_palette":
        payload = desktop_palette_text(theme)
        filename = f"{name}.tdesktop-palette"
        caption = tr(language, "export_desktop_palette")
    elif platform == "android":
        payload = create_android_theme(theme, wallpaper)
        filename = f"{name}.attheme"
        caption = tr(language, "export_android")
        if wallpaper:
            caption += "\n" + tr(language, "wallpaper_embedded")
    elif platform == "ios":
        payload = create_ios_theme(theme)
        filename = f"{name}.tgios-theme"
        caption = tr(language, "export_ios")
    elif platform == "macos":
        payload = create_macos_palette(theme)
        filename = f"{name}.palette"
        caption = tr(language, "export_macos")
    elif platform == "tgx":
        payload = create_tgx_theme(theme)
        filename = f"{name}.tgx-theme"
        caption = tr(language, "export_tgx")
    else:
        await callback.answer(tr(language, "unknown_format"), show_alert=True)
        return

    await callback.message.answer_document(
        BufferedInputFile(payload, filename=filename),
        caption=caption,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer(tr(language, "file_ready"))


INSTANCE_LOCK_HANDLE = None


def acquire_instance_lock():
    """Prevent two local copies from polling the same bot token at once."""
    global INSTANCE_LOCK_HANDLE
    # BackgroundRunner acquires this lock before running the updater. Direct
    # launches of bot.py still acquire it here.
    if os.environ.get("THEME_MAKER_RUNNER_LOCK_HELD") == "1":
        return
    lock_path = ROOT / ".bot.lock"
    handle = open(lock_path, "a+b")
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
    except (OSError, BlockingIOError) as exc:
        handle.close()
        raise RuntimeError("Эта копия бота уже запущена. Закрой первое окно Start.bat и повтори запуск.") from exc
    INSTANCE_LOCK_HANDLE = handle


async def main():
    try:
        acquire_instance_lock()
    except RuntimeError as exc:
        print(f"Ошибка запуска: {exc}")
        raise SystemExit(1) from exc
    bot = Bot(TOKEN)
    try:
        await set_user_commands(bot)
        print("Команды бота зарегистрированы в меню Telegram.")
    except Exception as exc:
        # Registration requires an internet connection, but a temporary
        # connection delay at Windows sign-in must not stop polling.
        print(f"Не удалось обновить список команд при запуске (не критично): {exc}")
    print(f"Theme Maker {APP_VERSION} запущен. Для остановки нажми Ctrl+C.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
