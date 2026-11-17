using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Diagnostics;

namespace MiGw2Deploy {
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
 public sealed class ReadOnlyFtp : IDisposable {
  readonly IPAddress address; readonly int passivePort; readonly string password;
  readonly Dictionary<string,string> files; TcpListener listener; volatile bool running;
  readonly object gate=new object(); readonly List<TcpClient> clients=new List<TcpClient>();
  public long BytesSent;
  public int Port { get { return ((IPEndPoint)listener.LocalEndpoint).Port; } }
  public ReadOnlyFtp(string ip,int port,int dataPort,string secret,Dictionary<string,string> allowed) {
   address=IPAddress.Parse(ip); passivePort=dataPort; password=secret; files=allowed;
   listener=new TcpListener(address,port);
  }
  public void Start() { listener.Start(4); running=true; Thread t=new Thread(Accept); t.IsBackground=true; t.Start(); }
  void Accept() {
   while(running) {
    try {
     TcpClient c=listener.AcceptTcpClient();
     lock(gate) { if(clients.Count>=4) { c.Close(); continue; } clients.Add(c); }
     Thread t=new Thread(delegate() { Handle(c); }); t.IsBackground=true; t.Start();
    } catch(SocketException) { if(!running) break; } catch(ObjectDisposedException) { break; }
   }
  }
  string FileName(string argument) {
   string name=Uri.UnescapeDataString(argument).TrimStart('/');
   if(name.IndexOf('/')>=0 || name.IndexOf('\\')>=0 || name=="..") return null;
   return files.ContainsKey(name)?files[name]:null;
  }
  void Handle(TcpClient c) {
   TcpListener passive=null;
   try {
    c.ReceiveTimeout=20000; c.SendTimeout=20000;
    using(NetworkStream ns=c.GetStream())
    using(StreamReader reader=new StreamReader(ns,Encoding.ASCII))
    using(StreamWriter writer=new StreamWriter(ns,Encoding.ASCII)) {
     writer.NewLine="\r\n"; writer.AutoFlush=true; writer.WriteLine("220 GW2 temporary read-only FTP");
     bool user=false,authenticated=false;
     string line;
     while(running && (line=reader.ReadLine())!=null) {
      int split=line.IndexOf(' '); string verb=(split<0?line:line.Substring(0,split)).ToUpperInvariant();
      string arg=split<0?"":line.Substring(split+1);
      if(verb=="QUIT") { writer.WriteLine("221 Bye"); break; }
      if(verb=="USER") { user=arg=="deploy"; writer.WriteLine("331 Password required"); continue; }
      if(verb=="PASS") { authenticated=user && arg==password; writer.WriteLine(authenticated?"230 Logged in":"530 Login rejected"); continue; }
      if(!authenticated) { writer.WriteLine("530 Login first"); continue; }
      if(verb=="SYST") writer.WriteLine("215 UNIX Type: L8");
      else if(verb=="PWD" || verb=="XPWD") writer.WriteLine("257 \"/\"");
      else if(verb=="CWD") writer.WriteLine(arg=="/" || arg=="."?"250 Directory selected":"550 Directory not available");
      else if(verb=="TYPE" || verb=="OPTS" || verb=="NOOP") writer.WriteLine("200 OK");
      else if(verb=="FEAT") { writer.WriteLine("211-Features"); writer.WriteLine(" SIZE"); writer.WriteLine(" EPSV"); writer.WriteLine("211 End"); }
      else if(verb=="SIZE") { string p=FileName(arg); writer.WriteLine(p==null?"550 File not available":"213 "+new FileInfo(p).Length); }
      else if(verb=="PASV" || verb=="EPSV") {
       if(passive!=null) passive.Stop(); passive=new TcpListener(address,passivePort); passive.Start(1);
       int p=((IPEndPoint)passive.LocalEndpoint).Port;
       if(verb=="EPSV") writer.WriteLine("229 Entering Extended Passive Mode (|||"+p+"|)");
       else writer.WriteLine("227 Entering Passive Mode ("+address.ToString().Replace('.',',')+","+(p/256)+","+(p%256)+")");
      } else if(verb=="RETR") {
       string path=FileName(arg);
       if(path==null) { writer.WriteLine("550 File not available"); continue; }
       if(passive==null) { writer.WriteLine("425 Use passive mode"); continue; }
       writer.WriteLine("150 Opening binary data connection");
       try {
        var accept=passive.AcceptTcpClientAsync(); if(!accept.Wait(10000)) throw new TimeoutException();
        using(TcpClient data=accept.GetAwaiter().GetResult()) {
         data.SendTimeout=15000;
         using(FileStream input=File.OpenRead(path)) using(NetworkStream transfer=data.GetStream()) {
          input.CopyTo(transfer,32768); transfer.Flush(); Interlocked.Add(ref BytesSent,input.Length);
         }
        }
        writer.WriteLine("226 Transfer complete");
       } catch { writer.WriteLine("426 Transfer failed"); }
       finally { passive.Stop(); passive=null; }
      } else writer.WriteLine("502 Command not supported");
     }
    }
   } catch(IOException) { } catch(SocketException) { } catch(ObjectDisposedException) { } catch(UriFormatException) { }
   finally { if(passive!=null) passive.Stop(); c.Close(); lock(gate) { clients.Remove(c); } }
  }
  public void Dispose() {
   running=false; listener.Stop(); lock(gate) { foreach(TcpClient c in clients.ToArray()) c.Close(); }
  }
 }
 public static class ProtocolTests {
  static string Line(NetworkStream stream) {
   StringBuilder s=new StringBuilder(); int b;
   while((b=stream.ReadByte())>=0) {
    if(b==255) { int v=stream.ReadByte(); if(v>=251 && v<=254) stream.ReadByte(); continue; }
    if(b==10) return s.ToString(); if(b!=13) s.Append((char)b);
   }
   throw new IOException("Mock session ended");
  }
  public static void Telnet() {
   TcpListener listener=new TcpListener(IPAddress.Loopback,0); listener.Start();
   int port=((IPEndPoint)listener.LocalEndpoint).Port; Exception serverError=null;
   Thread server=new Thread(delegate() {
    try {
     using(TcpClient c=listener.AcceptTcpClient()) using(NetworkStream ns=c.GetStream()) {
      Action<string> send=delegate(string text) { byte[] b=Encoding.ASCII.GetBytes(text); ns.Write(b,0,b.Length); };
      byte[] negotiation={255,251,1}; ns.Write(negotiation,0,negotiation.Length); send("Mock login: ");
      if(Line(ns)!="root") throw new Exception("Root login was not sent"); send("Password: ");
      if(Line(ns)!="") throw new Exception("Password was not empty"); send("\r\n~ # ");
      if(Line(ns)!="false") throw new Exception("Unexpected test command"); string marker=Line(ns);
      Match m=Regex.Match(marker,@"(__GW2_[a-f0-9]+):"); if(!m.Success) throw new Exception("Missing command marker");
      // Echo the printf input first: it must not be mistaken for a result.
      send(marker+"\r\noutput\r\n"+m.Groups[1].Value+":7\r\n~ # ");
     }
    } catch(Exception e) { serverError=e; }
   }); server.IsBackground=true; server.Start();
   try { using(TelnetSession session=new TelnetSession()) { session.Open("127.0.0.1",port,5000); if(session.Command("false",5000,null).Code!=7) throw new Exception("Wrong exit status"); } }
   finally { listener.Stop(); server.Join(1000); }
   if(serverError!=null) throw serverError;
  }
 }
}
namespace MiGw2Deploy {
 public sealed class MockResumeGateway : IDisposable {
  TcpListener listener; volatile bool running; bool needsReboot=true; bool complete;
  public int RebootCount; public int ResumeCount; public int VerifyCount; int port;
  public string LastError;
  public int Port { get { return port; } }
  public void Start() {
   listener=new TcpListener(IPAddress.Loopback,0); listener.Server.SetSocketOption(SocketOptionLevel.Socket,SocketOptionName.ReuseAddress,true); listener.Start(); port=((IPEndPoint)listener.LocalEndpoint).Port; running=true;
   Thread thread=new Thread(Run); thread.IsBackground=true; thread.Start();
  }
  static string ReadLine(NetworkStream ns) {
   StringBuilder b=new StringBuilder(); int c;
   while((c=ns.ReadByte())>=0) { if(c==10) return b.ToString(); if(c!=13) b.Append((char)c); }
   return null;
  }
  static void Send(NetworkStream ns,string text) { byte[] b=Encoding.ASCII.GetBytes(text); ns.Write(b,0,b.Length); }
  void Run() {
   while(running) {
    bool reboot=false;
    try {
     using(TcpClient client=listener.AcceptTcpClient()) using(NetworkStream ns=client.GetStream()) {
      client.ReceiveTimeout=15000; Send(ns,"Mock login: "); if(ReadLine(ns)!="root") continue; Send(ns,"\r\n~ # ");
      StringBuilder command=new StringBuilder(); string line;
      while(running && (line=ReadLine(ns))!=null) {
       command.AppendLine(line); Match marker=Regex.Match(line,@"(__GW2_[a-f0-9]+):"); if(!marker.Success) continue;
       string value=command.ToString(); command.Clear();
       if(value.Contains("sync; reboot")) { Interlocked.Increment(ref RebootCount); needsReboot=false; reboot=true; break; }
       if(value.Contains("__GW2_STAGE=")) {
        Send(ns,"\r\n__GW2_STAGE="+(complete?"complete":"waiting-reboot")+"\r\n__GW2_VERSION=0.2.0\r\n__GW2_NEED_REBOOT="+(needsReboot?"1":"0")+"\r\n__GW2_ACTIVE=0\r\n__GW2_BOOT_READY=1\r\n__GW2_EXISTING=/data/rcp-mode\r\n");
       } else if(value.Contains("install.sh resume")) { Interlocked.Increment(ref ResumeCount); complete=true; Send(ns,"\r\nmock continuation completed\r\n"); }
       else if(value.Contains("install.sh verify")) { Interlocked.Increment(ref VerifyCount); Send(ns,"\r\nmock file verification completed\r\n"); }
       else { Send(ns,"\r\nunexpected command\r\n"+marker.Groups[1].Value+":1\r\n"); continue; }
       Send(ns,marker.Groups[1].Value+":0\r\n~ # ");
      }
     }
    } catch(IOException) { } catch(SocketException) { if(!running) break; } catch(ObjectDisposedException) { break; }
    if(reboot && running) {
     // Delay the login service while retaining the listener: Windows child
     // processes may inherit socket handles, making rebind-based mocks invalid.
     Thread.Sleep(1500);
    }
   }
  }
  public void Dispose() { running=false; listener.Stop(); }
 }
}
