import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time

root=Path(__file__).resolve().parent
def crc(b):
    c=65535
    for v in b:
        c^=v
        for _ in range(8): c=(c>>1)^(0x8408 if c&1 else 0)
    return c^65535
def packed(v):
    out=bytearray()
    while True:
        out.append(v&127); v>>=7
        if not v: return out
        out[-1]|=128
def encode(data):
    payload=data+crc(data).to_bytes(2,'little'); out=bytearray([126])
    for c in payload:
        if c in [126,125,17,19,248]: out.append(125); c^=32
        out.append(c)
    return out+bytes([126])
for corrupt in [False,True]:
    master,slave=pty.openpty(); logfile=tempfile.TemporaryFile()
    proc=subprocess.Popen([str(root/'spinel-probe-host'),os.ttyname(slave)],stdout=logfile,stderr=logfile)
    buf=bytearray(); escaped=False; started=False; sent_bad=False; requests=0
    deadline=time.monotonic()+15
    try:
        while proc.poll() is None and time.monotonic()<deadline:
            if not select.select([master],[],[],0.1)[0]: continue
            for c in os.read(master,8192):
                if c==126:
                    if len(buf)>=5:
                        frame=bytes(buf); assert crc(frame[:-2])==int.from_bytes(frame[-2:],'little')
                        header,command=frame[:2]; assert command==2,'Non-GET command detected'
                        prop=0; shift=0
                        for v in frame[2:-2]:
                            prop|=(v&127)<<shift; shift+=7
                            if not v&128: break
                        requests+=1
                        values={2:b'SL-OPENTHREAD/2.5.3.0_Test; EFR32\0',1:b'\x04\x03',5:packed(512)+packed(513),176:packed(10),177:packed(4)}
                        reply=bytearray(encode(bytes([header,6])+packed(prop)+values[prop]))
                        if corrupt and not sent_bad: reply[-2]^=1; sent_bad=True
                        os.write(master,reply)
                    buf.clear(); escaped=False; started=True
                elif started:
                    if not escaped and c==125: escaped=True; continue
                    if escaped: c^=32; escaped=False
                    buf.append(c)
        if proc.poll() is None: raise AssertionError('Probe simulator timeout')
        proc.wait(); logfile.seek(0); output=logfile.read().decode()
        assert proc.returncode==0 and 'SPINEL_RCP_PROBE_PASS' in output,output
        assert requests==(6 if corrupt else 5),requests
        print('PASS simulated GET-only Spinel probe; corrupt_first_reply='+str(corrupt))
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
        os.close(master); os.close(slave); logfile.close()
print('SPINEL_PROBE_SIMULATION_PASS')
