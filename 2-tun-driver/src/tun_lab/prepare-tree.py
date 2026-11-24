from pathlib import Path
import shutil
import zipfile
root = Path(__file__).resolve().parents[1]
src = root / 'source/linux-chenxing-vendor-slop-ikayaki_dlm00v014'
dst = root / 'tun_lab/kernel-work'
if dst.exists():
    if not (dst / '.mi-gateway2-worktree').exists():
        raise SystemExit('Unknown existing kernel-work directory; refusing to use it.')
    print('Reusing independent worktree:', dst)
    raise SystemExit(0)
print('Copying source into independent worktree...')
shutil.copytree(src, dst)
# Python ZIP extraction did not preserve Unix executable permissions.
archive = root / 'external/kernel-archive/linux-chenxing-vendor-slop-ikayaki_dlm00v014.zip'
with zipfile.ZipFile(archive) as z:
    for entry in z.infolist():
        rel = Path(entry.filename).parts[1:]
        if not rel or entry.is_dir(): continue
        p = dst.joinpath(*rel)
        if not p.resolve().is_relative_to(dst.resolve()):
            raise SystemExit('Unexpected archive path')
        mode = (entry.external_attr >> 16) & 0o777
        if p.is_file() and mode:
            p.chmod(mode)
(dst / '.config.mi-gateway2-baseline').write_bytes((dst / '.config').read_bytes())
(dst / '.mi-gateway2-worktree').write_text('Independent ABI experiment tree; original source untouched.\n')
print('Ready:', dst)
