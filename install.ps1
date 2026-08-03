# Install Liszt's Python packages into a virtual environment inside this repo.
#
# Standard invocation:
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Options:
#   -WithDeck   also install the slide deck packages
#   -Offline    install from a local vendor\wheels folder, which you build first
#               (the script explains how when the folder is missing)
#
# Works with Windows PowerShell 5.1. No admin rights are needed. Nothing
# outside this repo is changed: the script writes the .venv folder and build
# output here, and that is all.

param(
    [switch]$Offline,
    [switch]$WithDeck
)

# Native commands write progress to the error stream at times; do not let
# that stop the script. Exit codes are checked by hand instead.
$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# ---- find a Python that is at least 3.11 -----------------------------------
#
# 3.11 is the floor, not 3.10, because the pinned packages in requirements/
# require it. Ask for a specific version before the generic names: a machine
# often has an older Python on the path and a newer one installed alongside it.

function Test-PythonAtLeast311 {
    param([string]$Exe, [string[]]$BaseArgs)
    try {
        & $Exe @BaseArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$PyExe = $null
$PyArgs = @()
$candidates = @(
    @{ Exe = "py";      Args = @("-3.13") },
    @{ Exe = "py";      Args = @("-3.12") },
    @{ Exe = "py";      Args = @("-3.11") },
    @{ Exe = "py";      Args = @("-3") },
    @{ Exe = "python";  Args = @() },
    @{ Exe = "python3"; Args = @() }
)
foreach ($c in $candidates) {
    if (Get-Command $c.Exe -ErrorAction SilentlyContinue) {
        if (Test-PythonAtLeast311 -Exe $c.Exe -BaseArgs $c.Args) {
            $PyExe = $c.Exe
            $PyArgs = $c.Args
            break
        }
    }
}
if (-not $PyExe) {
    Write-Host ""
    Write-Host "Liszt needs Python 3.11 or newer, and no such Python was found."
    Write-Host ""
    Write-Host "To install one:"
    Write-Host ""
    Write-Host "  Windows: download the installer from python.org/downloads,"
    Write-Host "           or run: winget install Python.Python.3.11"
    Write-Host ""
    Write-Host "Then run this script again. It will find the new version on its own."
    exit 1
}
$pyVersion = & $PyExe @PyArgs -c "import sys; print('Python ' + '.'.join(str(n) for n in sys.version_info[:3]))"
$pyLabel = ("$PyExe " + ($PyArgs -join " ")).Trim()
Write-Host "Using $pyVersion ($pyLabel)."

# ---- offline mode groundwork -----------------------------------------------

$WheelDir = Join-Path $Root "vendor\wheels"
if ($Offline) {
    $wheels = @(Get-ChildItem -Path $WheelDir -Filter "*.whl" -ErrorAction SilentlyContinue)
    if ($wheels.Count -eq 0) {
        Write-Host ""
        Write-Host "The offline install needs a local folder of wheel files at vendor\wheels, and there is none here."
        Write-Host "This repository does not ship wheel files. Build the folder once on a machine that has package"
        Write-Host "index access, matching the Python version and the platform of THIS machine:"
        Write-Host ""
        Write-Host "  pip download -r requirements/base.txt -r requirements/deck.txt ``"
        Write-Host "      --only-binary=:all: ``"
        Write-Host "      --python-version 3.11 --platform win_amd64 ``"
        Write-Host "      -d vendor/wheels"
        Write-Host ""
        Write-Host "Platform tags: win_amd64 for Windows, manylinux_2_28_x86_64 for Linux x86_64,"
        Write-Host "macosx_11_0_arm64 for Apple Silicon. Then copy vendor\wheels here and run this script again."
        Write-Host ""
        Write-Host "If your organization runs an internal package mirror (Artifactory, Nexus, devpi), point pip at"
        Write-Host "it instead and run this script with no switches:"
        Write-Host ""
        Write-Host "  pip config set global.index-url <your internal index url>"
        Write-Host "  powershell -ExecutionPolicy Bypass -File install.ps1"
        Write-Host ""
        Write-Host "The full procedure is in docs/09-air-gapped.md, section 6."
        exit 1
    }
    Write-Host "Offline mode: installing from the wheel files in vendor\wheels, with no package index."
    Write-Host "The wheels have to match this Python version and platform, or pip will not find them."
}

# ---- create the virtual environment ----------------------------------------

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "Creating the virtual environment at .venv ..."
    $venvOut = (& $PyExe @PyArgs -m venv (Join-Path $Root ".venv") 2>&1) | Out-String
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) {
        if ($venvOut.Trim().Length -gt 0) { Write-Host $venvOut }
        if ($venvOut -match "ensurepip|No module named venv") {
            Write-Host "This Python cannot create a virtual environment because its venv or ensurepip piece is missing; install a full Python 3.11 build and run this script again."
        } else {
            Write-Host "The virtual environment was not created; delete the .venv folder if it exists and run this script again."
        }
        exit 1
    }
}

# ---- install packages -------------------------------------------------------

# Runs pip, stays quiet on success, and explains the two failures people
# actually hit: certificate interception and an externally managed Python.
function Invoke-PipInstall {
    param([string[]]$PipArgs)
    $out = (& $script:VenvPy -m pip install --quiet --no-cache-dir @PipArgs 2>&1) | Out-String
    if ($LASTEXITCODE -ne 0) {
        if ($out.Trim().Length -gt 0) { Write-Host $out }
        if ($out -match "CERTIFICATE_VERIFY_FAILED|certificate verify failed|SSLError|SSLCertVerificationError") {
            Write-Host "That is a certificate failure, which usually means a company proxy inspects secure web traffic; set SSL_CERT_FILE and PIP_CERT to the path of your company root certificate bundle and run this script again."
        }
        if ($out -match "externally-managed-environment") {
            Write-Host "This Python is marked externally managed, which blocks installs outside a virtual environment; delete the .venv folder and run this script again so a fresh one is created."
        }
        return $false
    }
    return $true
}

function Install-Tier {
    param([string]$RequirementsFile)
    if ($Offline) {
        return (Invoke-PipInstall -PipArgs @("--no-index", "--find-links", $WheelDir, "-r", $RequirementsFile))
    }
    return (Invoke-PipInstall -PipArgs @("-r", $RequirementsFile))
}

if (-not $Offline) {
    & $VenvPy -m pip install --quiet --no-cache-dir --upgrade pip 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Note: could not upgrade pip; continuing with the version already in the virtual environment."
    }
}

Write-Host "Installing the core packages ..."
if (-not (Install-Tier -RequirementsFile (Join-Path $Root "requirements\base.txt"))) { exit 1 }
Write-Host "Installed the core packages."

if ($WithDeck) {
    Write-Host "Installing the deck packages ..."
    if (-not (Install-Tier -RequirementsFile (Join-Path $Root "requirements\deck.txt"))) { exit 1 }
    Write-Host "Installed the deck packages."
}

# ---- self test --------------------------------------------------------------

Write-Host ""
Write-Host "Self test:"
$SelfTestFailed = $false

# The coverage and viewer tools include drafts here so the self test still
# proves the install works in a library where nothing is published yet.
function Invoke-SelfTest {
    param([string]$Name, [string[]]$ToolArgs)
    $out = (& $script:VenvPy @ToolArgs 2>&1) | Out-String
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ${Name}: ok"
        return $true
    }
    Write-Host "  ${Name}: FAILED"
    if ($out.Trim().Length -gt 0) { Write-Host $out }
    return $false
}

if (-not (Invoke-SelfTest -Name "tools/validate.py" -ToolArgs @((Join-Path $Root "tools\validate.py")))) { $SelfTestFailed = $true }
if (-not (Invoke-SelfTest -Name "tools/coverage.py" -ToolArgs @((Join-Path $Root "tools\coverage.py"), "--include-drafts"))) { $SelfTestFailed = $true }
if (-not (Invoke-SelfTest -Name "tools/build_viewer.py" -ToolArgs @((Join-Path $Root "tools\build_viewer.py"), "--include-drafts"))) { $SelfTestFailed = $true }

if ($SelfTestFailed) {
    Write-Host ""
    Write-Host "The install finished, but the self test failed; the output above says which tool broke and why."
    exit 1
}

# ---- done -------------------------------------------------------------------

Write-Host ""
Write-Host "Done. Next, run:"
Write-Host "  .\liszt doctor"
Write-Host "  .\liszt serve"
