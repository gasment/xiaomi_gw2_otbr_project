from pathlib import Path
import os
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1] / "rcp-openmiio-package/payload/openmiio_agent.guard.sh"
functions = source.read_text().split("# LED_SYNC_FUNCTIONS_BEGIN\n", 1)[1].split("# LED_SYNC_FUNCTIONS_END", 1)[0]
old = 'old {"method":"local.status","params":"cloud_connected"}'
fresh = 'new {"method":"local.status","params":"cloud_connected"}'
cases = [
    ("fresh online reply repairs once", "network_connected", fresh, True, "ok", 0, 1, 0),
    ("connecting can recover", "network_connecting", fresh, True, "ok", 0, 1, 0),
    ("stale reply cannot trigger", "network_connected", old, True, "ok", 0, 0, 1),
    ("offline reply cannot trigger", "network_connected", 'new {"method":"local.status","params":"cloud_retry"}', True, "ok", 0, 0, 1),
    ("missing hardware cannot trigger", "network_connected", fresh, False, "ok", 0, 0, 1),
    ("identify is preserved", "system_identify", fresh, True, "ok", 0, 0, 0),
    ("pairing is preserved", "network_waiting", fresh, True, "ok", 0, 0, 0),
    ("ready is not overridden", "system_ready", fresh, True, "ok", 0, 0, 0),
    ("notification failure stays pending", "network_connected", fresh, True, "fail", 0, 1, 1),
    ("three attempts cap", "network_connected", fresh, True, "ok", 3, 0, 0),
]
for name, state, status, hardware, mode, tries, calls, rc in cases:
    with tempfile.TemporaryDirectory() as directory:
        d = Path(directory)
        (d / "state").write_text(state)
        (d / "messages").write_text(status + "\n")
        (d / "openmiio").write_text("accept conn app=hardware\n" if hardware else "")
        script = """set -u
agetprop() { cat "$TEST_DIR/state"; }
sleep() { :; }
timeout() {
    echo called >> "$TEST_DIR/calls"
    [ "$TEST_MODE" = ok ] || return 1
    echo system_ready > "$TEST_DIR/state"
    echo '{"result":["ok"]}'
}
""" + functions + """
LED_MESSAGES=$TEST_DIR/messages
LED_OPENMIIO_LOG=$TEST_DIR/openmiio
LED_INITIAL_STATUS=$TEST_OLD
LED_TRIES=$TEST_TRIES
led_sync_tick
"""
        env = dict(os.environ, TEST_DIR=str(d), TEST_MODE=mode, TEST_OLD=old, TEST_TRIES=str(tries))
        result = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
        observed = len((d / "calls").read_text().splitlines()) if (d / "calls").exists() else 0
        assert (observed, result.returncode) == (calls, rc), (name, observed, result.stdout, result.stderr)
        if calls and mode == "ok":
            # The real post-notification state check terminates subsequent work.
            again = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
            assert again.returncode == 0 and len((d / "calls").read_text().splitlines()) == 1
        print("PASS:", name)
subprocess.run(["sh", "-n", str(source)], check=True)
print("LED_SUPERVISOR_CHECK_PASS")
