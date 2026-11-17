"""Check kernel/stock preflight with fixtures only; never access a gateway."""
from pathlib import Path
import os
import subprocess
import tempfile

source=Path(__file__).with_name('install.sh').read_text()
functions=source.split('# PLATFORM_PREFLIGHT_BEGIN\n',1)[1].split('# PLATFORM_PREFLIGHT_END',1)[0]
cases=[('different kernel', 'kernel build 2022', 'kernel build 2026', 1, False),
       ('matching kernel', 'kernel build 2026', 'kernel build 2026', 0, True),
       ('different stock scripts', 'kernel build 2026', 'kernel build 2026', 1, True)]
for name,actual,expected,rc,stock in cases:
    with tempfile.TemporaryDirectory() as directory:
        d=Path(directory)
        script="""set -eu
fail() { echo "$*" >&2; exit 1; }
cat() { if [ "$1" = /proc/version ]; then printf '%s\n' "$TEST_ACTUAL"; else command cat "$@"; fi; }
agetprop() { case "$1" in ro.sys.mi_fw_ver) echo 1.0.3;; *) echo 0028;; esac; }
extract() {
    if [ "$2" = mi_gateway_2_tun_deploy ]; then
        mkdir -p "$WORK/$2/payload"
        printf '%s\n' "$TEST_EXPECTED" > "$WORK/$2/payload/expected-proc-version.txt"
    else
        mkdir -p "$WORK/rcp-mode/payload"
    fi
}
sha256sum() { echo checked > "$TEST_DIR/stock-check"; [ "$TEST_STOCK" = good ]; }
TUN=tun.tar.gz
MODE=mode.tar.gz
WORK=$TEST_DIR
"""+functions+"\nplatform_preflight\n"
        env=dict(os.environ,TEST_DIR=str(d),TEST_ACTUAL=actual,TEST_EXPECTED=expected,TEST_STOCK='bad' if name=='different stock scripts' else 'good')
        result=subprocess.run(['sh','-c',script],env=env,capture_output=True,text=True)
        assert result.returncode==rc,(name,result.stdout,result.stderr)
        assert (d/'stock-check').exists()==stock,name
        if actual!=expected:
            assert 'UNSUPPORTED_KERNEL_BASELINE' in result.stderr and actual in result.stderr and expected in result.stderr
        print('PASS:',name)
print('KERNEL_PREFLIGHT_POLICY_PASS: fixtures only; no module or radio operation')
