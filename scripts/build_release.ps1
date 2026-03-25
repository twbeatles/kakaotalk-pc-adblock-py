param(
    [string]$PythonExe = "python",
    [string]$SpecPath = "kakaotalk_adblock.spec",
    [string]$ExeName = "KakaoTalkLayoutAdBlocker_v11.exe",
    [string]$DistDir = "dist",
    [string]$WorkDir = "build",
    [switch]$NoSign,
    [switch]$SkipSmokeCheck
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resolvedSpec = Resolve-Path (Join-Path $repoRoot $SpecPath)

function Get-SigningConfig {
    $signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if (-not $signtool) {
        throw "signtool.exe not found. Install Windows SDK Signing Tools, or run with -NoSign."
    }

    $args = @("sign", "/fd", "SHA256")

    if ($env:SIGN_PFX_PATH) {
        if (-not (Test-Path $env:SIGN_PFX_PATH)) {
            throw "SIGN_PFX_PATH not found: $($env:SIGN_PFX_PATH)"
        }
        $args += @("/f", $env:SIGN_PFX_PATH)
        if ($env:SIGN_PFX_PASSWORD) {
            $args += @("/p", $env:SIGN_PFX_PASSWORD)
        }
    } elseif ($env:SIGN_CERT_SHA1) {
        $args += @("/sha1", $env:SIGN_CERT_SHA1)
        if ($env:SIGN_CERT_STORE) {
            $args += @("/s", $env:SIGN_CERT_STORE)
        }
        if ($env:SIGN_CERT_SUBJECT) {
            $args += @("/n", $env:SIGN_CERT_SUBJECT)
        }
    } else {
        throw "Signing configuration missing. Set SIGN_PFX_PATH (and optional SIGN_PFX_PASSWORD) or SIGN_CERT_SHA1."
    }

    $timestampUrl = if ($env:SIGN_TIMESTAMP_URL) { $env:SIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }
    $args += @("/tr", $timestampUrl, "/td", "SHA256")
    return [PSCustomObject]@{
        SignTool = $signtool.Source
        SignArgs = $args
    }
}

function Invoke-Sign {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath,
        [Parameter(Mandatory = $true)]
        [PSCustomObject]$SigningConfig
    )
    Write-Host "Signing $ExePath"
    $signArgs = @($SigningConfig.SignArgs + $ExePath)
    & $SigningConfig.SignTool @signArgs
    if ($LASTEXITCODE -ne 0) {
        throw "signtool sign failed with exit code $LASTEXITCODE"
    }

    & $SigningConfig.SignTool verify /pa /v $ExePath
    if ($LASTEXITCODE -ne 0) {
        throw "signtool verify failed with exit code $LASTEXITCODE"
    }
}

function New-TempDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )
    $path = Join-Path ([System.IO.Path]::GetTempPath()) ("{0}-{1}" -f $Prefix, [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return $path
}

function Remove-TempDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (-not (Test-Path $Path)) {
        return
    }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force
    } catch {
        Write-Warning "Failed to clean temp dir ${Path}: $($_.Exception.Message)"
    }
}

function Test-InteractiveShell {
    if ($env:CI) {
        return $false
    }
    try {
        return [Environment]::UserInteractive -and ((Get-Process -Id $PID).SessionId -gt 0)
    } catch {
        return $false
    }
}

function Invoke-PackagedSelfCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath
    )

    $tempAppData = New-TempDir -Prefix "ktalb-smoke-appdata"
    $reportPath = Join-Path $tempAppData "self-check.json"
    $previousAppData = $env:APPDATA
    try {
        $env:APPDATA = $tempAppData
        Write-Host "Running packaged smoke check (--self-check --json): $ExePath"
        $proc = Start-Process `
            -FilePath $ExePath `
            -ArgumentList @("--self-check", "--json", "--self-check-report", $reportPath) `
            -PassThru `
            -WindowStyle Hidden
        if (-not $proc.WaitForExit(60000)) {
            try {
                $proc.Kill()
            } catch {
            }
            throw "packaged --self-check timed out"
        }
        $exitCode = $proc.ExitCode
    } finally {
        $env:APPDATA = $previousAppData
    }

    if (-not (Test-Path $reportPath)) {
        throw "packaged --self-check did not produce JSON report: $reportPath"
    }
    try {
        $result = Get-Content $reportPath -Raw | ConvertFrom-Json
        if ($null -eq $result.summary) {
            throw "packaged --self-check JSON summary missing"
        }
        if ([int]$result.summary.exit_code -ne 0 -or $exitCode -ne 0) {
            throw "packaged --self-check failed (exit_code=$($result.summary.exit_code), process_exit=$exitCode)"
        }
        if ([int]$result.summary.optional_failed -gt 0) {
            Write-Warning "Optional self-check failures detected: $($result.summary.optional_failed)"
        }
    } finally {
        Remove-TempDir -Path $tempAppData
    }
}

function Invoke-StartupSmoke {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath
    )

    if (-not (Test-InteractiveShell)) {
        return [PSCustomObject]@{
            status = "skipped"
            reason = "interactive shell not detected"
        }
    }

    $tempAppData = New-TempDir -Prefix "ktalb-startup-appdata"
    $tracePath = Join-Path $tempAppData "startup-trace.json"
    $previousAppData = $env:APPDATA
    try {
        $env:APPDATA = $tempAppData
        Write-Host "Running packaged startup smoke (--startup-launch --minimized)..."
        $proc = Start-Process `
            -FilePath $ExePath `
            -ArgumentList @("--startup-launch", "--minimized", "--startup-trace", $tracePath, "--exit-after-startup-ms", "1500") `
            -PassThru `
            -Wait `
            -WindowStyle Hidden
    } finally {
        $env:APPDATA = $previousAppData
    }
    try {
        if ($proc.ExitCode -ne 0) {
            throw "packaged startup smoke failed with exit code $($proc.ExitCode)"
        }
        if (-not (Test-Path $tracePath)) {
            throw "packaged startup smoke did not produce startup trace: $tracePath"
        }

        $trace = Get-Content $tracePath -Raw | ConvertFrom-Json
        if (-not $trace.startup_launch) {
            throw "startup trace did not record startup_launch=true"
        }
        if (-not $trace.shell_wait_attempted) {
            throw "startup trace did not record shell wait"
        }
        if (-not $trace.tray_available) {
            Write-Warning "Startup smoke completed but tray was unavailable on this host."
        } elseif ($trace.tray_start_error) {
            Write-Warning "Startup smoke completed with tray warning: $($trace.tray_start_error)"
        }
        return [PSCustomObject]@{
            status = "completed"
            reason = ""
        }
    } finally {
        Remove-TempDir -Path $tempAppData
    }
}

Push-Location $repoRoot
try {
    $signingConfig = $null
    if (-not $NoSign) {
        # Fail fast before build when signing prerequisites are missing.
        $signingConfig = Get-SigningConfig
    }

    Write-Host "Building with PyInstaller spec: $resolvedSpec"
    & $PythonExe -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $WorkDir $resolvedSpec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE"
    }

    $exePath = Join-Path $repoRoot (Join-Path $DistDir $ExeName)
    if (-not (Test-Path $exePath)) {
        throw "Built EXE not found: $exePath"
    }

    if ($SkipSmokeCheck) {
        Write-Host "Skipping packaged smoke check (-SkipSmokeCheck)."
    } else {
        Invoke-PackagedSelfCheck -ExePath $exePath
        $startupSmoke = Invoke-StartupSmoke -ExePath $exePath
        Write-Host "Startup smoke status: $($startupSmoke.status)"
        if ($startupSmoke.reason) {
            Write-Host "Startup smoke detail: $($startupSmoke.reason)"
        }
    }

    if ($NoSign) {
        Write-Host "Skipping code signing (-NoSign)."
    } else {
        Invoke-Sign -ExePath $exePath -SigningConfig $signingConfig
    }

    Write-Host "Done: $exePath"
} finally {
    Pop-Location
}
