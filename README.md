# Telegram Theme Maker

Windows Telegram bot for creating Telegram themes from images.

## Project files

The complete application source is stored in this repository. The current application version is listed in [VERSION.txt](VERSION.txt).

## Windows setup

1. Install Python 3.10–3.14.
2. Run `Start.bat`.
3. On first run, the launcher creates a local `.env` from `config.example.env`. Paste the token from BotFather into `BOT_TOKEN=`.
4. Save the file and run `Start.bat` again.

To start the bot invisibly after signing in to Windows, run `Install-Autostart.vbs` after the first successful setup. The installer verifies the Startup-folder shortcut. Startup diagnostics are written to `logs/autostart.log`; the background process log is `logs/bot.log`.

## Automatic updates and releases

The updater checks the latest stable GitHub Release, downloads its ZIP and SHA-256 file, verifies the checksum, and only then applies the update. It preserves local `.env`, virtual environments, `user_data/`, and `logs/`. A temporary failure while checking GitHub or registering Telegram commands no longer prevents the bot from starting.

To publish a release:

1. Update `VERSION.txt` to the new version, for example `3.7.3`.
2. Commit and push the changes to `main`.
3. GitHub Actions automatically creates the matching `vX.Y.Z` tag and release, builds the Windows ZIP and SHA-256 file, and attaches both assets.

Do not create the release manually; the workflow handles it when `VERSION.txt` changes on `main`.

## Security

Never commit `.env`, bot tokens, `.venv/`, logs, or user-generated files. The repository `.gitignore` and release workflow exclude local secrets and runtime data.
