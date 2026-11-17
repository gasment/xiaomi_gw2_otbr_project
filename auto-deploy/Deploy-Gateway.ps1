[CmdletBinding()]
param(
    [string]$Gateway,
    [string]$ReleaseDirectory,
    [string]$Version,
    [string]$LocalAddress,
    [ValidateRange(1,65535)][int]$TelnetPort = 23,
    [ValidateRange(1024,65534)][int]$FtpPort = 2121,
    [ValidateRange(2,120)][int]$TimeoutMinutes = 20,
    [ValidateRange(1,30)][int]$ReconnectSeconds = 5,
    [switch]$TransportTest,
    [switch]$CheckOnly,
    [switch]$NoFirewallRule,
    [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
# Windows PowerShell started from PowerShell 7/cmd may inherit a module path
# without its own built-in modules. This changes only this process environment.
$builtinModules = Join-Path $PSHOME 'Modules'
$env:PSModulePath = $builtinModules + [IO.Path]::PathSeparator + $env:PSModulePath
function Get-Sha256([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $inputFile = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($inputFile)).Replace('-','').ToLowerInvariant() }
    finally { $inputFile.Dispose(); $algorithm.Dispose() }
}
if (-not ('MiGw2Deploy.TelnetSession' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'GatewayDeployNet.cs')
}
function Assert-Result($Result, [string]$Step) {
    if ($Result.Code -ne 0) { throw "$Step failed (gateway exit $($Result.Code)).`n$($Result.Output)" }
}
if ($SelfTest) {
    [MiGw2Deploy.ProtocolTests]::Telnet()
    Write-Host 'PASS: Telnet negotiation, root/blank login and echoed-marker rejection'
    $temp = Join-Path ([IO.Path]::GetTempPath()) ('gw2-ftp-test-' + [guid]::NewGuid().ToString('N'))
    $ftp = $null
    try {
        [IO.Directory]::CreateDirectory($temp) | Out-Null
        $fixture = Join-Path $temp 'fixture.bin'
        [IO.File]::WriteAllBytes($fixture, [Text.Encoding]::ASCII.GetBytes('verified FTP fixture'))
        $files = New-Object 'System.Collections.Generic.Dictionary[string,string]'
        $files.Add('fixture.bin', $fixture)
        $ftp = New-Object MiGw2Deploy.ReadOnlyFtp('127.0.0.1', 0, 0, 'self-test-only', $files)
        $ftp.Start()
        $request = [Net.FtpWebRequest]::Create(('ftp://127.0.0.1:{0}/fixture.bin' -f $ftp.Port))
        $request.Credentials = New-Object Net.NetworkCredential('deploy','self-test-only')
        $request.Method = [Net.WebRequestMethods+Ftp]::DownloadFile
        $request.UsePassive = $true; $request.UseBinary = $true; $request.Proxy = $null
        $response = $request.GetResponse()
        try {
            $memory = New-Object IO.MemoryStream
            $response.GetResponseStream().CopyTo($memory)
            if ([Text.Encoding]::ASCII.GetString($memory.ToArray()) -ne 'verified FTP fixture') { throw 'FTP content mismatch' }
        } finally { $response.Close() }
        Write-Host 'PASS: passive FTP authenticated binary download'
        $request = [Net.FtpWebRequest]::Create(('ftp://127.0.0.1:{0}/private.bin' -f $ftp.Port))
        $request.Credentials = New-Object Net.NetworkCredential('deploy','self-test-only')
        $request.Method = [Net.WebRequestMethods+Ftp]::DownloadFile; $request.Proxy = $null
        $denied = $false
        try { $unexpected = $request.GetResponse(); $unexpected.Close() } catch [Net.WebException] { $denied = $true }
        if (-not $denied) { throw 'FTP exposed an unlisted file' }
        Write-Host 'PASS: unlisted files denied'
        $mockBundle = Join-Path $temp 'mi-gw2-auto-deploy-0.2.0.tar.gz'
        [IO.File]::WriteAllText($mockBundle, 'not installed; reconnect test fixture')
        $mockHash = Get-Sha256 $mockBundle
        [IO.File]::WriteAllText(($mockBundle+'.sha256'), ($mockHash+'  mi-gw2-auto-deploy-0.2.0.tar.gz'))
        $mock = New-Object MiGw2Deploy.MockResumeGateway
        try {
            $mock.Start()
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Gateway 127.0.0.1 -TelnetPort $mock.Port -ReleaseDirectory $temp -Version 0.2.0 -NoFirewallRule -TimeoutMinutes 2 -ReconnectSeconds 1
            if ($LASTEXITCODE -ne 0 -or $mock.RebootCount -ne 1 -or $mock.ResumeCount -ne 1 -or $mock.VerifyCount -ne 1) { throw 'Reboot/reconnect continuation test failed' }
            Write-Host 'PASS: actual PowerShell controller reconnects and resumes after simulated reboot'
        } finally { $mock.Dispose() }
    } finally {
        if ($ftp) { $ftp.Dispose() }
        if ([IO.Directory]::Exists($temp)) { [IO.Directory]::Delete($temp, $true) }
    }
    Write-Host 'WINDOWS_DEPLOY_SELFTEST_PASS: loopback only; no gateway operation'
    exit 0
}
if ([string]::IsNullOrWhiteSpace($Gateway)) { $Gateway = Read-Host 'Gateway IPv4 address' }
$parsed = $null
if (-not [Net.IPAddress]::TryParse($Gateway, [ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { throw 'Gateway must be an IPv4 address' }
$Gateway = $parsed.ToString()
if ([string]::IsNullOrWhiteSpace($ReleaseDirectory)) {
    if (Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'mi-gw2-auto-deploy-*.tar.gz' -File) { $ReleaseDirectory = $PSScriptRoot }
    else { $ReleaseDirectory = Join-Path $PSScriptRoot '..\..\release' }
}
$ReleaseDirectory = (Resolve-Path -LiteralPath $ReleaseDirectory).ProviderPath
if ([string]::IsNullOrWhiteSpace($Version)) {
    $bundles = @(Get-ChildItem -LiteralPath $ReleaseDirectory -Filter 'mi-gw2-auto-deploy-*.tar.gz' -File)
    if ($bundles.Count -ne 1) { throw 'Specify -Version when zero or multiple full bundles exist' }
    $Version = [regex]::Match($bundles[0].Name, '^mi-gw2-auto-deploy-([0-9.]+)\.tar\.gz$').Groups[1].Value
}
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid release version' }
$name = 'mi-gw2-auto-deploy-' + $Version + '.tar.gz'
$bundle = Join-Path $ReleaseDirectory $name
$checksum = $bundle + '.sha256'
$expected = [IO.File]::ReadAllText($checksum).Trim()
if ($expected -notmatch ('^([0-9a-fA-F]{64})  ' + [regex]::Escape($name) + '$')) { throw 'Invalid bundle checksum file' }
$hash = $Matches[1].ToLowerInvariant()
if ((Get-Sha256 $bundle) -ne $hash) { throw 'Local release bundle checksum mismatch' }
$clock = [Diagnostics.Stopwatch]::StartNew()
$limit = $TimeoutMinutes * 60000
function Remaining-Milliseconds {
    $remaining = $limit - $clock.ElapsedMilliseconds
    if ($remaining -le 0) { throw 'Deployment time limit reached. Inspect gateway state before retrying.' }
    return [int][Math]::Min($remaining, [int]::MaxValue)
}
function New-GatewaySession {
    Write-Verbose "Opening Telnet $Gateway`:$TelnetPort"
    $s = New-Object MiGw2Deploy.TelnetSession
    $s.Open($Gateway, $TelnetPort, [Math]::Min(8000, (Remaining-Milliseconds)))
    return $s
}
function Invoke-Gateway($Session, [string]$Command, [int]$Maximum = 60000, [switch]$Live) {
    $callback = $null
    if ($Live) { $callback = [Action[string]] { param($chunk) Write-Host -NoNewline ([regex]::Replace($chunk, '(?m)^.*__GW2_[a-f0-9]+.*(?:\r?\n)?', '')) } }
    return $Session.Command($Command, [Math]::Min($Maximum, (Remaining-Milliseconds)), $callback)
}
$stateCommand = @'
printf '\n__GW2_STAGE='; cat /data/mi-gw2-auto/stage 2>/dev/null || echo absent
printf '\n__GW2_VERSION='; cat /data/mi-gw2-auto/VERSION 2>/dev/null || echo absent
printf '\n__GW2_NEED_REBOOT='
if [ -f /data/mi-gw2-auto/install-boot-id ] && [ "$(cat /data/mi-gw2-auto/install-boot-id)" = "$(cat /proc/sys/kernel/random/boot_id)" ]; then echo 1; else echo 0; fi
printf '__GW2_ACTIVE='
P=$(cat /tmp/mi-gw2-auto.lock/pid 2>/dev/null || :)
case "$P" in ''|*[!0-9]*) echo 0;; *) if kill -0 "$P" 2>/dev/null; then echo 1; else echo 0; fi;; esac
printf '__GW2_BOOT_READY='
if cmp -s /data/scripts/post_init.sh /data/rcp-mode/post_init.sh && cmp -s /bin/fw_manager.sh /data/rcp-mode/fw_manager.sh && cmp -s /bin/app_monitor.sh /data/rcp-mode/app_monitor.sh; then echo 1; else echo 0; fi
for D in /data/openssh /data/tun /data/rcp-mode /data/rcp-openmiio /data/otbr; do [ ! -e "$D" ] || printf '__GW2_EXISTING=%s\n' "$D"; done
'@
function Read-State($Session) {
    $result = Invoke-Gateway $Session $stateCommand
    Assert-Result $result 'Reading deployment state'
    $stage = [regex]::Match($result.Output, '(?m)^__GW2_STAGE=([^\r\n]+)').Groups[1].Value
    $v = [regex]::Match($result.Output, '(?m)^__GW2_VERSION=([^\r\n]+)').Groups[1].Value
    if (-not $stage) { throw 'Gateway deployment state was not readable' }
    return [pscustomobject]@{ Stage=$stage; Version=$v; Active=($result.Output -match '(?m)^__GW2_ACTIVE=1'); NeedReboot=($result.Output -match '(?m)^__GW2_NEED_REBOOT=1'); BootReady=($result.Output -match '(?m)^__GW2_BOOT_READY=1'); Existing=($result.Output -match '(?m)^__GW2_EXISTING=') }
}
function Reboot-Gateway($Session) {
    Write-Host 'RCP verified. Rebooting gateway; reconnecting within the time limit...'
    try { $r = Invoke-Gateway $Session 'sync; reboot' 15000; Assert-Result $r 'Reboot' } catch [IO.IOException] { } catch [TimeoutException] { }
    $Session.Dispose()
}
$session = $null; $ftp = $null; $firewallName = $null
try {
    Write-Host "Connecting to $Gateway (Telnet $TelnetPort), release $Version..."
    while (-not $session) {
        try { $session = New-GatewaySession }
        catch {
            if ($_.Exception.Message -match 'blank-password.*rejected') { throw }
            $null = Remaining-Milliseconds
            Write-Host 'Waiting for initial Telnet connection...'
            Start-Sleep -Seconds $ReconnectSeconds
        }
    }
    $state = Read-State $session
    if ($state.Stage -ne 'absent' -and $state.Version -ne $Version) { throw 'Existing journal has another version; no automatic change' }
    if ($state.Stage -eq 'absent' -and $state.Existing -and -not ($TransportTest -or $CheckOnly)) { throw 'Gateway already has project components. First-install automation blocked; use manual upgrade.' }
    $needsTransfer = $TransportTest -or $CheckOnly -or ($state.Stage -in @('absent','new','ssh','tun') -and -not $state.Active)
    if ($needsTransfer) {
        if (-not $NoFirewallRule) {
            $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
            $admin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
            if (-not $admin) {
                $session.Dispose(); $session = $null
                Write-Host 'Requesting administrator rights for two temporary FTP firewall ports, scoped to this gateway.'
                $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File', ('"' + $PSCommandPath + '"'), '-Gateway', $Gateway, '-ReleaseDirectory', ('"' + $ReleaseDirectory + '"'), '-Version', $Version, '-TelnetPort', $TelnetPort, '-FtpPort', $FtpPort, '-TimeoutMinutes', $TimeoutMinutes, '-ReconnectSeconds', $ReconnectSeconds)
                if ($LocalAddress) { $arguments += @('-LocalAddress',$LocalAddress) }
                if ($TransportTest) { $arguments += '-TransportTest' }
                if ($CheckOnly) { $arguments += '-CheckOnly' }
                # This is the interactive deployment console, not a hidden helper.
                $process = Start-Process -FilePath powershell.exe -Verb RunAs -ArgumentList ($arguments -join ' ') -WindowStyle Normal -Wait -PassThru
                exit $process.ExitCode
            }
        }
        if (-not $LocalAddress) {
            $route = New-Object Net.Sockets.UdpClient
            try { $route.Connect($Gateway, $TelnetPort); $LocalAddress = $route.Client.LocalEndPoint.Address.ToString() } finally { $route.Dispose() }
        }
        $localIP = $null
        if (-not [Net.IPAddress]::TryParse($LocalAddress, [ref]$localIP) -or $localIP.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or $localIP.Equals([Net.IPAddress]::Any)) { throw 'LocalAddress must be a concrete local IPv4 address' }
        $LocalAddress = $localIP.ToString()
        if (-not $NoFirewallRule) {
            $firewallName = 'MiGW2-Deploy-' + [guid]::NewGuid().ToString('N')
            New-NetFirewallRule -Name $firewallName -DisplayName 'Xiaomi GW2 temporary deployment FTP' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $LocalAddress -LocalPort @($FtpPort,($FtpPort+1)) -RemoteAddress $Gateway -Profile Any | Out-Null
        }
        $secret = [guid]::NewGuid().ToString('N')
        $files = New-Object 'System.Collections.Generic.Dictionary[string,string]'
        $files.Add($name,$bundle); $files.Add(($name+'.sha256'),$checksum)
        $ftp = New-Object MiGw2Deploy.ReadOnlyFtp($LocalAddress,$FtpPort,($FtpPort+1),$secret,$files)
        $ftp.Start()
        Write-Host "Temporary read-only FTP ready on $LocalAddress`:$FtpPort. Sending verified bundle..."
        $url = 'ftp://deploy:' + $secret + '@' + $LocalAddress + ':' + $FtpPort + '/' + $name
        $fetch = "umask 077; mkdir -p /tmp/mi-gw2-pc-deploy && cd /tmp/mi-gw2-pc-deploy && wget -T 30 -O $name.part '$url' && mv $name.part $name && printf '%s  %s\n' '$hash' '$name' | sha256sum -c -"
        $result = Invoke-Gateway $session $fetch 180000
        if ($result.Code -ne 0) { throw ('FTP download/checksum failed. Check the selected NIC/firewall.' + "`n" + $result.Output.Replace($secret,'[temporary-password]')) }
        Write-Host 'Gateway FTP download and SHA256 verification passed.'
        if ($TransportTest) { Write-Host 'TRANSPORT_TEST_PASS: Telnet, real FTP pull and checksum; no install, UART or reboot.'; exit 0 }
        $extract = "tar -xzf /tmp/mi-gw2-pc-deploy/$name -C /tmp"
        if ($state.Stage -eq 'absent' -or $CheckOnly) { $extract += ' && sh /tmp/mi-gw2-auto-deploy/install.sh check' }
        $result = Invoke-Gateway $session $extract 120000 -Live
        Assert-Result $result 'Gateway preflight'
        if ($CheckOnly) { Write-Host 'CHECK_ONLY_PASS: no install or radio operation.'; exit 0 }
        Write-Host 'Installing in order. RCP flash is part of this first-install operation...'
        $result = Invoke-Gateway $session 'sh /tmp/mi-gw2-auto-deploy/install.sh install --no-reboot' (Remaining-Milliseconds) -Live
        Assert-Result $result 'Pre-reboot installation'
        $state = Read-State $session
        if ($state.Stage -ne 'waiting-reboot') { throw 'Expected waiting-reboot journal; no automatic reflash' }
        Reboot-Gateway $session; $session = $null
    }
    $lastStage = ''
    while ((Remaining-Milliseconds) -gt 0) {
        if (-not $session) {
            try { $session = New-GatewaySession }
            catch { Write-Host ('Waiting for Telnet after reboot: ' + $_.Exception.Message); Start-Sleep -Seconds $ReconnectSeconds; continue }
        }
        try { $state = Read-State $session }
        catch { $session.Dispose(); $session = $null; Start-Sleep -Seconds $ReconnectSeconds; continue }
        if ($state.Version -ne $Version) { throw 'Journal version changed; stopped' }
        if ($state.Stage -ne $lastStage) { Write-Host ('Gateway stage: ' + $state.Stage); $lastStage = $state.Stage }
        if ($state.Stage -eq 'complete') {
            $result = Invoke-Gateway $session 'sh /data/mi-gw2-auto/install.sh verify' 60000 -Live
            Assert-Result $result 'Final verification'
            Write-Host 'DEPLOYMENT_COMPLETE: component files and boot chain verified.'
            Write-Host 'Edit /data/otbr/config.yaml, then run check.sh and restart.sh. Re-enable the HA gateway entry.'
            break
        }
        if ($state.Stage -eq 'waiting-reboot' -and $state.NeedReboot -and -not $state.Active) {
            Reboot-Gateway $session; $session = $null; Start-Sleep -Seconds $ReconnectSeconds; continue
        }
        if (-not $state.Active) {
            if ($state.Stage -eq 'radio-in-progress') { throw 'Radio operation interrupted. Automatic reflash prohibited; inspect native recovery.' }
            if ($state.Stage -in @('waiting-reboot','ble','host')) {
                if ($state.Stage -eq 'waiting-reboot' -and -not $state.BootReady) {
                    Write-Host 'Waiting for the RCP startup isolation to become ready...'
                    Start-Sleep -Seconds $ReconnectSeconds
                    continue
                }
                Write-Host 'Continuing an idle post-reboot stage...'
                $result = Invoke-Gateway $session 'sh /data/mi-gw2-auto/install.sh resume' (Remaining-Milliseconds) -Live
                if ($result.Code -ne 0) {
                    $nextState = Read-State $session
                    if ($nextState.Active) { Write-Host 'The gateway boot hook already started continuation; following its progress...'; continue }
                }
                Assert-Result $result 'Continuation'
                continue
            }
            throw ('Stopped at ' + $state.Stage + '; inspect /data/mi-gw2-auto/last-step.log. No automatic reflash.')
        }
        Start-Sleep -Seconds $ReconnectSeconds
    }
} finally {
    if ($session) { $session.Dispose() }
    if ($ftp) { $ftp.Dispose() }
    if ($firewallName) { Remove-NetFirewallRule -Name $firewallName -ErrorAction SilentlyContinue }
}
