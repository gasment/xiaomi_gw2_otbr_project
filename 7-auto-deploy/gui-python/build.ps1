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
    $siblingAssets = Join-Path $root "assets"
    if (Test-Path -LiteralPath (Join-Path $siblingAssets "SHA256SUMS")) {
        $AssetsDirectory = $siblingAssets
    } else {
        $AssetsDirectory = Join-Path $build ("assets-input-" + [Guid]::NewGuid().ToString("N"))
        & $Python (Join-Path $root "resources.py") stage $AssetsDirectory
        if ($LASTEXITCODE -ne 0) { throw "Component asset staging failed." }
    }
}
& $Python (Join-Path $root "resources.py") check $AssetsDirectory
if ($LASTEXITCODE -ne 0) { throw "Component asset verification failed." }

$guiVersion = (Get-Content -Raw -LiteralPath (Join-Path $root "VERSION")).Trim()
if ($guiVersion -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
    throw "Invalid GUI VERSION."
}
$versionParts = $guiVersion.Split(".")
if (@($versionParts | Where-Object { [int]$_ -gt 65535 }).Count -ne 0) {
    throw "GUI VERSION exceeds Windows version resource limits."
}
New-Item -ItemType Directory -Path $build -Force | Out-Null
$env:MI_GW2_BUILD_VERSION_INFO = Join-Path $build "version_info.txt"
$versionInfo = Get-Content -Raw -LiteralPath (Join-Path $root "version_info.txt")
$versionInfo = $versionInfo.Replace("@GUI_VERSION@", $guiVersion).Replace("@GUI_VERSION_TUPLE@", ($versionParts -join ", ") + ", 0")
[IO.File]::WriteAllText($env:MI_GW2_BUILD_VERSION_INFO, $versionInfo, [Text.UTF8Encoding]::new($false))

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
$target = Join-Path $deploy "MiGateway2AutoDeploy-$guiVersion.exe"
Copy-Item -LiteralPath $exe -Destination $target -Force
$hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText(
    "$target.sha256",
    "$hash  $([IO.Path]::GetFileName($target))`n",
    [Text.UTF8Encoding]::new($false)
)
Write-Host "BUILD_PASS=$target"
Write-Host "SHA256=$hash"
