$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSCommandPath
$LogDir = Join-Path $Root "logs"
$ReportPath = Join-Path $LogDir "check-report.txt"
$script:Checks = @()

function Add-Check {
    param(
        [string]$Name,
        [ValidateSet("PASS", "WARN", "FAIL", "INFO")][string]$Status,
        [string]$Detail
    )
    $line = "[{0}] {1}: {2}" -f $Status, $Name, $Detail
    $script:Checks += $line
    Write-Host $line
}

Write-Host ""
Write-Host "Telegram Theme Maker - installation diagnostics"
Write-Host ("Project: " + $Root)
Write-Host ""

$requiredFiles = @(
    "Start.bat",
    "BackgroundRunner.py",
    "UpdateManager.py",
    "SQLiteStorage.py",
    "bot.py",
    "requirements.txt",
    "VERSION.txt",
    "config.example.env",
    "themes\catalog.json",
    "themes\android_keys.txt",
    "assets\welcome.png"
)
$missingFiles = @()
foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root $relativePath) -PathType Leaf)) {
        $missingFiles += $relativePath
    }
}
if ($missingFiles.Count -eq 0) {
    Add-Check "Project files" "PASS" "All required files are present."
} else {
    Add-Check "Project files" "FAIL" ("Missing: " + ($missingFiles -join ", "))
}

$versionPath = Join-Path $Root "VERSION.txt"
if (Test-Path -LiteralPath $versionPath) {
    $version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
    if ($version -match '^\d+\.\d+\.\d+$') {
        Add-Check "Project version" "PASS" $version
    } else {
        Add-Check "Project version" "FAIL" ("Invalid VERSION.txt value: " + $version)
    }
} else {
    $version = "unknown"
    Add-Check "Project version" "FAIL" "VERSION.txt was not found."
}

$assetPath = Join-Path $Root "assets\welcome.png"
if (Test-Path -LiteralPath $assetPath -PathType Leaf) {
    try {
        $assetBytes = [System.IO.File]::ReadAllBytes($assetPath)
        $pngSignature = @(137, 80, 78, 71, 13, 10, 26, 10)
        $isPng = $assetBytes.Length -ge 8
        for ($i = 0; $i -lt 8 -and $isPng; $i++) {
            if ($assetBytes[$i] -ne $pngSignature[$i]) { $isPng = $false }
        }
        if ($isPng) {
            Add-Check "Welcome image" "PASS" ("PNG signature valid; {0} bytes. File was only read." -f $assetBytes.Length)
        } else {
            Add-Check "Welcome image" "FAIL" "The file does not have a valid PNG signature."
        }
    } catch {
        Add-Check "Welcome image" "FAIL" $_.Exception.Message
    }
}

$updaterPath = Join-Path $Root "UpdateManager.py"
if (Test-Path -LiteralPath $updaterPath) {
    $updaterText = Get-Content -LiteralPath $updaterPath -Raw
    if ($updaterText -match '(?s)PRESERVED_ROOT_ITEMS\s*=\s*\{[^}]*["'']assets["'']') {
        Add-Check "Asset update protection" "PASS" "The updater preserves the local assets directory."
    } else {
        Add-Check "Asset update protection" "FAIL" "The updater does not list assets as a preserved directory."
    }
}

$envPath = Join-Path $Root ".env"
$tokenReady = $false
if (Test-Path -LiteralPath $envPath) {
    $envText = Get-Content -LiteralPath $envPath -Raw
    $tokenMatch = [regex]::Match($envText, '(?m)^\s*BOT_TOKEN\s*=\s*(.*?)\s*$')
    if ($tokenMatch.Success) {
        $tokenValue = $tokenMatch.Groups[1].Value.Trim().Trim('"').Trim("'")
        if ($tokenValue.Length -gt 20 -and $tokenValue -notmatch 'PASTE_YOUR_BOT_TOKEN_HERE') {
            $tokenReady = $true
        }
    }
}
if ($tokenReady) {
    Add-Check "Bot configuration" "PASS" "A BOT_TOKEN value is configured. The token itself is not displayed."
} else {
    Add-Check "Bot configuration" "FAIL" "BOT_TOKEN is missing or still contains the example placeholder in .env."
}

$pythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonExe = $pythonCommand.Source
    } else {
        $pythonExe = $null
    }
}

$pythonReady = $false
$dependenciesReady = $false
if ($pythonExe) {
    $pythonVersion = & $pythonExe -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>&1
    $pythonExit = $LASTEXITCODE
    if ($pythonExit -eq 0 -and "$pythonVersion" -match '^(\d+)\.(\d+)') {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -eq 3 -and $minor -ge 10 -and $minor -le 14) {
            $pythonReady = $true
            Add-Check "Python runtime" "PASS" ("Python " + "$pythonVersion")
        } else {
            Add-Check "Python runtime" "FAIL" ("Found Python " + "$pythonVersion" + "; supported versions are 3.10-3.14.")
        }
    } else {
        Add-Check "Python runtime" "FAIL" ("Could not query Python version: " + ($pythonVersion -join " "))
    }

    if ($pythonReady) {
        & $pythonExe -c "import aiogram, aiohttp, dotenv; from PIL import Image" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $dependenciesReady = $true
            Add-Check "Python dependencies" "PASS" "aiogram, aiohttp, Pillow and python-dotenv are importable."
        } else {
            Add-Check "Python dependencies" "FAIL" "One or more required libraries are missing. Run Start.bat to install requirements."
        }
    }
} else {
    Add-Check "Python runtime" "FAIL" "No project virtual environment or system python.exe was found."
}

if ($pythonReady) {
    $syntaxCheck = @'
import ast
from pathlib import Path
root = Path.cwd()
excluded = {".venv", "venv", "env", "__pycache__", ".git", "user_data"}
files = [p for p in root.rglob("*.py") if not any(part in excluded for part in p.parts)]
for path in files:
    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
print("Parsed", len(files), "Python files.")
'@
    Push-Location $Root
    try {
        $syntaxOutput = & $pythonExe -c $syntaxCheck 2>&1
        $syntaxExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($syntaxExit -eq 0) {
        Add-Check "Python syntax" "PASS" ($syntaxOutput -join " ")
    } else {
        Add-Check "Python syntax" "FAIL" ($syntaxOutput -join " ")
    }
}

if ($pythonReady -and $dependenciesReady) {
    Push-Location $Root
    try {
        $testOutput = & $pythonExe -m unittest discover -s tests -v 2>&1
        $testExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($testExit -eq 0) {
        Add-Check "Regression tests" "PASS" "All automated tests passed."
    } else {
        Add-Check "Regression tests" "FAIL" ($testOutput -join " ")
    }
} else {
    Add-Check "Regression tests" "WARN" "Skipped because Python or required dependencies are unavailable."
}

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Telegram Theme Maker.lnk"
if (Test-Path -LiteralPath $shortcutPath) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        if ($shortcut.Arguments -match 'RunHidden\.vbs') {
            Add-Check "Windows auto-start" "PASS" "The project shortcut is present in the current user's Startup folder."
        } else {
            Add-Check "Windows auto-start" "WARN" "A shortcut exists, but it does not point to RunHidden.vbs."
        }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    } catch {
        Add-Check "Windows auto-start" "WARN" ("Could not inspect the Startup shortcut: " + $_.Exception.Message)
    }
} else {
    Add-Check "Windows auto-start" "WARN" "No startup shortcut is installed. This is optional."
}

try {
    $runnerPath = (Join-Path $Root "BackgroundRunner.py").ToLowerInvariant()
    $botProcesses = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($runnerPath) })
    if ($botProcesses.Count -gt 0) {
        Add-Check "Background process" "PASS" ("Found " + $botProcesses.Count + " Theme Maker process(es).")
    } else {
        Add-Check "Background process" "WARN" "No hidden Theme Maker process is running. Start.bat may still be running in a visible console."
    }
} catch {
    Add-Check "Background process" "WARN" ("Windows did not allow process inspection: " + $_.Exception.Message)
}

foreach ($logName in @("bot.log", "autostart.log")) {
    $logPath = Join-Path $LogDir $logName
    if (Test-Path -LiteralPath $logPath) {
        $logItem = Get-Item -LiteralPath $logPath
        Add-Check ("Log " + $logName) "INFO" ("Present; last modified " + $logItem.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"))
    } else {
        Add-Check ("Log " + $logName) "INFO" "Not created yet."
    }
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$script:Checks | Set-Content -LiteralPath $ReportPath -Encoding UTF8
$failedCount = @($script:Checks | Where-Object { $_ -like "[FAIL]*" }).Count
$passedCount = @($script:Checks | Where-Object { $_ -like "[PASS]*" }).Count
$warningCount = @($script:Checks | Where-Object { $_ -like "[WARN]*" }).Count

Write-Host ""
Write-Host ("Summary: {0} passed, {1} warning(s), {2} failed." -f $passedCount, $warningCount, $failedCount)
Write-Host ("Report: " + $ReportPath)
Write-Host "No files inside assets were modified."

if ($failedCount -gt 0) {
    exit 1
}
exit 0
