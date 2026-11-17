from pathlib import Path
lab = Path(__file__).resolve().parent
p = lab / "kernel-work/Makefile"
s = p.read_text()
old = "@python scripts/ms_gen_mvxv_h.py"
new = "@python3 scripts/ms_gen_mvxv_h.py"
if old in s:
    backup = p.with_name("Makefile.before-python3")
    if not backup.exists(): backup.write_text(s)
    p.write_text(s.replace(old, new))
    print("Patched BSP version generator to use python3 in independent worktree.")
elif new in s:
    print("BSP Python 3 patch already applied.")
else:
    raise SystemExit("Unexpected BSP Makefile; not modified.")
