# Telegram Theme Maker

Windows Telegram bot for creating Telegram themes from images.

## Project files

The complete application source is stored in this repository. The current application version is listed in [VERSION.txt](VERSION.txt).

## Windows setup

1. Install Python 3.10–3.14.
2. Run `Start.bat`.
3. On first run, the launcher creates a local `.env` from `config.example.env`. Paste the token from BotFather into `BOT_TOKEN=`.
4. Save the file and run `Start.bat` again.

To start the bot invisibly after signing in to Windows, run `Install-Autostart.vbs` after the first successful setup. The background runner also checks for updates.

## Automatic updates and releases

The updater checks the latest stable GitHub Release, downloads its ZIP and SHA-256 file, verifies the checksum, and only then applies the update. It preserves local `.env`, virtual environments, `user_data/`, and `logs/`.

To publish a release:

1. Update `VERSION.txt` to the new version, for example `3.7.2`.
2. Commit and push the changes.
3. In GitHub, open **Releases → Draft a new release**.
4. Create a matching tag, for example `v3.7.2`, targeting the updated `main` branch, then publish the release.
5. GitHub Actions builds the Windows ZIP and SHA-256 file and attaches both to that release.

The first release must use tag `v3.7.1` to match the current version. Publishing it will create the first downloadable release package.

## Security

Never commit `.env`, bot tokens, `.venv/`, logs, or user-generated files. The repository `.gitignore` and release workflow exclude local secrets and runtime data.
