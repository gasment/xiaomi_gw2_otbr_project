"""Temporary-space regression: fixtures only, no gateway or component operation."""
from pathlib import Path
import subprocess,tempfile

source=Path(__file__).with_name('install.sh').read_text()
function=source.split('# RELEASE_DOWNLOAD_ARCHIVE_BEGIN\n',1)[1].split('# RELEASE_DOWNLOAD_ARCHIVE_END',1)[0]
assert source.count('verify_bundle\n    release_download_archive\n')==2
assert source.count('free_space /tmp 28000')==2
for name in ['release verified duplicate','keep unrelated version','keep symlink','keep manual bundle']:
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory)
        download=base/'pc';download.mkdir()
        expanded=base/'expanded';expanded.mkdir()
        archive=download/'mi-gw2-auto-deploy-0.2.5.tar.gz'
        unrelated=download/'mi-gw2-auto-deploy-0.2.0.tar.gz';unrelated.write_bytes(b'unrelated')
        target=base/'target';target.write_bytes(b'do not remove')
        if name=='keep symlink':archive.symlink_to(target)
        else:archive.write_bytes(b'download already expanded and verified')
        code=function.replace('/tmp/mi-gw2-auto-deploy',str(expanded)).replace('/tmp/mi-gw2-pc-deploy',str(download))
        bundle=expanded if name!='keep manual bundle' else base/'manual'
        prefix='set -eu\nfail() { echo "$*" >&2; exit 1; }\nVERSION=0.2.5\nBUNDLE='+str(bundle)+'\n'
        subprocess.run(['sh','-c',prefix+code+'\nrelease_download_archive\n'],check=True,capture_output=True,text=True)
        assert unrelated.read_bytes()==b'unrelated'
        assert target.read_bytes()==b'do not remove'
        assert archive.exists()==(name in ['keep symlink','keep manual bundle'])
        print('PASS:',name)
print('TEMP_SPACE_REGRESSION_PASS: verified duplicate reclaimed; fixed 28000 KiB gate retained; unrelated files preserved.')
