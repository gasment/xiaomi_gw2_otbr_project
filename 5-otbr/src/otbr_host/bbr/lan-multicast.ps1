param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$InterfaceIndex,
    [ValidateSet('send', 'receive')][string]$Mode = 'receive',
    [string]$Group = 'ff15::1234',
    [ValidateRange(1, 65535)][int]$Port = 18515,
    [ValidateRange(1, 50)][int]$Count = 10,
    [ValidateRange(1000, 60000)][int]$IntervalMs = 1000,
    [ValidateRange(5, 300)][int]$DurationSeconds = 90
)
$ErrorActionPreference = 'Stop'
$groupAddress = [System.Net.IPAddress]::Parse($Group)
if ($groupAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetworkV6 -or -not $groupAddress.IsIPv6Multicast) {
    throw 'Group must be IPv6 multicast.'
}
$scope = $groupAddress.GetAddressBytes()[1] -band 15
if ($scope -lt 4 -or $scope -gt 14) { throw 'Use multicast scope 4..14; ff03 is not forwarded across the BR.' }
$client = [System.Net.Sockets.UdpClient]::new([System.Net.Sockets.AddressFamily]::InterNetworkV6)
try {
    $client.Client.DualMode = $false
    $client.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IPv6, [System.Net.Sockets.SocketOptionName]::MulticastInterface, $InterfaceIndex)
    $client.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IPv6, [System.Net.Sockets.SocketOptionName]::MulticastTimeToLive, 16)
    if ($Mode -eq 'send') {
        $addresses = @(Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv6 | Where-Object {
            $_.AddressState -eq 'Preferred' -and -not $_.SkipAsSource -and
            -not ([System.Net.IPAddress]::Parse($_.IPAddress)).IsIPv6LinkLocal -and $_.IPAddress -ne '::1'
        })
        if ($addresses.Count -eq 0) { throw 'This LAN interface has no preferred non-link-local IPv6 source.' }
        $source = [System.Net.IPAddress]::Parse($addresses[0].IPAddress)
        $client.Client.Bind([System.Net.IPEndPoint]::new($source, 0))
        $target = [System.Net.IPEndPoint]::new($groupAddress, $Port)
        $session = [System.Guid]::NewGuid().ToString('N')
        for ($sequence = 1; $sequence -le $Count; $sequence++) {
            $text = "MI-BBR-TEST/1;source=lan;session=$session;seq=$sequence"
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
            [void]$client.Send($bytes, $bytes.Length, $target)
            Write-Output "TX source=$source group=$Group port=$Port payload=$text"
            if ($sequence -lt $Count) { Start-Sleep -Milliseconds $IntervalMs }
        }
        Write-Output 'LAN_SEND_FINISHED: verify corresponding RX lines on the ESP node; sending alone is not a pass.'
    } else {
        $client.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket, [System.Net.Sockets.SocketOptionName]::ReuseAddress, $true)
        $client.Client.Bind([System.Net.IPEndPoint]::new([System.Net.IPAddress]::IPv6Any, $Port))
        $client.JoinMulticastGroup($InterfaceIndex, $groupAddress)
        $client.Client.ReceiveTimeout = 1000
        $deadline = [System.DateTime]::UtcNow.AddSeconds($DurationSeconds)
        $received = 0
        Write-Output "LISTEN group=$Group port=$Port ifIndex=$InterfaceIndex duration=${DurationSeconds}s"
        while ([System.DateTime]::UtcNow -lt $deadline) {
            $peer = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::IPv6Any, 0)
            try { $bytes = $client.Receive([ref]$peer) }
            catch {
                $cause = $_.Exception
                while ($cause.InnerException) { $cause = $cause.InnerException }
                if ($cause -is [System.Net.Sockets.SocketException] -and $cause.SocketErrorCode -eq [System.Net.Sockets.SocketError]::TimedOut) { continue }
                throw
            }
            $text = [System.Text.Encoding]::UTF8.GetString($bytes)
            if ($text.StartsWith('MI-BBR-TEST/1;source=node;')) {
                $received++
                Write-Output "RX peer=$peer payload=$text"
            }
        }
        Write-Output "LAN_RECEIVE_FINISHED: node_datagrams=$received; compare session/sequence and gateway counters."
    }
} finally { $client.Close() }
