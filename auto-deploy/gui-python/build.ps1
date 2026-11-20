param(
    [string]$Python = "",
    [string]$AssetsDirectory = ""
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$build = Join-Path $root "build"
$dist = Join-Path $root "dist"
$deploy = Join-Path $root "deploy"

if (-not $Python) {
    $candidates = @(
        (Join-Path (Split-Path (Split-Path $root -Parent) -Parent) ".venv-gui\Scripts\python.exe"),
        (Join-Path $root ".venv\Scripts\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $Python = $candidate
            break
        }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found. Create a venv and install requirements.txt, or pass -Python."
}

if (-not $AssetsDirectory) {
    $candidates = @(
        (Join-Path $root "assets")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate "SHA256SUMS")) {
            $AssetsDirectory = $candidate
            break
        }
    }
}
if (-not $AssetsDirectory -or -not (Test-Path -LiteralPath (Join-Path $AssetsDirectory "SHA256SUMS"))) {
    $projectRoot = Split-Path (Split-Path $root -Parent) -Parent
    $assetMap = [ordered]@{
        'post-init-modular-0.3.0.tar.gz' = 'tools/post-init/deploy/post-init-modular-0.3.0.tar.gz'
        'mi_gateway_2_openssh_deploy-0.3.0.tar.gz' = '1-openssh/deploy/mi_gateway_2_openssh_deploy-0.3.0.tar.gz'
        'mi_gateway_2_tun_deploy-0.3.0.tar.gz' = '2-tun-driver/deploy/mi_gateway_2_tun_deploy-0.3.0.tar.gz'
        'ble-spec-cache-0.3.0.tar.gz' = 'xiaomi_gateway3_patch/ble-spec-cache/deploy/ble-spec-cache-0.3.0.tar.gz'
        'rcp-native-0.3.0.tar.gz' = '3-rcp-mode/deploy/rcp-native-0.3.0.tar.gz'
        'rcp-mode-0.3.0.tar.gz' = '3-rcp-mode/deploy/rcp-mode-0.3.0.tar.gz'
        'rcp-openmiio-0.3.0.tar.gz' = '4-rcp-openmiio/deploy/rcp-openmiio-0.3.0.tar.gz'
        'mi-gw2-otbr-0.3.0.tar.gz' = '5-otbr/deploy/mi-gw2-otbr-0.3.0.tar.gz'
        'rcp-recovery-update-0.3.0.tar.gz' = '5-otbr/deploy/rcp-recovery-update-0.3.0.tar.gz'
        'spinel-probe-0.3.0' = '3-rcp-mode/deploy/tools/spinel-probe'
        'openmiio_agent-1.2.1-arm' = '4-rcp-openmiio/deploy/dependencies/openmiio_agent'
    }
    $missing = @($assetMap.Keys | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $assetMap[$_]) -PathType Leaf) })
    if ($missing.Count -eq 0) {
        $assetStage = Join-Path $build "assets-input"
        if (Test-Path -LiteralPath $assetStage) { Remove-Item -LiteralPath $assetStage -Recurse -Force }
        New-Item -ItemType Directory -Path $assetStage -Force | Out-Null
        $rows = @()
        foreach ($name in $assetMap.Keys) {
            $source = Join-Path $projectRoot $assetMap[$name]
            Copy-Item -LiteralPath $source -Destination (Join-Path $assetStage $name) -Force
            $rows += "$((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant())  $name"
        }
        [IO.File]::WriteAllLines(
            (Join-Path $assetStage "SHA256SUMS"),
            ($rows | Sort-Object),
            [Text.UTF8Encoding]::new($false)
        )
        $AssetsDirectory = $assetStage
    } else {
        throw "Component deploy assets missing: $($missing -join ', ')"
    }
}
if (-not $AssetsDirectory -or -not (Test-Path -LiteralPath (Join-Path $AssetsDirectory "SHA256SUMS"))) {
    throw "Assets directory not found. Pass -AssetsDirectory or ensure component deploy packages exist."
}

$AssetsDirectory = (Resolve-Path -LiteralPath $AssetsDirectory).ProviderPath
$env:MI_GW2_BUILD_ASSETS = $AssetsDirectory

& $Python -c "from PIL import Image; im=Image.open(r'$root\icon.png').convert('RGBA'); im.save(r'$root\app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $dist `
    --workpath $build `
    (Join-Path $root "MiGateway2AutoDeploy.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$exe = Join-Path $dist "MiGateway2AutoDeploy.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Expected executable was not created." }

New-Item -ItemType Directory -Path $deploy -Force | Out-Null
$target = Join-Path $deploy "MiGateway2AutoDeploy-0.3.0.exe"
Copy-Item -LiteralPath $exe -Destination $target -Force
$hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText(
    "$target.sha256",
    "$hash  $([IO.Path]::GetFileName($target))`n",
    [Text.UTF8Encoding]::new($false)
)
Write-Host "BUILD_PASS=$target"
Write-Host "SHA256=$hash"
