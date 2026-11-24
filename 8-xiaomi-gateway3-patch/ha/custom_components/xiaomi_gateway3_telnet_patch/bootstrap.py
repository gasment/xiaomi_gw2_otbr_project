"""Atomic, explicit installation of the parent-package startup hook from the UI."""
import ast
import io
import os
import re
from pathlib import Path
import tempfile
import tokenize

BEGIN = "# BEGIN XIAOMI_GATEWAY3_PASSWORD_PATCH"
END = "# END XIAOMI_GATEWAY3_PASSWORD_PATCH"
BLOCK = "\n".join([
    BEGIN,
    "from .xiaomi_gateway3_telnet_patch.early import install_early_hooks as _gw2_install_password_hooks",
    "_gw2_install_password_hooks()",
    END,
]) + "\n"


class BootstrapError(RuntimeError):
    pass


def install_bootstrap(custom_components):
    directory = Path(custom_components)
    if not directory.is_dir() or directory.is_symlink():
        raise BootstrapError("A writable regular custom_components directory is required")
    path = directory / "__init__.py"
    if path.is_symlink():
        raise BootstrapError("Refusing to replace a symlink bootstrap")
    before = path.read_bytes() if path.exists() else b""
    encoding, _ = tokenize.detect_encoding(io.BytesIO(before).readline)
    text = before.decode(encoding)
    newline = "\r\n" if "\r\n" in text else "\n"
    block = BLOCK.replace("\n", newline)
    if BEGIN in text or END in text:
        if text.count(BEGIN) == 1 and text.count(END) == 1 and block in text:
            return False
        raise BootstrapError("Existing password bootstrap was edited; review it manually")
    try:
        compile(text, str(path), "exec", dont_inherit=True)
        tree = ast.parse(text)
    except SyntaxError:
        raise BootstrapError("Existing custom_components initializer has invalid syntax") from None
    lines = text.splitlines(keepends=True)
    index = 0
    for i, line in enumerate(lines[:2]):
        if (i == 0 and line.startswith("#!")) or re.match(r"^[ \t\f]*#.*?coding[:=]\s*[-\w.]+", line):
            index = i + 1
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            index = max(index, node.end_lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
            index = max(index, node.end_lineno)
        else:
            break
    prefix = "".join(lines[:index])
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += newline
    after = (prefix + block + "".join(lines[index:])).encode(encoding)
    compile(after, str(path), "exec", dont_inherit=True)
    if before:
        backup = directory / "__init__.py.before-gw2-password-patch"
        try:
            with backup.open("xb") as stream:
                stream.write(before)
        except FileExistsError:
            pass
    with tempfile.NamedTemporaryFile(prefix=".gw2-bootstrap-", dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(after)
    try:
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        if path.exists() and path.read_bytes() != before:
            raise BootstrapError("Initializer changed concurrently; retry installation")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True
