from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import COLORS, GatewayApp
from engine import ComponentStatus
from resources import VERSION


def test_ui_smoke() -> None:
    app = GatewayApp()
    app.withdraw()
    widgets = [app]
    for widget in widgets:
        widgets.extend(widget.winfo_children())
        if isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkEntry, ctk.CTkLabel, ctk.CTkTextbox)):
            if isinstance(widget, ctk.CTkLabel) and not widget.cget("text"):
                continue
            expected = "Consolas" if widget is app.logbox else "Microsoft YaHei UI"
            assert widget.cget("font").cget("family") == expected
    app.update_idletasks()
    app.cards["openssh"].update_status(ComponentStatus("yes", "yes", "0.3.9", "0.3.10"))
    app.update_idletasks()
    assert app.cards["openssh"].install_state.cget("text") == "安装：是 · 0.3.9 · 可升级 0.3.10"
    assert app.cards["openssh"].run_state.cget("text") == "运行：是"
    actions = [(widget.cget("text"), widget.cget("fg_color")) for widget in app.action_widgets[1:]]
    assert actions == [
        ("刷新状态", COLORS["action_green"]),
        ("部署所选", "#2f7bff"),
        ("更新 OTBR 配置", COLORS["action_green"]),
        ("卸载并清理", COLORS["action_orange"]),
        ("恢复原厂", COLORS["action_red"]),
    ]
    assert f"Xiaomi Gateway 2 OTBR {VERSION}" in app.title()
    assert app.ip_var.get() == ""
    assert app.connect_button.cget("text") == "连接并刷新"
    app.deiconify()
    app.update()
    log_panel = app.logbox.master
    main = log_panel.master
    cards = list(app.cards.values())
    card_widths = [card.winfo_width() for card in cards]
    log_width = log_panel.winfo_width()
    window_width = app.winfo_width()
    window_height = app.winfo_height()
    logical_height = app.geometry().split("+", 1)[0].split("x")[1]
    actions = app.action_widgets[-1].master

    assert tuple(map(int, app.resizable())) == (1, 0)
    assert all(abs(width - log_width) <= 2 for width in card_widths)
    for width in (1392, 1480, 1600):
        app.geometry(f"{width}x{logical_height}")
        app.update()
        assert [card.winfo_width() for card in cards] == card_widths
        assert log_panel.winfo_width() - log_width == app.winfo_width() - window_width
        assert app.winfo_height() == window_height
        assert log_panel.winfo_x() > cards[0].master.master.winfo_x()
        assert log_panel.winfo_y() == 0
        assert log_panel.winfo_height() == main.winfo_height()
        actions_bottom = actions.winfo_rooty() + actions.winfo_height()
        log_bottom = log_panel.winfo_rooty() + log_panel.winfo_height()
        assert 0 <= log_bottom - actions_bottom <= 2
        window_bottom = app.winfo_rooty() + window_height
        assert abs(window_bottom - actions_bottom - int(main.grid_info()["pady"])) <= 2
        assert app.logbox.winfo_height() >= 0.8 * log_panel.winfo_height()
        assert log_panel.winfo_x() + log_panel.winfo_width() == main.winfo_width()
        connection = app.connect_button.master
        assert app.connect_button.winfo_x() + app.connect_button.winfo_width() <= connection.winfo_width()
    app.destroy()


if __name__ == "__main__":
    test_ui_smoke()
    print("UI_SMOKE_TEST_PASS")
