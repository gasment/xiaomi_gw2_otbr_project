from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import GatewayApp
from engine import ComponentStatus


def test_ui_smoke() -> None:
    app = GatewayApp()
    app.withdraw()
    app.update_idletasks()
    app.cards["openssh"].update_status(ComponentStatus("yes", "yes"))
    app.update_idletasks()
    assert app.cards["openssh"].install_state.cget("text") == "安装：是"
    assert app.cards["openssh"].run_state.cget("text") == "运行：是"
    assert any(getattr(widget, "cget", lambda _: "")("text") == "卸载并清理" for widget in app.action_widgets)
    assert "Xiaomi Gateway 2 OTBR 0.3.0" in app.title()
    assert app.ip_var.get() == ""
    assert app.connect_button.cget("text") == "连接并刷新"
    app.destroy()


if __name__ == "__main__":
    test_ui_smoke()
    print("UI_SMOKE_TEST_PASS")
