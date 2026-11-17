"""Exercise the scripts-only installer in a fake root; never operate a gateway."""
from pathlib import Path
import hashlib
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def run_case(kind):
    with tempfile.TemporaryDirectory(prefix='rcp-script-update-test-') as directory:
        tmp=Path(directory); base=tmp/'otbr'; base.mkdir()
        package=tmp/'package'; package.mkdir(); (package/'payload').mkdir()
        tools=tmp/'bin'; tools.mkdir()
        for name, contents in [('id','#!/bin/sh\necho 0\n'),('usleep','#!/bin/sh\nexit 0\n'),('fuser','#!/bin/sh\nexit 1\n')]:
            (tools/name).write_text(contents); (tools/name).chmod(0o700)
        for name in ('install.sh','rollback.sh'):
            text=(root/'recovery'/name).read_text().replace('/data/otbr',str(base))
            (package/name).write_text(text)
        for name in ('common.sh','supervisor.sh','status.sh'):
            (base/name).write_text('#!/bin/sh\n# original '+name+'\n')
        (base/'check.sh').write_text('#!/bin/sh\nexit 0\n')
        (base/'stop.sh').write_text('#!/bin/sh\necho stop >> "$FIXTURE/events"\n')
        (base/'start.sh').write_text('''#!/bin/sh
echo start >> "$FIXTURE/events"
if [ -f "$FIXTURE/fail-start" ]; then rm "$FIXTURE/fail-start"; exit 1; fi
''')
        (base/'mi-otbr-host').write_bytes(b'RUNNING_BINARY_MUST_NOT_CHANGE')
        (base/'config.yaml').write_text('USER_OWNED_CONFIG')
        (base/'secrets.yaml').write_text('USER_OWNED_SECRETS')
        before={p.name:p.read_bytes() for p in base.iterdir() if p.is_file()}
        for name in ('supervisor.sh','status.sh','rcp-recovery.sh'):
            (package/'payload'/name).write_text('#!/bin/sh\n# updated '+name+'\n')
        def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
        (package/'compatibility.sha256').write_text(''.join(digest(base/name)+'  '+str(base/name)+'\n' for name in ('common.sh','start.sh','stop.sh')))
        (package/'accepted-supervisor.sha256').write_text(digest(base/'supervisor.sh')+'\n'+digest(package/'payload/supervisor.sh')+'\n')
        (package/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.relative_to(package).as_posix()+'\n' for p in sorted(package.rglob('*')) if p.is_file()))
        if kind=='compatibility-refusal': (base/'common.sh').write_text('INDEPENDENT_USER_EDIT')
        if kind=='automatic-rollback': (tmp/'fail-start').touch()
        env=dict(os.environ,FIXTURE=str(tmp),PATH=str(tools)+':/usr/bin:/bin')
        result=subprocess.run(['sh',str(package/'install.sh')],env=env,capture_output=True,text=True,timeout=8)
        assert (result.returncode==0)==(kind=='success-and-explicit-rollback'),(kind,result.stdout,result.stderr)
        for name in ('mi-otbr-host','config.yaml','secrets.yaml'):
            assert (base/name).read_bytes()==before[name],(kind,name)
        if kind=='compatibility-refusal':
            assert not (tmp/'events').exists()
            assert (base/'supervisor.sh').read_bytes()==before['supervisor.sh']
        elif kind=='automatic-rollback':
            assert (base/'supervisor.sh').read_bytes()==before['supervisor.sh'],result.stdout
            assert 'RCP_RECOVERY_ROLLBACK_DONE' in result.stdout
        else:
            assert (base/'supervisor.sh').read_bytes()==(package/'payload/supervisor.sh').read_bytes()
            # A repeated install must not replace the original backup with the new supervisor.
            result=subprocess.run(['sh',str(package/'install.sh')],env=env,capture_output=True,text=True,timeout=8)
            assert result.returncode==0,(result.stdout,result.stderr)
            assert (base/'rcp-recovery-backup/supervisor.sh').read_bytes()==before['supervisor.sh']
            result=subprocess.run(['sh',str(base/'rcp-recovery-backup/rollback.sh')],env=env,capture_output=True,text=True,timeout=8)
            assert result.returncode==0,(result.stdout,result.stderr)
            assert (base/'supervisor.sh').read_bytes()==before['supervisor.sh']
        print('PASS: scripts-only updater '+kind)


for case in ('success-and-explicit-rollback','automatic-rollback','compatibility-refusal'):
    run_case(case)
print('RCP_RECOVERY_UPDATE_FIXTURE_PASS: fake root only; binary/YAML preserved, no GPIO or gateway operation.')
