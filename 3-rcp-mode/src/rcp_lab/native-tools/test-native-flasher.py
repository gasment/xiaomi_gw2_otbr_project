import binascii
import errno
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time

root=Path(__file__).resolve().parent
exe=root/'radio-flasher-host'
firmware=root.parent/'firmware/lumi-gateway-mgl001_opentread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_460800.gbl'
original=firmware.read_bytes()
menu=b'\r\nGecko Bootloader v1.9.2\r\n1. upload gbl\r\n2. run\r\n3. ebl info\r\nBL > '

def simulate(case, image=firmware):
    master,slave=pty.openpty()
    device=os.ttyname(slave)
    log=tempfile.TemporaryFile()
    mode='probe' if case=='probe' else 'flash'
    args=[str(exe),mode,device]+([str(image)] if mode=='flash' else [])
    proc=subprocess.Popen(args,stdout=log,stderr=log)
    state='menu'; pending=bytearray(); payload=bytearray(); nextblock=1; retry=False; uploads=0; ran=False
    deadline=time.monotonic()+15
    try:
        while proc.poll() is None and time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],0.1)
            if not ready: continue
            data=os.read(master,8192)
            pending.extend(data)
            while pending:
                if state=='menu':
                    c=pending.pop(0)
                    if c==13:
                        if case=='wrong-version': os.write(master,menu.replace(b'v1.9.2',b'v0.0.0'))
                        else: os.write(master,menu)
                    elif c==49:
                        uploads+=1; os.write(master,b'\r\nbegin upload\r\nC'); state='upload'
                    elif c==50: ran=True
                else:
                    if pending[0]==0x18:
                        pending.pop(0); state='menu'; continue
                    if pending[0]==4:
                        pending.pop(0)
                        assert bytes(payload[:len(original)])==original
                        assert set(payload[len(original):])<={255}
                        os.write(master,b'\x06\r\nSerial upload complete\r\n0x00\x00'+menu)
                        state='menu'; continue
                    if len(pending)<133: break
                    block=bytes(pending[:133]); del pending[:133]
                    assert block[0]==1 and block[1]==nextblock%256 and block[2]==255-block[1]
                    assert binascii.crc_hqx(block[3:131],0)==int.from_bytes(block[131:133],'big')
                    if case=='abort':
                        os.write(master,b'\x18\x18'); state='menu'; continue
                    if case=='retry' and nextblock==3 and not retry:
                        retry=True; os.write(master,b'\x15'); continue
                    payload.extend(block[3:131]); nextblock+=1; os.write(master,b'\x06')
        if proc.poll() is None: raise AssertionError('Simulator timed out')
        # Drain a final run command written immediately before process exit.
        if select.select([master],[],[],0.1)[0]:
            tail=os.read(master,8192)
            if state=='menu' and b'2' in tail: ran=True
        proc.wait(timeout=2)
        log.seek(0); output=log.read().decode(errors='replace')
        success=case in ['normal','retry','probe']
        assert (proc.returncode==0)==success,(case,proc.returncode,output)
        if case=='probe': assert uploads==0 and not ran and 'BOOTLOADER_PROBE_PASS' in output
        elif success: assert uploads==1 and ran and 'APPLICATION_UPLOAD_PASS' in output
        elif case in ['bad-crc','wrong-version']: assert uploads==0 and not ran
        else: assert not ran
        print('PASS',case)
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()
        os.close(master); os.close(slave); log.close()

simulate('probe')
simulate('normal')
simulate('retry')
simulate('abort')
simulate('wrong-version')
with tempfile.TemporaryDirectory() as d:
    bad=Path(d)/'bad.gbl'; data=bytearray(original); data[100]^=1; bad.write_bytes(data)
    simulate('bad-crc',bad)
print('NATIVE_FLASHER_SIMULATION_PASS')
