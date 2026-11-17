"""Exercise reset policy against fake GPIO/scripts/clock; never touch a gateway."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
original = (root / 'deploy/payload/rcp-recovery.sh').read_text()


def run_case(name, body, expected=0, signal=False):
    with tempfile.TemporaryDirectory(prefix='otbr-rcp-reset-test-') as directory:
        tmp = Path(directory)
        base = tmp / 'base'; base.mkdir()
        (base / 'enabled').touch()
        (tmp / 'ready').touch()
        (tmp / 'uptime').write_text('100.00 0.00\n')
        gpio = tmp / 'gpio'
        for pin, value in ((43, '1'), (44, '0')):
            path = gpio / ('gpio' + str(pin)); path.mkdir(parents=True)
            (path / 'direction').write_text('out\n')
            (path / 'value').write_text(value + '\n')
        binary = tmp / 'bin'; binary.mkdir()
        for kind, pin in (('isp',43), ('reset',44)):
            text = '#!/bin/sh\nset -eu\n'
            text += 'printf "%s %s\\n" ' + kind + ' "$1" >> "$FIXTURE/operations"\n'
            if kind == 'isp':
                text += '[ ! -f "$FIXTURE/fail-isp" ] || exit 1\n'
            else:
                text += '[ "$1" != 1 ] || [ ! -f "$FIXTURE/fail-assert" ] || exit 1\n'
                text += '[ "$1" != 0 ] || [ ! -f "$FIXTURE/fail-release" ] || exit 1\n'
            text += 'printf "%s\\n" "$1" > "$FIXTURE/gpio/gpio' + str(pin) + '/value"\n'
            (binary / ('zigbee_' + kind + '.sh')).write_text(text)
        (binary / 'fuser').write_text('''#!/bin/sh
if [ -f "$FIXTURE/uart-error" ]; then echo 'mock UART inspection failed' >&2; exit 2; fi
if [ -f "$FIXTURE/uart-busy" ]; then echo 123; exit 0; fi
exit 1
''')
        sleep_script = '#!/bin/sh\nexit 0\n'
        if signal:
            sleep_script = '''#!/bin/sh
if [ "$1" = 100000 ]; then kill -TERM "$PPID"; fi
exit 0
'''
        (binary / 'usleep').write_text(sleep_script)
        for p in binary.iterdir(): p.chmod(0o700)
        script = original.replace('/tmp/mi-otbr-rcp-recovery', str(tmp/'recovery'))
        script = script.replace('/tmp/rcp-openmiio.stock-ready', str(tmp/'ready'))
        script = script.replace('/proc/uptime', str(tmp/'uptime')).replace('/sys/class/gpio', str(gpio))
        script = script.replace('/dev/ttyS1', '/dev/null')
        for kind in ('isp','reset'):
            script = script.replace('/bin/zigbee_' + kind + '.sh', str(binary/('zigbee_'+kind+'.sh')))
        helper = tmp / 'helper.sh'; helper.write_text(script)
        wrapper = tmp / 'run.sh'
        wrapper.write_text('''#!/bin/sh
set -eu
BASE="$FIXTURE/base"
STOP="$FIXTURE/stop"
CHILD_PID="$FIXTURE/child.pid"
pid_matches() { [ -f "$FIXTURE/host-live" ]; }
. "$FIXTURE/helper.sh"
rcp_recovery_init
clock() { printf '%s.00 0.00\\n' "$1" > "$FIXTURE/uptime"; }
expect_rc() {
    EXPECTED=$1; shift
    if "$@"; then ACTUAL=0; else ACTUAL=$?; fi
    [ "$ACTUAL" -eq "$EXPECTED" ] || { echo "expected=$EXPECTED actual=$ACTUAL"; exit 91; }
}
no_gpio() { [ ! -e "$FIXTURE/operations" ]; }
''' + body)
        env = dict(os.environ, FIXTURE=str(tmp), PATH=str(binary)+':/usr/bin:/bin')
        result = subprocess.run(['sh', str(wrapper)], env=env, capture_output=True, text=True, timeout=8)
        assert result.returncode == expected, (name, result.returncode, result.stdout, result.stderr)
        if signal:
            assert (gpio / 'gpio44/value').read_text().strip() == '0', name
            assert (tmp / 'operations').read_text().splitlines()[-1] == 'reset 0', name
        print('PASS:', name)


run_case('exit classification excludes normal/config/incompatible/software reset/signals', '''
for RC in 0 1 2 3 5 7 8 137 143; do expect_rc 1 rcp_queue_recovery "$RC"; done
[ -z "$RCP_PENDING_RC" ]; no_gpio
for RC in 4 6; do rcp_queue_recovery "$RC"; [ "$RCP_PENDING_RC" = "$RC" ]; done
no_gpio
''')
run_case('normal boot, timed pulse, readback and persistent attempt record', '''
rcp_queue_recovery 6
expect_rc 1 rcp_recover_pending; no_gpio
clock 105
rcp_recover_pending
[ -z "$RCP_PENDING_RC" ]
[ "$(cat "$FIXTURE/operations")" = "$(printf 'isp 1\\nreset 1\\nreset 0')" ]
[ "$(cat "$RCP_HISTORY")" = 105 ]
grep -q 'result=reset-complete' "$RCP_STATUS"
''')
for marker in ('uart-busy','uart-error','host-live','stop'):
    prefix = 'echo 123 > "$CHILD_PID"\n' if marker == 'host-live' else ''
    run_case('no GPIO when ' + marker, prefix + 'touch "$FIXTURE/' + marker + '"\n' + '''
rcp_queue_recovery 6; clock 110
expect_rc 1 rcp_recover_pending; no_gpio
''')
run_case('rolling budget/backoff survives a new supervisor session', '''
rcp_queue_recovery 6; clock 105; rcp_recover_pending
rcp_queue_recovery 4; clock 119; expect_rc 1 rcp_recover_pending
clock 120; rcp_recover_pending
rcp_queue_recovery 6; clock 149; expect_rc 1 rcp_recover_pending
clock 150; rcp_recover_pending
. "$FIXTURE/helper.sh"
rcp_recovery_init; rcp_queue_recovery 6
clock 180; expect_rc 1 rcp_recover_pending
[ "$(wc -l < "$RCP_HISTORY")" -eq 3 ]
[ "$(grep -c 'reset 1' "$FIXTURE/operations")" -eq 3 ]
clock 800; rcp_recover_pending
[ "$(cat "$RCP_HISTORY")" = 800 ]
''')
run_case('bad history blocks GPIO', '''
printf 'bad-data\\n' > "$RCP_HISTORY"
rcp_queue_recovery 6; clock 110
expect_rc 1 rcp_recover_pending; no_gpio
''')
run_case('boot mode failure never asserts reset', '''
touch "$FIXTURE/fail-isp"
rcp_queue_recovery 6; clock 110
expect_rc 2 rcp_recover_pending
! grep -q 'reset' "$FIXTURE/operations"
''')
run_case('assert failure still releases reset', '''
touch "$FIXTURE/fail-assert"
rcp_queue_recovery 6; clock 110
expect_rc 2 rcp_recover_pending
[ "$RCP_RESET_ASSERTED" -eq 0 ]
[ "$(cat "$FIXTURE/gpio/gpio44/value")" = 0 ]
''')
run_case('release failure blocks Host restart', '''
touch "$FIXTURE/fail-release"
rcp_queue_recovery 6; clock 110
expect_rc 3 rcp_recover_pending
[ "$RCP_RESET_ASSERTED" -eq 1 ]
grep -q 'result=reset-release-failed' "$RCP_STATUS"
''')
run_case('TERM during pulse executes release cleanup', '''
trap 'if [ "$RCP_RESET_ASSERTED" -eq 1 ]; then rcp_release_reset; fi; exit 143' TERM
rcp_queue_recovery 6; clock 110
rcp_recover_pending
''', expected=143, signal=True)

supervisor = (root / 'deploy/payload/supervisor.sh').read_text()
assert supervisor.index('--check-config') < supervisor.index('if rcp_recover_pending') < supervisor.index('sh "$BASE/routing.sh" apply')
assert supervisor.index('if wait "$CHILD"') < supervisor.index('CHILD=\n    rm -f "$CHILD_PID"') < supervisor.index('rcp_queue_recovery "$RC"')
assert 'if [ "$RCP_RESET_ASSERTED" -eq 1 ]; then' in supervisor
print('RCP_RECOVERY_FIXTURE_PASS: fake GPIO/UART/clock only; no compiler, gateway access or hardware operation.')
