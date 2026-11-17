from pathlib import Path
import shutil
import json
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
# GitHub source edition stores executable permissions separately from the ZIP.
manifest=root.parents[1]/'dependencies/kernel-permissions.json'
for name,mode in json.loads(manifest.read_text()).items():
    p=dst/name
    if not p.resolve().is_relative_to(dst.resolve()):
        raise SystemExit('Unexpected permission-map path')
    if p.is_file(): p.chmod(mode)
if not (dst/'.config').is_file():
    shutil.copyfile(root/'tun_lab/tested-kernel.config',dst/'.config')
(dst / '.config.mi-gateway2-baseline').write_bytes((dst / '.config').read_bytes())
(dst / '.mi-gateway2-worktree').write_text('Independent ABI experiment tree; original source untouched.\n')
print('Ready:', dst)
