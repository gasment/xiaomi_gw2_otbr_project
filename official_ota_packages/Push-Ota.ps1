param(
    [Parameter(Mandatory=$true)][string]$Gateway,
    [Parameter(Mandatory=$true)][string]$Package,
    [ValidateRange(1,65535)][int]$Port=23,
    [switch]$UploadOnly
)
$ErrorActionPreference='Stop'
if(-not ('MiGw2ManualOta.TelnetSession' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Diagnostics;

namespace MiGw2ManualOta {
 public sealed class CommandResult { public int Code; public string Output; }
 public sealed class TelnetSession : IDisposable {
  TcpClient client; NetworkStream stream; int state; int verb;
  Decoder decoder = Encoding.UTF8.GetDecoder();
  public bool Connected { get { return client != null && client.Connected; } }
  void Send(string line) { byte[] b=Encoding.UTF8.GetBytes(line+"\r\n"); stream.Write(b,0,b.Length); }
  string Read(int milliseconds) {
   Stopwatch watch=Stopwatch.StartNew();
   while (watch.ElapsedMilliseconds < milliseconds) {
    if (client.Available > 0) {
     byte[] raw=new byte[8192]; int n=stream.Read(raw,0,raw.Length);
     if(n==0) throw new IOException("Telnet disconnected");
     List<byte> plain=new List<byte>();
     for(int i=0;i<n;i++) {
      byte b=raw[i];
      if(state==0) { if(b==255) state=1; else if(b!=0) plain.Add(b); }
      else if(state==1) {
       if(b==255) { plain.Add(b); state=0; }
       else if(b==251 || b==252 || b==253 || b==254) { verb=b; state=2; }
       else if(b==250) state=3; else state=0;
      } else if(state==2) {
       if(verb==251 || verb==253) {
        byte[] response={255,(byte)(verb==251?254:252),b}; stream.Write(response,0,3);
       }
       state=0;
      } else if(state==3) { if(b==255) state=4; }
      else if(state==4) { state=b==240?0:3; }
     }
     byte[] bytes=plain.ToArray(); char[] chars=new char[Encoding.UTF8.GetMaxCharCount(bytes.Length)];
     int length=decoder.GetChars(bytes,0,bytes.Length,chars,0,false);
     return new string(chars,0,length);
    }
    if(client.Client.Poll(0,SelectMode.SelectRead) && client.Available==0) throw new IOException("Telnet disconnected");
    Thread.Sleep(20);
   }
   return "";
  }
  public void Open(string address,int port,int timeout) {
   client=new TcpClient();
   try {
    var pending=client.ConnectAsync(address,port);
    if(!pending.Wait(timeout)) throw new TimeoutException("Telnet connect timeout");
    pending.GetAwaiter().GetResult(); client.NoDelay=true; stream=client.GetStream();
    Stopwatch watch=Stopwatch.StartNew(); StringBuilder text=new StringBuilder(); int login=0;
    while(watch.ElapsedMilliseconds < timeout) {
     text.Append(Read(300)); string value=text.ToString();
     if(Regex.IsMatch(value,@"(?:^|[\r\n])[^\r\n]*[#$]\s*$")) return;
     if(login==0 && Regex.IsMatch(value,@"login:\s*$",RegexOptions.IgnoreCase)) { Send("root"); login=1; text.Clear(); }
     else if(login<=1 && Regex.IsMatch(value,@"password:\s*$",RegexOptions.IgnoreCase)) { Send(""); login=2; text.Clear(); }
     if(Regex.IsMatch(value,@"login incorrect|authentication failed",RegexOptions.IgnoreCase)) throw new IOException("Root blank-password Telnet login was rejected");
    }
    throw new TimeoutException("Telnet login timeout");
   } catch { Dispose(); throw; }
  }
  public CommandResult Command(string command,int timeout,Action<string> progress) {
   string token="__GW2_"+Guid.NewGuid().ToString("N");
   Send(command); Send("printf '\\n"+token+":%s\\n' \"$?\"");
   Regex marker=new Regex(@"(?:^|[\r\n])"+token+@":([0-9]+)(?:\r?\n)");
   Stopwatch watch=Stopwatch.StartNew(); StringBuilder text=new StringBuilder();
   while(watch.ElapsedMilliseconds < timeout) {
    string chunk=Read(400); if(chunk.Length==0) continue;
    text.Append(chunk); if(progress!=null) progress(chunk);
    Match match=marker.Match(text.ToString());
    if(match.Success) return new CommandResult { Code=int.Parse(match.Groups[1].Value), Output=text.ToString() };
    if(text.Length>4*1024*1024) text.Remove(0,2*1024*1024);
   }
   throw new TimeoutException("Gateway command timed out");
  }
  public void Dispose() { if(stream!=null) stream.Dispose(); if(client!=null) client.Close(); stream=null; client=null; }
 }
}
'@
}
function Run([string]$Command,[int]$Timeout=30000) {
    $r=$script:Session.Command($Command,$Timeout,$null)
    if($r.Code -ne 0) {throw "Gateway command failed ($($r.Code)):`n$($r.Output)"}
    return $r.Output
}
function Field([string]$Text,[string]$Name) {
    $m=[regex]::Match($Text,'(?m)^'+[regex]::Escape($Name)+'=([^\r\n]*)')
    if(-not $m.Success) {throw "Missing gateway result: $Name"}
    return $m.Groups[1].Value.Trim()
}
$file=Get-Item -LiteralPath $Package
if($file.PSIsContainer -or $file.Length -lt 4) {throw 'Select an original MIOT .bin package.'}
$inputStream=[IO.File]::OpenRead($file.FullName)
try {$magic=New-Object byte[] 4;[void]$inputStream.Read($magic,0,4)} finally {$inputStream.Dispose()}
if([Text.Encoding]::ASCII.GetString($magic) -ne 'MIOT') {throw 'Not a MIOT package. Partition images and GBL files are not accepted.'}
$md5=(Get-FileHash -LiteralPath $file.FullName -Algorithm MD5).Hash.ToLowerInvariant()
$size=[long]$file.Length
$remote='/data/firmware/firmware_ota.bin'
$partial='/data/firmware/manual_ota.uploading'
$script:Session=New-Object MiGw2ManualOta.TelnetSession
$echoOff=$false
try {
    Write-Host "Connecting to $Gateway`:$Port (root, empty password)..."
    $script:Session.Open($Gateway,$Port,10000)
    $probe=Run @'
( test "$(id -u)" = 0 || exit 1
command -v base64 >/dev/null || exit 1
command -v md5sum >/dev/null || exit 1
command -v stty >/dev/null || exit 1
model=$(agetprop ro.sys.model)
case "$model" in lumi.gateway.mcn001) ;; *) echo "Unsupported model: $model"; exit 1 ;; esac
[ -x /bin/fw_manager.sh ] || exit 1
if ps | grep -E '[f]w_manager.*-u|[f]w_miot_unpack|[n]andwrite|[f]lash_erase' >/dev/null; then echo 'Updater already running'; exit 1; fi
mkdir -p /data/firmware || exit 1
printf 'MODEL=%s\n' "$model"
printf 'VERSION=%s_%s\n' "$(agetprop ro.sys.mi_fw_ver)" "$(agetprop ro.sys.mi_build_num)"
printf 'FREE_KIB=%s\n' "$(df -k /data | tail -n 1 | awk '{print $4}')"
printf 'TMP_FREE_KIB=%s\n' "$(df -k /tmp | tail -n 1 | awk '{print $4}')"
printf 'MEM_AVAILABLE_KIB=%s\n' "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
if [ -f /data/firmware/firmware_ota.bin ]; then printf 'EXISTING_MD5=%s\n' "$(md5sum /data/firmware/firmware_ota.bin | awk '{print $1}')"; else echo EXISTING_MD5=none; fi
if [ -f /tmp/mi-gw2-manual-ota/firmware_ota.bin ]; then printf 'TMP_EXISTING_MD5=%s\n' "$(md5sum /tmp/mi-gw2-manual-ota/firmware_ota.bin | awk '{print $1}')"; else echo TMP_EXISTING_MD5=none; fi
if [ -d /data/rcp-mode ] || [ -d /data/otbr ]; then echo MODIFIED=1; else echo MODIFIED=0; fi
)
'@
    Write-Host "Gateway: $(Field $probe 'MODEL')  $(Field $probe 'VERSION')"
    if(-not $UploadOnly -and (Field $probe 'MODIFIED') -eq '1') {
        Write-Warning 'OTBR/RCP components detected. Stock OTA can change the kernel, invalidate tun.ko and startup isolation, and may update the radio firmware. This tool does not migrate or repair those components.'
        $confirmation=Read-Host 'Continue OTA on this OTBR/RCP gateway? Type YES to confirm; anything else cancels'
        if($confirmation -cne 'YES') {throw 'OTA cancelled. No package uploaded and no installer started.'}
    }
    $same=(Field $probe 'EXISTING_MD5') -eq $md5
    $kib=[long][Math]::Ceiling($size/1024.0)
    $required=1024L
    if(-not $same) {$required+=$kib}
    if(-not $UploadOnly) {$required+=$kib}
    $free=[long](Field $probe 'FREE_KIB')
    $tmpRequired=8192L
    if(-not $UploadOnly) {$tmpRequired+=$kib}
    if($free -lt $required) {
        # The installer still requires one package-sized free area in /data.
        $dataRequired=1024L
        if(-not $UploadOnly) {$dataRequired+=$kib}
        if($free -lt $dataRequired) {throw "Insufficient /data unpack space: free=$free KiB; required=$dataRequired KiB. Existing files were not deleted."}
        $remote='/tmp/mi-gw2-manual-ota/firmware_ota.bin'
        $partial='/tmp/mi-gw2-manual-ota/manual_ota.uploading'
        $same=(Field $probe 'TMP_EXISTING_MD5') -eq $md5
        if(-not $same) {$tmpRequired+=$kib}
        Write-Host 'Using /tmp staging: /data cannot hold both upload and unpack space.'
    }
    if(-not $UploadOnly -or $remote.StartsWith('/tmp/')) {
        $tmpFree=[long](Field $probe 'TMP_FREE_KIB')
        $memAvailable=[long](Field $probe 'MEM_AVAILABLE_KIB')
        if($tmpFree -lt $tmpRequired -or $memAvailable -lt $tmpRequired) {
            throw "Insufficient temporary capacity: /tmp free=$tmpFree KiB; MemAvailable=$memAvailable KiB; required=$tmpRequired KiB. No installer started."
        }
    }
    Write-Host "Package staging path: $remote"
    if($same) {
        Write-Host 'Identical package already on gateway; reusing verified copy.'
    } else {
        $directory=$remote.Substring(0,$remote.LastIndexOf('/'))
        [void](Run "mkdir -p $directory && test ! -e $partial && : > $partial")
        [void](Run 'stty -echo');$echoOff=$true
        $inputStream=[IO.File]::OpenRead($file.FullName)
        try {
            $buffer=New-Object byte[] 49152
            $sent=0L
            while(($count=$inputStream.Read($buffer,0,$buffer.Length)) -gt 0) {
                $b64=[Convert]::ToBase64String($buffer,0,$count)
                $body=([regex]::Matches($b64,'.{1,768}') | ForEach-Object {$_.Value}) -join "`n"
                $tag='GW2_'+[Guid]::NewGuid().ToString('N')
                $command="base64 -d >> $partial <<'$tag'`n$body`n$tag"
                [void](Run $command 60000)
                $sent+=$count
                Write-Progress -Activity 'Uploading MIOT through Telnet' -Status "$sent / $size bytes" -PercentComplete ([int](100*$sent/$size))
            }
        } finally {$inputStream.Dispose()}
        [void](Run 'stty echo');$echoOff=$false
        Write-Progress -Activity 'Uploading MIOT through Telnet' -Completed
        $verify=Run "printf 'UPLOAD_MD5=%s\n' `"`$(md5sum $partial | awk '{print `$1}')`"; printf 'UPLOAD_SIZE=%s\n' `"`$(wc -c < $partial)`""
        if((Field $verify 'UPLOAD_MD5') -ne $md5 -or [long](Field $verify 'UPLOAD_SIZE') -ne $size) {
            throw "Upload verification failed. Partial file retained at $partial; no installation started."
        }
        [void](Run "mv -f $partial $remote")
    }
    $verify=Run "printf 'FINAL_MD5=%s\n' `"`$(md5sum $remote | awk '{print `$1}')`""
    if((Field $verify 'FINAL_MD5') -ne $md5) {throw 'Final package MD5 mismatch; no installation started.'}
    Write-Host "PACKAGE_VERIFIED bytes=$size MD5=$md5 path=$remote"
    if($UploadOnly) {Write-Host 'UPLOAD_ONLY_PASS: no guards removed; no installer started.';return}
    # Remove only the exact temporary capture guards made for this gateway.
    $prepare=@'
( size=$(du __PACKAGE_PATH__ | awk '{print $1}')
free=$(df -k /data | tail -n 1 | awk '{print $4}')
[ "$free" -ge "$size" ] || { echo 'Insufficient OTA unpack space'; exit 1; }
tmpfree=$(df -k /tmp | tail -n 1 | awk '{print $4}')
available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
required=$((size + 8192))
[ "$tmpfree" -ge "$required" ] && [ "$available" -ge "$required" ] || { echo 'Insufficient temporary unpack capacity'; exit 1; }
[ ! -e /tmp/manual-ota.running ] || { echo 'Manual OTA already launched in this boot'; exit 1; }
for target in /bin/flash_erase /bin/nandwrite /bin/fw_unpack /bin/fw_miot_unpack /bin/fw_update.sh /bin/fw_manager.sh; do
    if grep -q 'OTA_CAPTURE_ONLY: installation is blocked' "$target"; then
        [ -f /tmp/ota-capture/guard.sh ] && cmp -s /tmp/ota-capture/guard.sh "$target" || exit 1
        umount "$target" || exit 1
    fi
done
! grep -q 'OTA_CAPTURE_ONLY: installation is blocked' /bin/fw_manager.sh || exit 1
)
'@
    [void](Run ($prepare.Replace('__PACKAGE_PATH__',$remote)))
    # Detach the installer from Telnet; never retry a possibly accepted trigger.
    $launch=@'
( command -v nohup >/dev/null || exit 1
cat > /tmp/manual-ota-run.sh <<'GW2_OTA_RUN'
#!/bin/sh
/bin/fw_manager.sh -u -s __PACKAGE_PATH__
rc=$?
printf 'INSTALLER_EXIT=%s\n' "$rc"
exit "$rc"
GW2_OTA_RUN
: > /tmp/manual-ota.running
nohup sh /tmp/manual-ota-run.sh </dev/null >/tmp/manual-ota.log 2>&1 &
printf 'OTA_STARTED_PID=%s\n' "$!"
)
'@
    $launch=$launch.Replace('__PACKAGE_PATH__',$remote)
    try {$result=Run $launch;Write-Host "OTA_STARTED PID=$(Field $result 'OTA_STARTED_PID')"}
    catch {throw "Trigger result unknown. Do NOT retry automatically. Check /tmp/manual-ota.log and firmware version. $($_.Exception.Message)"}
    Write-Host 'Signed stock installer launched. It reboots automatically on success.'
    Write-Host 'Do not power off. Installer log: /tmp/manual-ota.log'
    Write-Host 'After reconnect: agetprop ro.sys.mi_fw_ver; agetprop ro.sys.mi_build_num; cat /proc/version'
} finally {
    if($echoOff) {try {[void]$script:Session.Command('stty echo',3000,$null)} catch {}}
    $script:Session.Dispose()
}
