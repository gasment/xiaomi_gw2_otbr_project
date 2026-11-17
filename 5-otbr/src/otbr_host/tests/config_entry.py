"""User-run tests for config-only behavior and redacted feature reporting."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

binary = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='otbr-config-entry-') as directory:
    tmp = Path(directory)
    text = (root / 'tests/fixtures/parser-config.example').read_text()
    state = tmp / 'must-not-be-created'
    text = text.replace('/data/otbr/state', str(state))
    (tmp / 'config.yaml').write_text(text)
    def run(expected):
        result = subprocess.run([str(binary), str(tmp / 'config.yaml')], text=True, capture_output=True)
        assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
        assert not state.exists(), 'Configuration check created runtime state'
        for secret in ['00112233445566778899aabbccddeeff', '102132435465768798a9bacbdcedfe0f',
                       'TEST-ONLY-REPLACE-LOCALLY', 'CHANGE-ME', 'AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=']:
            assert secret not in result.stdout + result.stderr, 'Credential leaked in report'
        return result
    run(1)  # Missing secret file must fail before runtime initialization.
    shutil.copy2(root / 'tests/fixtures/parser-secrets.example', tmp / 'secrets.yaml')
    result = run(0)
    assert 'CONFIG_SCHEMA_VALID' in result.stdout and 'CONFIG_FIELDS_READY' in result.stdout
    assert 'background HTTP/HTTPS' in result.stdout
    # Optional HA mapping can be disabled without changing other YAML behavior.
    text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith(('ha_url:', 'ha_token:'))) + '\n'
    (tmp / 'config.yaml').write_text(text)
    result = run(0)
    assert 'CONFIG_CHECK_ONLY' in result.stdout and 'CONFIG_FIELDS_READY' in result.stdout
    print('CONFIG_ENTRY_PASS: missing secrets rejected; HA configuration wired; output redacted; no runtime state created.')
