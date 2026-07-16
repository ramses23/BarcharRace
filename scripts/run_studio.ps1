[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$CheckOnly,
    [switch]$SkipDoctor,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$StreamlitArgs
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RootDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsFile = Join-Path $RootDir "requirements.txt"
$DoctorScript = Join-Path $RootDir "src\tools\doctor.py"
$StudioScript = Join-Path $RootDir "src\ui\project_studio.py"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    if (-not $Setup) {
        Write-Error (
            "The project virtual environment does not exist. " +
            "Run scripts\run_studio.ps1 -Setup once."
        )
        exit 1
    }

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $PyLauncher) {
        Write-Error "Python launcher 'py' was not found. Install Python 3.13 first."
        exit 1
    }

    Write-Host "Creating .venv with Python 3.13..."
    & $PyLauncher.Source -3.13 -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Setup) {
    Write-Host "Installing the locked dependencies..."
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonExe -m pip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $SkipDoctor) {
    & $PythonExe $DoctorScript
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Environment checks failed. Resolve the errors above before starting Studio."
        exit $LASTEXITCODE
    }
}

if ($CheckOnly) {
    Write-Host "BarChartStudio is ready."
    exit 0
}

Set-Location -LiteralPath $RootDir
& $PythonExe -m streamlit run $StudioScript @StreamlitArgs
exit $LASTEXITCODE
