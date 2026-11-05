# Telegram Theme Maker

Windows Telegram bot for creating Telegram themes from photos or manually.

The repository distributes versioned Windows source archives through GitHub Releases. The project checks the latest stable release on startup, verifies the ZIP with SHA-256, and preserves local `.env`, `.venv`, `user_data/`, and `logs/`.

Current package: **3.7.1**. See `VERSION.txt`.

The full application source is included in the ZIP under `source/`. To install the first auto-updating build, download the 3.7.1 archive from the Releases section and extract it over the existing project folder. Do not replace `.env`.

Never commit bot tokens, `.env`, user-generated content, logs, or virtual environments.