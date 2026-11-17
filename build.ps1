# Builds dist\Trail-Setup.exe on Windows. Easiest: double-click BUILD-INSTALLER.bat
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Python {
    foreach ($c in @("py -3", "python")) {
        try {
            $exe = (& ([scriptblock]::Create("$c -c `"import sys; print(sys.executable)`"")) 2>$null)
            if ($LASTEXITCODE -eq 0 -and $exe -and $exe -notmatch "WindowsApps") { return $exe.Trim() }
        } catch {}
    }
    foreach ($p in @("$env:USERPROFILE\anaconda3\python.exe", "$env:USERPROFILE\miniconda3\python.exe",
                     "$env:ProgramData\anaconda3\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    throw "Python 3.10+ not found. Install it from python.org (tick 'Add to PATH') and run again."
}

Write-Host "== 1/3  Preparing a clean Python environment"
$base = Find-Python
Write-Host "   using $base"
if (-not (Test-Path .build-venv\Scripts\python.exe)) { & $base -m venv .build-venv }
$py = (Resolve-Path ".\.build-venv\Scripts\python.exe").Path
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "== 2/3  Bundling the app (takes a minute or two)"
& $py -m PyInstaller --noconfirm --clean --windowed --log-level WARN `
    --name Trail `
    --icon packaging\icon.ico `
    --collect-all psycopg_binary --hidden-import psycopg_binary `
    run_trail.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "== 3/3  Creating the installer"
function Find-Iscc {
    @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
      "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
      "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
}
$iscc = Find-Iscc
if (-not $iscc) {
    Write-Host "   Inno Setup (free installer builder) is not installed; installing it with winget..."
    winget install --id JRSoftware.InnoSetup -e --scope user --silent `
        --accept-package-agreements --accept-source-agreements
    $iscc = Find-Iscc
}
if (-not $iscc) {
    Write-Host "Could not install Inno Setup automatically. Get it from https://jrsoftware.org/isdl.php and run again."
    Write-Host "Meanwhile the app works without installing: dist\Trail\Trail.exe"
    exit 1
}
& $iscc /Qp packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "`nDone!  Your installer is: $PSScriptRoot\dist\Trail-Setup.exe"
