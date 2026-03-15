param(
    [string]$PythonExe = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

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
        Write-Host "Running pytest -q..."
        & $PythonExe -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed with exit code $LASTEXITCODE"
        }
    }
} finally {
    Pop-Location
}
