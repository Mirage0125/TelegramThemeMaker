"""Language preferences and short UI translations for Telegram Theme Maker.

Language choice is stored separately from the editor FSM so it survives /start,
editor resets, bot restarts, and automatic project updates.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


SUPPORTED_LANGUAGES = {"ru", "en"}


class LanguagePreferences:
    """Small SQLite-backed per-user language store."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path, timeout=10)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_languages (
                    user_id INTEGER PRIMARY KEY,
                    language TEXT NOT NULL CHECK (language IN ('ru', 'en'))
                )
                """
            )
            connection.commit()

    def get_language(self, user_id: int) -> str:
        with closing(sqlite3.connect(self.database_path, timeout=10)) as connection:
            row = connection.execute(
                "SELECT language FROM user_languages WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        return row[0] if row and row[0] in SUPPORTED_LANGUAGES else "ru"

    def has_language(self, user_id: int) -> bool:
        """Return whether the user explicitly selected a language before."""
        with closing(sqlite3.connect(self.database_path, timeout=10)) as connection:
            row = connection.execute(
                "SELECT 1 FROM user_languages WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        return row is not None

    def set_language(self, user_id: int, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language!r}")
        with closing(sqlite3.connect(self.database_path, timeout=10)) as connection:
            connection.execute(
                """
                INSERT INTO user_languages (user_id, language)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
                """,
                (int(user_id), language),
            )
            connection.commit()


TEXTS = {
    "ru": {
        "choose_language": (
            "<b>Добро пожаловать в Theme Maker!</b>\n\n"
            "Сначала выбери язык интерфейса. Его всегда можно будет поменять в главном меню."
        ),
        "language_selected": "Готово! Язык сохранён. Сейчас покажу, что умеет Theme Maker.",
        "language_saved": "Язык сохранён",
        "language_button": "🌐 Язык / Language",
        "welcome": (
            "<b>Привет! Я Theme Maker</b>\n\n"
            "Давай соберём тему для Telegram. Можно взять за основу фотографию или подобрать цвета вручную — "
            "я покажу предпросмотр, а тебе останется выбрать то, что нравится.\n\n"
            "С чего начнём?"
        ),
        "menu_photo": "🖼 Создать тему из фото",
        "menu_manual": "🎨 Собрать тему вручную",
        "menu_catalog": "📚 Готовые темы",
        "menu_help": "❔ Как установить тему",
        "field_background": "Основной цвет",
        "field_accent": "Акцент",
        "field_outgoing": "Мои сообщения",
        "field_incoming": "Входящие сообщения",
        "field_text": "Основной текст",
        "field_message_text": "Текст сообщений",
        "field_background_help": "Фон окон, списка чатов и панелей. Это не фотография-обои.",
        "field_accent_help": "Кнопки, ссылки, команды, галочки, иконки файлов и другие активные элементы.",
        "field_outgoing_help": "Заливка пузырей сообщений, которые отправляешь ты.",
        "field_incoming_help": "Заливка пузырей сообщений собеседников.",
        "field_text_help": "Обычный текст интерфейса: заголовки, названия чатов и разделов.",
        "field_message_text_help": "Текст внутри сообщений. По умолчанию выбирается контрастный чёрный или белый.",
        "opacity_outgoing": "Прозрачность моих сообщений",
        "opacity_incoming": "Прозрачность входящих",
        "rename": "✏️ Название темы",
        "reset": "↺ Сбросить цвета",
        "shuffle": "🎲 Перемешать цвета",
        "export": "📦 Экспортировать тему",
        "home": "🏠 Главное меню",
        "back": "↩️ Назад",
        "custom_hex": "✏️ Ввести свой HEX",
        "custom_color": "✏️ Ввести название или HEX",
        "export_other": "Другие форматы…",
        "back_export": "↩️ Назад к настройкам",
        "photo_palette_prompt": "Выбери один из оттенков, которые нашлись на фотографии.\nHEX-код — точное значение цвета.",
        "color_prompt": "Выбери название цвета или введи свой оттенок.",
        "theme_wallpaper": "На макете показаны выбранные обои.",
        "theme_solid": "Пока здесь однотонный фон. Фотографию можно добавить через главное меню.",
        "palette_note_title": "Палитра из фото:",
        "palette_note": (
            "При настройке можно выбрать любой из этих оттенков. "
            "«Перемешать цвета» соберёт новое сочетание, не меняя фотографию."
        ),
        "theme_legend_title": "Что здесь можно настроить:",
        "legend_background": "• Основной цвет — панели и фон окон.",
        "legend_accent": "• Акцент — ссылки, кнопки, выделение и активные элементы.",
        "legend_outgoing": "• Мои сообщения — фон твоих сообщений.",
        "legend_incoming": "• Входящие — фон сообщений собеседников.",
        "legend_opacity": "• Прозрачность — насколько видны обои сквозь сообщения.",
        "theme_auto_text": (
            "Цвет основного текста и текста сообщений настраивается отдельно. "
            "По умолчанию я подбираю контрастный вариант автоматически."
        ),
        "prefix_create": "Новая тема готова к настройке.\n\n",
        "prefix_photo": (
            "Готово! Я взял цвета с фотографии. Можно выбрать отдельные оттенки "
            "или перемешать их сочетание.\n\n"
        ),
        "prefix_color_selected": "Для параметра «{field}» выбран цвет {color}.\n\n",
        "prefix_palette_shuffled": "Новое сочетание из той же фотографии готово.\n\n",
        "prefix_field_changed": "Параметр «{field}» обновлён.\n\n",
        "prefix_opacity": "Прозрачность обновлена.\n\n",
        "prefix_preset": "Готовая тема выбрана. Давай настроим её под себя.\n\n",
        "prefix_reset": "Цвета возвращены к исходному варианту. Обои, название и прозрачность сохранены.\n\n",
        "prompt_image": (
            "Пришли фотографию как фото или файл. Можно также вставить прямую ссылку на JPG, PNG или WebP.\n\n"
            "После загрузки я покажу макет Telegram с этой картинкой и подобранными цветами."
        ),
        "prompt_image_command": (
            "Пришли фотографию как фото или файл либо вставь прямую ссылку на изображение. "
            "Я использую её как обои там, где формат темы это поддерживает."
        ),
        "photo_progress": "<b>Загрузка: {percent}%</b>\n{stage}",
        "photo_progress_error": "Не получилось обработать фото: {error}",
        "photo_stage_downloading": "Получаю изображение…",
        "photo_stage_analyzing": "Проверяю изображение…",
        "photo_stage_palette": "Подбираю цвета по фотографии…",
        "photo_stage_saving": "Сохраняю обои…",
        "photo_stage_preview": "Готовлю предпросмотр темы…",
        "photo_stage_done": "Готово!",
        "image_waiting": "Жду изображение. Пришли его файлом или вставь прямую ссылку на картинку.",
        "image_too_large": "Изображение великовато: максимальный размер — 12 МБ.",
        "image_no_colors": "Не получилось подобрать цвета по этой картинке. Попробуй другое изображение.",
        "image_error": "Не получилось обработать изображение: {error}",
        "image_url_error": "Не удалось загрузить картинку по ссылке: {error}",
        "field_unknown": "Неизвестный параметр",
        "color_not_found": "Этого цвета нет в палитре фотографии.",
        "photo_color_applied": "Цвет с фотографии применён",
        "need_photo_first": "Сначала создай тему из фотографии.",
        "colors_shuffled": "Цвета перемешаны",
        "enter_hex_photo": "Введи HEX-цвет для «{field}», например <code>#FF88AA</code> или <code>FF88AA</code>.",
        "enter_color": (
            "Введи цвет для «{field}». Можно написать <b>black</b>, <b>белый</b>, "
            "<b>red</b>, <b>серый</b>, <b>#FF88AA</b> или <b>FF88AA</b> без решётки."
        ),
        "color_read_error": "Не удалось прочитать цвет.",
        "color_unknown": "Такого цвета нет в списке.",
        "hex_invalid": "Не распознал HEX. Введи шестизначный код, например <code>#FF88AA</code> или <code>FF88AA</code>.",
        "color_invalid": (
            "Не распознал цвет. Напиши название (например, <b>black</b>, <b>white</b>, "
            "<b>gray</b>, <b>red</b>) или шестизначный код вроде <code>FF88AA</code> без #."
        ),
        "field_not_selected": "Не выбран параметр. Открой конструктор ещё раз.",
        "opacity_prompt_outgoing": "Выбери прозрачность своих сообщений.",
        "opacity_prompt_incoming": "Выбери прозрачность входящих сообщений.",
        "opacity_explainer": "100% — сообщения непрозрачные, 50% — обои заметно просвечивают.",
        "opacity_invalid": "Не получилось распознать прозрачность.",
        "rename_prompt": "Как назовём тему? Например: Sakura Evening",
        "name_invalid": "Название должно содержать от 1 до 48 символов.",
        "name_saved": "Название сохранено.\n\n",
        "reset_missing": "Не удалось найти тему. Создай её ещё раз из главного меню.",
        "catalog_prompt": "Выбери тему, с которой хочешь начать:",
        "catalog_not_found": "Не удалось найти эту тему.",
        "export_prompt": "Для какого приложения подготовить файл темы?",
        "export_more": "Есть и другие форматы:",
        "help_title": "<b>Как пользоваться экспортом</b>\n\n",
        "help_body": (
            "• <b>Windows / Telegram Desktop:</b> <code>.tdesktop-theme</code> — готовый файл темы; фото встраивается внутрь.\n"
            "• <b>Desktop Theme Editor:</b> <code>.tdesktop-palette</code> — палитра для импорта через редактор тем в настройках Desktop.\n"
            "• <b>Android:</b> <code>.attheme</code> — тема Android; поддерживаемые обои встраиваются в файл.\n"
            "• <b>iPhone / iOS:</b> <code>.tgios-theme</code> — файл с цветами интерфейса; фото в него не встраивается.\n"
            "• <b>macOS:</b> <code>.palette</code> — палитра Telegram для macOS.\n"
            "• <b>Telegram X:</b> <code>.tgx-theme</code> — отдельный формат; фото в него не встраивается.\n\n"
            "Форматы разных приложений не взаимозаменяемы. Чтобы получить облачную ссылку "
            "<code>t.me/addtheme/...</code>, опубликуй тему через официальный редактор от своего аккаунта."
        ),
        "help_cloud_editor": "Открыть редактор облачных тем",
        "version_text": (
            "<b>Telegram Theme Maker {version}</b>\n"
            "Новые версии проверяются автоматически при запуске. Если обновление доступно, "
            "оно устанавливается до появления меню в Telegram."
        ),
        "cancelled": "Хорошо, текущий шаг отменён.",
        "unknown_format": "Неизвестный формат.",
        "file_ready": "Файл темы готов",
        "opacity_label_outgoing": "своих сообщений",
        "opacity_label_incoming": "входящих сообщений",
        "export_windows": "<b>Telegram Desktop для Windows</b>\nОткрой файл в Telegram Desktop и подтверди применение темы.",
        "export_android": "<b>Telegram для Android</b>\nОткрой файл в Telegram на телефоне и выбери применение темы.",
        "export_ios": (
            "<b>Telegram для iPhone / iOS</b>\nОтправь файл в «Избранное», открой его на iPhone и выбери Apply Theme. "
            "Фото-обои в этот формат не встраиваются; цвета интерфейса сохраняются."
        ),
        "export_macos": (
            "<b>Telegram для macOS</b>\nГотова нативная палитра .palette. Фото-обои в этот формат не встраиваются; "
            "после импорта проверь основные экраны в клиенте macOS."
        ),
        "export_tgx": (
            "<b>Telegram X для Android</b>\nОткрой файл в Telegram X и выбери применение темы. "
            "Фото-обои в этот формат пока не встраиваются."
        ),
        "export_desktop_palette": (
            "<b>Палитра Telegram Desktop</b>\nНастройки → Chat Settings → Edit theme → меню ⋮ → Import theme.\n"
            "Этот формат импортируется через редактор, а не открывается как готовая тема двойным щелчком."
        ),
        "wallpaper_embedded": "Изображение включено в файл темы.",
        "color_black": "⚫ Чёрный",
        "color_white": "⚪ Белый",
        "color_gray": "🩶 Серый",
        "color_red": "🔴 Красный",
        "color_orange": "🟠 Оранжевый",
        "color_yellow": "🟡 Жёлтый",
        "color_green": "🟢 Зелёный",
        "color_blue": "🔵 Синий",
        "color_lightblue": "🩵 Голубой",
        "color_cyan": "🩵 Бирюзовый",
        "color_purple": "🟣 Фиолетовый",
        "color_pink": "🩷 Розовый",
        "default_theme_name": "Моя тема",
        "commands": {
            "start": "Главное меню",
            "create": "Создать тему вручную",
            "fromphoto": "Создать тему из фото",
            "catalog": "Готовые темы",
            "help": "Помощь и установка тем",
            "cancel": "Отменить текущий шаг",
            "version": "Версия и обновления",
        },
        "bot_description": "Создание тем Telegram из фотографий и вручную. Предпросмотр и экспорт для разных клиентов Telegram.",
        "bot_short_description": "Создавай темы Telegram из фотографий и цветов.",
    },
    "en": {
        "choose_language": (
            "<b>Welcome to Theme Maker!</b>\n\n"
            "First, choose the interface language. You can change it later from the main menu."
        ),
        "language_selected": "All set! Your language is saved. Here's what Theme Maker can do.",
        "language_saved": "Language saved",
        "language_button": "🌐 Language",
        "welcome": (
            "<b>Hey! I'm Theme Maker</b>\n\n"
            "Let's put together a Telegram theme. Start with a photo or choose the colours yourself — "
            "I'll show you a preview before you export anything.\n\n"
            "Where shall we start?"
        ),
        "menu_photo": "🖼 Create from a photo",
        "menu_manual": "🎨 Create manually",
        "menu_catalog": "📚 Ready-made themes",
        "menu_help": "❔ How to apply a theme",
        "field_background": "Main background",
        "field_accent": "Accent",
        "field_outgoing": "Outgoing messages",
        "field_incoming": "Incoming messages",
        "field_text": "Interface text",
        "field_message_text": "Message text",
        "field_background_help": "The background of windows, chat lists and panels. This is separate from chat wallpaper.",
        "field_accent_help": "Buttons, links, commands, checkmarks, file icons and other active elements.",
        "field_outgoing_help": "The fill colour of messages you send.",
        "field_incoming_help": "The fill colour of messages you receive.",
        "field_text_help": "Regular interface text, such as headings, chat names and section labels.",
        "field_message_text_help": "Text inside chat bubbles. By default, a contrasting black or white is selected automatically.",
        "opacity_outgoing": "Outgoing message opacity",
        "opacity_incoming": "Incoming message opacity",
        "rename": "✏️ Rename theme",
        "reset": "↺ Reset colours",
        "shuffle": "🎲 Shuffle colours",
        "export": "📦 Export theme",
        "home": "🏠 Main menu",
        "back": "↩️ Back",
        "custom_hex": "✏️ Enter a HEX value",
        "custom_color": "✏️ Enter a colour name or HEX",
        "export_other": "More formats…",
        "back_export": "↩️ Back to editor",
        "photo_palette_prompt": "Pick one of the shades found in your photo.\nHEX codes show the exact colour values.",
        "color_prompt": "Choose a colour name or enter your own shade.",
        "theme_wallpaper": "The preview is using your selected wallpaper.",
        "theme_solid": "This theme currently has a solid background. You can add a photo from the main menu.",
        "palette_note_title": "Photo palette:",
        "palette_note": (
            "You can use any of these shades while editing. "
            "Shuffle colours to try a new combination without changing the photo."
        ),
        "theme_legend_title": "What you can customise:",
        "legend_background": "• Main background — panels and window surfaces.",
        "legend_accent": "• Accent — links, buttons, selection and active elements.",
        "legend_outgoing": "• Outgoing — the background of your messages.",
        "legend_incoming": "• Incoming — the background of other people's messages.",
        "legend_opacity": "• Opacity — how much wallpaper shows through the bubbles.",
        "theme_auto_text": (
            "Interface text and message text can be adjusted separately. "
            "By default, I pick a contrasting colour automatically."
        ),
        "prefix_create": "Your new theme is ready to customise.\n\n",
        "prefix_photo": (
            "Done! I've picked a palette from your photo. Choose individual shades "
            "or shuffle them to try another combination.\n\n"
        ),
        "prefix_color_selected": "The colour for “{field}” is now {color}.\n\n",
        "prefix_palette_shuffled": "Here's a fresh combination from the same photo.\n\n",
        "prefix_field_changed": "Updated “{field}”.\n\n",
        "prefix_opacity": "Opacity updated.\n\n",
        "prefix_preset": "Ready-made theme selected. Let's make it yours.\n\n",
        "prefix_reset": "Colours are back to their original values. Wallpaper, name and opacity were kept.\n\n",
        "prompt_image": (
            "Send a photo or an image file. You can also paste a direct JPG, PNG or WebP link.\n\n"
            "Once it arrives, I'll show you a Telegram preview with a matching colour palette."
        ),
        "prompt_image_command": (
            "Send a photo or image file, or paste a direct image link. "
            "I'll use it as chat wallpaper in the theme formats that support it."
        ),
        "photo_progress": "<b>Loading: {percent}%</b>\n{stage}",
        "photo_progress_error": "Couldn't process the photo: {error}",
        "photo_stage_downloading": "Receiving the image…",
        "photo_stage_analyzing": "Checking the image…",
        "photo_stage_palette": "Picking colours from the photo…",
        "photo_stage_saving": "Saving the wallpaper…",
        "photo_stage_preview": "Preparing the theme preview…",
        "photo_stage_done": "All done!",
        "image_waiting": "I'm ready for the image — send it as a file or paste a direct image link.",
        "image_too_large": "That image is a bit too large. The limit is 12 MB.",
        "image_no_colors": "I couldn't find a usable colour palette in that image. Try another one.",
        "image_error": "I couldn't process that image. Please try another JPG, PNG or WebP file.",
        "image_url_error": "I couldn't download the image from that link. Try sending the image file instead.",
        "field_unknown": "Unknown setting.",
        "color_not_found": "That colour isn't in the photo palette.",
        "photo_color_applied": "Photo colour applied",
        "need_photo_first": "Create a photo-based theme first.",
        "colors_shuffled": "Colours shuffled",
        "enter_hex_photo": "Enter a HEX colour for “{field}”, for example <code>#FF88AA</code> or <code>FF88AA</code>.",
        "enter_color": (
            "Enter a colour for “{field}”. You can use <b>black</b>, <b>white</b>, "
            "<b>red</b>, <b>gray</b>, <b>#FF88AA</b> or <b>FF88AA</b> without the #."
        ),
        "color_read_error": "I couldn't read that colour.",
        "color_unknown": "That colour isn't in the list.",
        "hex_invalid": "That doesn't look like a HEX value. Enter six digits, for example <code>#FF88AA</code> or <code>FF88AA</code>.",
        "color_invalid": (
            "I couldn't recognise that colour. Try a name such as <b>black</b>, <b>white</b>, "
            "<b>gray</b> or <b>red</b>, or enter a six-digit HEX value such as <code>FF88AA</code>."
        ),
        "field_not_selected": "No setting is selected. Please open the editor again.",
        "opacity_prompt_outgoing": "Choose the opacity of your outgoing messages.",
        "opacity_prompt_incoming": "Choose the opacity of incoming messages.",
        "opacity_explainer": "100% is fully opaque; at 50%, the wallpaper shows through more clearly.",
        "opacity_invalid": "That opacity value isn't valid.",
        "rename_prompt": "What should we call this theme? For example: Sakura Evening",
        "name_invalid": "The name must contain between 1 and 48 characters.",
        "name_saved": "Theme name saved.\n\n",
        "reset_missing": "I couldn't find the current theme. Please create it again from the main menu.",
        "catalog_prompt": "Choose a theme to start with:",
        "catalog_not_found": "I couldn't find that theme.",
        "export_prompt": "Which Telegram app do you need the theme file for?",
        "export_more": "Here are the additional formats:",
        "help_title": "<b>Export formats and how to use them</b>\n\n",
        "help_body": (
            "• <b>Windows / Telegram Desktop:</b> <code>.tdesktop-theme</code> — a ready-to-open theme file; the photo is included.\n"
            "• <b>Desktop Theme Editor:</b> <code>.tdesktop-palette</code> — a palette to import through Desktop's theme editor.\n"
            "• <b>Android:</b> <code>.attheme</code> — an Android theme; supported wallpapers are included in the file.\n"
            "• <b>iPhone / iOS:</b> <code>.tgios-theme</code> — a file with interface colours; photos are not embedded.\n"
            "• <b>macOS:</b> <code>.palette</code> — a native Telegram macOS palette.\n"
            "• <b>Telegram X:</b> <code>.tgx-theme</code> — a separate format; photos are not embedded.\n\n"
            "Formats for different Telegram apps are not interchangeable. To get a cloud link "
            "such as <code>t.me/addtheme/...</code>, publish the theme through the official editor from your account."
        ),
        "help_cloud_editor": "Open the cloud theme editor",
        "version_text": (
            "<b>Telegram Theme Maker {version}</b>\n"
            "The bot checks for new versions automatically when it starts. Available updates "
            "are installed before the Telegram menu appears."
        ),
        "cancelled": "No problem — the current step has been cancelled.",
        "unknown_format": "Unknown export format.",
        "file_ready": "Your theme file is ready",
        "opacity_label_outgoing": "outgoing messages",
        "opacity_label_incoming": "incoming messages",
        "export_windows": "<b>Telegram Desktop for Windows</b>\nOpen the file in Telegram Desktop and confirm that you want to apply the theme.",
        "export_android": "<b>Telegram for Android</b>\nOpen the file in Telegram on your phone and choose to apply the theme.",
        "export_ios": (
            "<b>Telegram for iPhone / iOS</b>\nSend the file to Saved Messages, open it on your iPhone and choose Apply Theme. "
            "Photo wallpapers are not embedded in this format; interface colours are preserved."
        ),
        "export_macos": (
            "<b>Telegram for macOS</b>\nA native .palette file is ready. Photo wallpapers are not embedded; "
            "check the main screens in the macOS client after importing."
        ),
        "export_tgx": (
            "<b>Telegram X for Android</b>\nOpen the file in Telegram X and choose to apply the theme. "
            "Photo wallpapers are not embedded in this format yet."
        ),
        "export_desktop_palette": (
            "<b>Telegram Desktop palette</b>\nSettings → Chat Settings → Edit theme → ⋮ menu → Import theme.\n"
            "Import this file through the editor; it is not a ready-made theme to open by double-clicking."
        ),
        "wallpaper_embedded": "The image is included in the theme file.",
        "color_black": "⚫ Black",
        "color_white": "⚪ White",
        "color_gray": "🩶 Gray",
        "color_red": "🔴 Red",
        "color_orange": "🟠 Orange",
        "color_yellow": "🟡 Yellow",
        "color_green": "🟢 Green",
        "color_blue": "🔵 Blue",
        "color_lightblue": "🩵 Light blue",
        "color_cyan": "🩵 Turquoise",
        "color_purple": "🟣 Purple",
        "color_pink": "🩷 Pink",
        "default_theme_name": "My theme",
        "commands": {
            "start": "Open the main menu",
            "create": "Create a theme manually",
            "fromphoto": "Create a theme from a photo",
            "catalog": "Browse ready-made themes",
            "help": "Help and applying themes",
            "cancel": "Cancel the current step",
            "version": "Version and updates",
        },
        "bot_description": "Create Telegram themes from photos or colours. Preview and export for different Telegram apps.",
        "bot_short_description": "Create Telegram themes from photos and colours.",
    },
}


def normalize_language(language: str | None) -> str:
    return language if language in SUPPORTED_LANGUAGES else "ru"


def text(language: str | None, key: str, **values) -> str | dict:
    selected = normalize_language(language)
    template = TEXTS[selected].get(key, TEXTS["ru"].get(key, key))
    return template.format(**values) if values else template
