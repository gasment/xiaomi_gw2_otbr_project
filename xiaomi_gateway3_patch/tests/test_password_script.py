"""Fake filesystem/commands only; never change a real account password or signal sshd."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "gateway/set-root-password.sh"


class PasswordScriptTests(unittest.TestCase):
    def exercise(self, mode="good"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["openssh/etc", "openssh/sbin", "res", "etc", "proc/424242", "bin"]:
                (root / name).mkdir(parents=True)
            auth = root / "res/passwd"
            auth.write_text("root::0:0:root:/root:/bin/sh\nsshd:*:65534:65534:SSH:/var/empty:/bin/false\n")
            (root / "etc/passwd").symlink_to(auth)
            (root / "pid").write_text("424242\n")
            config = root / "openssh/etc/sshd_config"
            original = "Port 2223\nPermitRootLogin yes\nPasswordAuthentication yes\nPermitEmptyPasswords yes\nSubsystem sftp internal-sftp\n"
            if mode == "match":
                original += "Match User root\n"
            config.write_text(original)
            sshd = root / "openssh/sbin/sshd"
            sshd.write_text("#!/bin/sh\n[ \"$FAKE_MODE\" != invalid-config ]\n")
            sshd.chmod(0o755)
            (root / "proc/424242/exe").symlink_to(sshd)
            passwd = root / "bin/passwd"
            passwd.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_ROOT/actions\"\n[ \"$FAKE_MODE\" != password-failed ] || exit 1\nprintf 'root:$6$fixture-only:0:0:root:/root:/bin/sh\\n' > \"$FAKE_ROOT/res/passwd\"\n")
            passwd.chmod(0o755)
            busybox = root / "bin/busybox"
            busybox.write_text("#!/bin/sh\n[ \"$FAKE_MODE\" != unsupported-hash ] || exit 1\nprintf '$6$capability-fixture\\n'\n")
            busybox.chmod(0o755)
            if mode == "shadow":
                (root / "etc/shadow").touch()
            script = SOURCE.read_text()
            for old, new in [
                ("/data/openssh", root / "openssh"), ("/res/passwd", auth),
                ("/etc/passwd", root / "etc/passwd"), ("/etc/shadow", root / "etc/shadow"),
                ("/var/run/openssh-test.pid", root / "pid"), ("/proc/", str(root / "proc") + "/"),
                ("/tmp/mi-gw2-root-password.lock", root / "lock"),
            ]:
                script = script.replace(old, str(new))
            # Bypass terminal/root checks in this fixture, never in the shipped script.
            script = script.replace('[ -t 0 ]', 'true')
            prefix = 'id() { echo 0; }\nkill() { printf "SIGNAL %s\\n" "$*" >> "$FAKE_ROOT/actions"; return 0; }\n'
            path = root / "test.sh"
            path.write_text(prefix + script)
            env = dict(os.environ, PATH=str(root / "bin") + ":" + os.environ["PATH"], FAKE_ROOT=str(root), FAKE_MODE=mode)
            args = ["sh", str(path)] + (["--check"] if mode == "check" else [])
            p = subprocess.run(args, env=env, text=True, capture_output=True)
            actions = (root / "actions").read_text() if (root / "actions").exists() else ""
            self.assertNotIn("$6$", p.stdout + p.stderr)
            if mode == "good":
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertIn("PermitEmptyPasswords no", config.read_text())
                self.assertNotIn("PermitEmptyPasswords yes", config.read_text())
                self.assertIn("Subsystem sftp internal-sftp", config.read_text())
                self.assertIn("-a sha512 root", actions)
                self.assertIn("SIGNAL -HUP 424242", actions)
                self.assertEqual((root / "openssh/etc/sshd_config.before-root-password").read_text(), original)
            elif mode == "check":
                self.assertEqual(p.returncode, 0)
                self.assertIn("ROOT_AUTH=empty", p.stdout)
                self.assertEqual(actions, "")
            else:
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(config.read_text(), original)
                self.assertNotIn("SIGNAL -HUP", actions)
            self.assertFalse((root / "lock").exists())

    def test_success(self):
        self.exercise()

    def test_read_only_check(self):
        self.exercise("check")

    def test_password_failure_keeps_ssh_config(self):
        self.exercise("password-failed")

    def test_invalid_ssh_config_prevents_password_change(self):
        self.exercise("invalid-config")

    def test_custom_match_rejected(self):
        self.exercise("match")

    def test_unexpected_shadow_rejected(self):
        self.exercise("shadow")

    def test_unsupported_hash_prevents_password_change(self):
        self.exercise("unsupported-hash")


if __name__ == "__main__":
    unittest.main()
