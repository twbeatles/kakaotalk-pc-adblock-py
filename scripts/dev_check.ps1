param(
    [string]$PythonExe = "python",
    [switch]$SkipTests,
    [switch]$SkipRust,
    [switch]$SkipPython,
    [switch]$FixFmt
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$rustDir = Join-Path $repoRoot "rust"
$pytestBaseTemp = Join-Path $repoRoot ".pytest_tmp"

Push-Location $repoRoot
try {
    # 1. Rust checks matching CI (windows-ci.yml: rust-core)
    if (-not $SkipRust -and (Test-Path $rustDir)) {
        Push-Location $rustDir
        try {
            if ($FixFmt) {
                Write-Host "Formatting Rust codebase (cargo fmt --all)..."
                cargo fmt --all
            }
            Write-Host "Checking Rust formatting (cargo fmt --all -- --check)..."
            cargo fmt --all -- --check
            if ($LASTEXITCODE -ne 0) {
                throw "cargo fmt check failed. Run 'cargo fmt --all' or '.\scripts\dev_check.ps1 -FixFmt' to fix."
            }

            Write-Host "Running cargo clippy (--all-targets --all-features -- -D warnings)..."
            cargo clippy --all-targets --all-features -- -D warnings
            if ($LASTEXITCODE -ne 0) {
                throw "cargo clippy failed with exit code $LASTEXITCODE"
            }

            if ($SkipTests) {
                Write-Host "Skipping cargo test (-SkipTests)."
            } else {
                Write-Host "Running cargo test (--workspace)..."
                cargo test --workspace
                if ($LASTEXITCODE -ne 0) {
                    throw "cargo test failed with exit code $LASTEXITCODE"
                }
            }
        } finally {
            Pop-Location
        }
    }

    # 2. Python checks matching CI (windows-ci.yml: validate)
    if (-not $SkipPython) {
        $env:PYTHONPATH = Join-Path $repoRoot "legacy\python-v11"
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

Write-Host "All dev checks passed successfully!" -ForegroundColor Green
