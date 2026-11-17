from pathlib import Path
import hashlib
root=Path(__file__).resolve().parent
firmware=root.parents[1]/'0-build-src/firmware'
names={
 'lumi-gateway-mgl001_opentread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_460800.gbl':'faeedf5976e832342c4139e84968a7a32a1a6badb328f30a4346e5c735202d59',
 'xiaomi_stock_ncp_6.6.6.0_build218.gbl':'389c55ea876a0dc7dbcde2cbb1bc1aefc9cf884bb2850663077629dc51c9fed0'}
for name,expected in names.items():
 p=firmware/name
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
  raise SystemExit('Missing/mismatched firmware input: '+name+'; see BUILD-RESOURCES.md')
for slot in (root/'rcp_lab/firmware',root/'rcp_lab/native-tools/rcp-native/firmware'):
 if not slot.is_symlink() or slot.resolve()!=firmware.resolve():
  raise SystemExit('Restore dependency links first: python3 tools/restore-dependencies.py --create-links --component 3')
print('Verified shared firmware inputs ready; no package extraction, radio access or flash.')
