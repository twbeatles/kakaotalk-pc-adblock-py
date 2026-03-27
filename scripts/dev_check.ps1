param(
    [string]$PythonExe = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pytestBaseTemp = Join-Path $repoRoot ".pytest_tmp"

Push-Location $repoRoot
try {
    Write-Host "Running pyright..."
    & $PythonExe -m pyright
    if ($LASTEXITCODE -ne 0) {
        throw "pyright failed with exit code $LASTEXITCODE"
    }

    if ($SkipTests) {
        Write-Host "Skipping pytest (-SkipTests)."
    } else {
        Write-Host "Running pytest -q --basetemp .pytest_tmp..."
        & $PythonExe -m pytest -q --basetemp .pytest_tmp
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed with exit code $LASTEXITCODE"
        }
    }
} finally {
    if (Test-Path $pytestBaseTemp) {
        try {
            Remove-Item -Recurse -Force $pytestBaseTemp
        } catch {
            Write-Warning "Failed to clean ${pytestBaseTemp}: $($_.Exception.Message)"
        }
    }
    Pop-Location
}
