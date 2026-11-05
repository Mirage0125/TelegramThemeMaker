# Telegram Theme Maker

Windows Telegram bot for creating Telegram themes from photos or manually.

- Current application version: see [VERSION.txt](VERSION.txt)
- Python dependencies: [requirements.txt](requirements.txt)
- Safe example configuration: [config.example.env](config.example.env)
- Release workflow: [.github/workflows/release.yml](.github/workflows/release.yml)

## Important: initial source upload

This repository has been initialized with release metadata and the GitHub Actions workflow. The full application source still needs to be uploaded from the Windows ZIP package. Download the **TelegramThemeMaker 3.7.1** ZIP, extract it, then use GitHub's **Add file → Upload files** to upload the contents of the inner `TelegramThemeMaker` folder to the repository root. Do not upload `.env`, `.venv`, `user_data`, or `logs`.

## Windows setup

1. Install Python 3.10–3.14.
2. Run `Start.bat`.
3. On first run, add your BotFather token to the local `.env` file.
4. Run `Start.bat` again.

Optional background startup after Windows sign-in: run `Install-Autostart.vbs` after the first successful start.

## Automatic updates

After the full application source is uploaded and the first release is published, the background runner checks the latest stable release on startup. Release ZIPs are verified with SHA-256 before installation. The updater preserves local `.env`, `.venv`, `user_data/`, and `logs/`.

To publish a release, update `VERSION.txt` and push a matching tag such as `v3.7.2`. GitHub Actions builds the Windows ZIP and checksum.

## Security

Never commit `.env`, bot tokens, `.venv/`, logs, or user-generated files. The repository `.gitignore` excludes these paths.
