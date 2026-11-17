"""Host-only policy tests. Never run a component installer, flash tool or reboot."""
from pathlib import Path
import hashlib
import os
import re
import subprocess
import tempfile

source = Path(__file__).with_name('install.sh').read_text()
verify = source.split('# VERIFY_FUNCTIONS_BEGIN\n', 1)[1].split('# VERIFY_FUNCTIONS_END', 1)[0]
journal = source.split('# JOURNAL_FUNCTIONS_BEGIN\n', 1)[1].split('# JOURNAL_FUNCTIONS_END', 1)[0]

with tempfile.TemporaryDirectory(prefix='gw2-auto-test-') as temporary:
    d = Path(temporary)
    base = d / 'data/mi-gw2-auto'
    base.mkdir(parents=True)
    assets = d / 'bundle'
    assets.mkdir()
    f = assets / 'fixture.bin'
    f.write_bytes(b'verified payload')
    manifest = d / 'SHA256SUMS'
    manifest.write_text(hashlib.sha256(f.read_bytes()).hexdigest() + '  fixture.bin\n')
    prefix = 'set -eu\nfail() { echo "$*" >&2; exit 1; }\nlog() { :; }\nsync() { :; }\n'
    prefix += 'BASE=' + str(base) + '\nBASE_MANIFEST=' + str(manifest) + '\n'
    def run(code):
        return subprocess.run(['sh', '-c', prefix + code], capture_output=True, text=True)
    assert run(verify + '\nverify_file ' + str(assets) + ' fixture.bin').returncode == 0
    f.write_bytes(b'tampered payload')
    assert run(verify + '\nverify_file ' + str(assets) + ' fixture.bin').returncode != 0
    assert run(verify + '\nverify_file ' + str(assets) + ' missing.bin').returncode != 0
    print('PASS: verified assets accepted; corrupted and missing assets rejected')
    manifest.write_text(('0' * 64 + '  fixture.bin\n') * 2)
    assert run(verify + '\nverify_file ' + str(assets) + ' fixture.bin').returncode != 0
    print('PASS: ambiguous checksum entries rejected')
    assert run(journal + '\nwrite_state waiting-reboot\nvalidate_stage "$(cat "$BASE/stage")"').returncode == 0
    assert (base / 'stage').read_text().strip() == 'waiting-reboot'
    assert not (base / 'stage.new').exists()
    assert run(journal + '\nvalidate_stage unexpected').returncode != 0
    print('PASS: journal is atomically replaced; unknown stages rejected')
    # Restrict the fresh-install guard to synthetic paths, preserving the actual
    # implementation and proving that existing installs are not reflashed.
    fake_journal = journal.replace('/data/', str(d / 'data') + '/').replace('/tmp/rcp-native', str(d / 'native'))
    hook = d / 'boot-hook'
    env = '\nHOOK=' + str(hook) + '\n'
    assert run(fake_journal + env + 'fresh_install_check').returncode == 0
    (d / 'data/otbr').mkdir()
    assert run(fake_journal + env + 'fresh_install_check').returncode != 0
    print('PASS: existing OTBR installation blocks first-install automation')
    # Exercise actual top-level resume dispatch under a private synthetic tree.
    # All device preflight is disabled, and no component install path is reached.
    (base / 'VERSION').write_text('0.2.0\n')
    (d / 'tmp').mkdir()
    transformed = re.sub(r'/(data|tmp|proc|sys)(?=[/\s\"\'])', lambda m: str(d / m.group(1)), source)
    transformed = transformed.replace('[ \"$(id -u)\" = 0 ]', ':', 1)
    transformed = transformed.replace('check_tools\nmodel_check\n', ': # synthetic device preflight\n', 1)
    test_script = base / 'install.sh'
    test_script.write_text(transformed)
    for stage, error in [('radio-in-progress', 'Do not auto-reflash'), ('unknown', 'Unknown deployment journal')]:
        (base / 'stage').write_text(stage + '\n')
        result = subprocess.run(['sh', str(test_script), 'resume'], capture_output=True, text=True)
        assert result.returncode != 0 and error in result.stderr, result
    print('PASS: actual resume dispatcher refuses interrupted flashing and invalid state')
# Exercise the actual one-shot reboot wrapper against a synthetic boot tree.
with tempfile.TemporaryDirectory(prefix='gw2-boot-test-') as temporary:
    d = Path(temporary)
    base = d / 'data/mi-gw2-auto'
    mode = d / 'data/rcp-mode'
    hooks = d / 'data/scripts'
    for directory in (base, mode, hooks): directory.mkdir(parents=True, exist_ok=True)
    stock = '#!/bin/sh\necho stock-ready\n'
    (mode / 'post_init.sh').write_text(stock)
    (mode / 'payload.sha256').write_text(hashlib.sha256(stock.encode()).hexdigest() + '  post_init.sh\n')
    (base / 'install.sh').write_text('#!/bin/sh\necho "$1" > "' + str(base / 'resumed') + '"\n')
    hook = source.split("<<'BOOT_HOOK'\n", 1)[1].split('\nBOOT_HOOK', 1)[0]
    hook = re.sub(r'/(data|tmp|proc|sys)(?=[/\s\"\'])', lambda m: str(d / m.group(1)), hook)
    (base / 'resume-post_init.sh').write_text(hook)
    (hooks / 'post_init.sh').write_text(hook)
    result = subprocess.run(['sh', str(hooks / 'post_init.sh')], capture_output=True, text=True)
    assert result.returncode == 0, result
    import time
    for _ in range(20):
        if (base / 'resumed').exists(): break
        time.sleep(0.05)
    assert (base / 'resumed').read_text().strip() == 'resume'
    assert (hooks / 'post_init.sh').read_text() == stock
    print('PASS: boot wrapper restores stock RCP chain and launches continuation once')
    (base / 'resumed').unlink()
    (hooks / 'post_init.sh').write_text(hook)
    (mode / 'post_init.sh').write_text(stock + '# corrupted\n')
    result = subprocess.run(['sh', str(hooks / 'post_init.sh')], capture_output=True, text=True)
    assert result.returncode != 0 and not (base / 'resumed').exists()
    assert (hooks / 'post_init.sh').read_text() == hook
    print('PASS: corrupted RCP boot chain prevents continuation without overwriting the hook')
subprocess.run(['sh', '-n', str(Path(__file__).with_name('install.sh'))], check=True)
print('LOCAL_AUTO_DEPLOY_POLICY_PASS: no gateway or component program was run')
