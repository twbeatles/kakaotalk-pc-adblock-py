param(
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

function Invoke-SmokeCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath
    )

    Write-Host "Running packaged smoke check (--self-check): $ExePath"
    $proc = Start-Process -FilePath $ExePath -ArgumentList @("--self-check") -PassThru -Wait -WindowStyle Hidden
    if ($proc.ExitCode -ne 0) {
        throw "packaged --self-check failed with exit code $($proc.ExitCode)"
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
    python -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $WorkDir $resolvedSpec
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
        Invoke-SmokeCheck -ExePath $exePath
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
