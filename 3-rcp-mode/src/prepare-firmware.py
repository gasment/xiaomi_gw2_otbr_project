from pathlib import Path
import hashlib
import tarfile
root=Path(__file__).resolve().parent
version=(root.parent.parent/'5-otbr'/'VERSION').read_text().strip()
archive=root.parent/('deploy/rcp-native-'+version+'.tar.gz')
names={
 'lumi-gateway-mgl001_openthread_rcp_2.5.3.0_115200.gbl':'c70c5ddfa78840129422893a7f8850f02330f1937bc57a2ab29f87961d496d89',
 'xiaomi_stock_ncp_6.6.6.0_build218.gbl':'389c55ea876a0dc7dbcde2cbb1bc1aefc9cf884bb2850663077629dc51c9fed0'}
for name,expected in names.items():
    canonical=root/'rcp_lab/firmware'/name
    if canonical.is_file():
        data=canonical.read_bytes()
    else:
        with tarfile.open(archive) as package:
            data=package.extractfile('rcp-native/firmware/'+name).read()
    if hashlib.sha256(data).hexdigest()!=expected: raise SystemExit('Firmware mismatch: '+name)
    for directory in (root/'rcp_lab/firmware',root/'rcp_lab/native-tools/rcp-native/firmware'):
        directory.mkdir(parents=True,exist_ok=True)
        target=directory/name
        if not target.is_file(): target.write_bytes(data)
        elif target.read_bytes()!=data: raise SystemExit('Firmware mismatch: '+str(target))
print('RCP and stock rollback inputs verified.')
