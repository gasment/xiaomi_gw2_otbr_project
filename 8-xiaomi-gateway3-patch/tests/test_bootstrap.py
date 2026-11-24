import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1] / "ha/custom_components/xiaomi_gateway3_telnet_patch"
spec = importlib.util.spec_from_file_location("gw2_bootstrap_test", CODE / "bootstrap.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BootstrapTests(unittest.TestCase):
    def test_create_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(module.install_bootstrap(directory))
            p = Path(directory) / "__init__.py"
            before = p.read_bytes()
            self.assertFalse(module.install_bootstrap(directory))
            self.assertEqual(p.read_bytes(), before)
            ast.parse(before)

    def test_preserve_future_docstring_and_existing_code(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "__init__.py"
            before = '# coding: utf-8\n"""Existing initializer."""\nfrom __future__ import annotations\nVALUE = 7\n'
            p.write_text(before)
            module.install_bootstrap(directory)
            text = p.read_text()
            self.assertLess(text.index("from __future__"), text.index(module.BEGIN))
            self.assertLess(text.index(module.END), text.index("VALUE = 7"))
            self.assertEqual((Path(directory) / "__init__.py.before-gw2-password-patch").read_text(), before)
            ast.parse(text)

    def test_edited_marker_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "__init__.py"
            p.write_text(module.BEGIN + "\n# user edited\n" + module.END + "\n")
            before = p.read_bytes()
            with self.assertRaises(module.BootstrapError):
                module.install_bootstrap(directory)
            self.assertEqual(p.read_bytes(), before)

    def test_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "other.py"
            target.write_text("VALUE = 1\n")
            (Path(directory) / "__init__.py").symlink_to(target)
            with self.assertRaises(module.BootstrapError):
                module.install_bootstrap(directory)
            self.assertEqual(target.read_text(), "VALUE = 1\n")

    def test_crlf_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "__init__.py"
            p.write_bytes(b"VALUE = 1\r\n")
            module.install_bootstrap(directory)
            data = p.read_bytes()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
            self.assertFalse(module.install_bootstrap(directory))

    def test_invalid_existing_code_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "__init__.py"
            p.write_text("broken (\n")
            with self.assertRaises(module.BootstrapError):
                module.install_bootstrap(directory)
            self.assertEqual(p.read_text(), "broken (\n")


if __name__ == "__main__":
    unittest.main()
