import tempfile
import unittest
from pathlib import Path

from Localization import LanguagePreferences, text


class LanguagePreferencesTests(unittest.TestCase):
    def test_default_language_is_russian(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = LanguagePreferences(Path(directory) / "languages.sqlite3")
            self.assertEqual(preferences.get_language(101), "ru")

    def test_language_is_saved_and_survives_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "languages.sqlite3"
            preferences = LanguagePreferences(database)
            preferences.set_language(202, "en")

            reopened = LanguagePreferences(database)
            self.assertEqual(reopened.get_language(202), "en")

            reopened.set_language(202, "ru")
            self.assertEqual(preferences.get_language(202), "ru")

    def test_invalid_language_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = LanguagePreferences(Path(directory) / "languages.sqlite3")
            with self.assertRaises(ValueError):
                preferences.set_language(303, "de")

    def test_unknown_language_falls_back_to_russian(self):
        self.assertEqual(text("de", "menu_photo"), text("ru", "menu_photo"))

    def test_translation_and_commands_are_available(self):
        self.assertEqual(text("en", "menu_photo"), "🖼 Create from a photo")
        self.assertIn("start", text("en", "commands"))
        self.assertIn("соберём", text("ru", "welcome").lower())


if __name__ == "__main__":
    unittest.main()
