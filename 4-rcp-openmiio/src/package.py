from pathlib import Path
import hashlib
import shutil
import tarfile
import tempfile
root=Path(__file__).resolve().parent
output=root/'build-output'; output.mkdir(exist_ok=True)
def pack(template,arcname,filename,replacements=None):
    with tempfile.TemporaryDirectory(prefix='component-repack-',dir=output) as directory:
        stage=Path(directory)/arcname; shutil.copytree(root/template,stage)
        (stage/"VERSION").write_text((root.parent.parent/"VERSION").read_text())
        for src,dest in (replacements or {}).items():
            p=stage/dest; p.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(root/src,p)
        # Refresh only project-managed relative manifests, never stock or
        # upstream-binary compatibility hashes that refer to device files.
        for relative in ('payload/payload.sha256','payload/scripts.sha256'):
            manifest=stage/relative
            if manifest.is_file():
                names=[line.split('  ',1)[1] for line in manifest.read_text().splitlines() if line]
                for name in names:
                    target=(manifest.parent/name).resolve()
                    if not target.is_relative_to(stage.resolve()) or not target.is_file():
                        raise SystemExit('Invalid internal manifest path: '+name)
                manifest.write_text(''.join(hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in names))
        files=sorted(p for p in stage.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
        (stage/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(stage).as_posix()+'\n' for p in files))
        with tarfile.open(output/filename,'w:gz') as archive: archive.add(stage,arcname=arcname)
        print('REBUILT_COMPONENT_PACKAGE:',output/filename)

pack('rcp-openmiio-package','rcp-openmiio','rcp-openmiio-rebuilt.tar.gz')
