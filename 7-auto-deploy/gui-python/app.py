from __future__ import annotations

import ctypes
import ipaddress
import os
import queue
import threading
import time
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageTk

from engine import AutoDeployEngine, ComponentStatus, DeployOptions
from resources import VERSION, icon_path, resolve_assets

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "window": "#0b1220",
    "sidebar": "#101a2c",
    "card": "#152238",
    "card_alt": "#192943",
    "border": "#263a59",
    "text": "#eef5ff",
    "muted": "#94a6c2",
    "accent": "#4ea1ff",
    "accent_hover": "#6bb3ff",
    "green": "#50d890",
    "orange": "#f2b84b",
    "red": "#ff6b7a",
    "action_green": "#1e8a53",
    "action_green_hover": "#25a264",
    "action_orange": "#a65512",
    "action_orange_hover": "#bf6617",
    "action_red": "#c02028",
    "action_red_hover": "#db292f",
}


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class ComponentCard(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        key: str,
        title: str,
        subtitle: str,
        variable: ctk.BooleanVar,
    ) -> None:
        super().__init__(master, fg_color=COLORS["card"], corner_radius=16)
        self.key = key
        self.grid_columnconfigure(0, weight=1)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text=title,
            variable=variable,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        self.checkbox.grid(row=0, column=0, sticky="w", padx=16, pady=(15, 4))
        ctk.CTkLabel(
            self,
            text=subtitle,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=330,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self.install_state = self._state_pill("安装：未检查")
        self.install_state.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 6))
        self.run_state = self._state_pill("运行：未检查")
        self.run_state.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 15))

    def _state_pill(self, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            self,
            text=text,
            height=25,
            corner_radius=12,
            fg_color=COLORS["card_alt"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        )

    def update_status(self, status: ComponentStatus) -> None:
        install_map = {"yes": "是", "partial": "部分", "no": "否"}
        run_map = {"yes": "是", "waiting": "等待", "no": "否"}
        installed = install_map.get(status.installed, "未知")
        running = run_map.get(status.running, "未知")
        install_text = f"安装：{installed}"
        if status.installed == "yes":
            install_text += f" · {status.installed_version or '版本未知'}"
            if status.upgrade_version:
                install_text += f" · 可升级 {status.upgrade_version}"
        self.install_state.configure(
            text=install_text,
            fg_color=COLORS["green"] if status.installed == "yes" else COLORS["card_alt"],
            text_color=COLORS["window"] if status.installed == "yes" else COLORS["muted"],
        )
        if status.running == "yes":
            run_color = COLORS["green"]
            run_text_color = COLORS["window"]
        elif status.running == "waiting":
            run_color = COLORS["orange"]
            run_text_color = COLORS["window"]
        else:
            run_color = COLORS["card_alt"]
            run_text_color = COLORS["muted"]
        self.run_state.configure(
            text=f"运行：{running}",
            fg_color=run_color,
            text_color=run_text_color,
        )


class GatewayApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Xiaomi Gateway 2 OTBR {VERSION} - 组件管理")
        self.configure(fg_color=COLORS["window"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.assets = resolve_assets()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.busy = False
        self.engine: AutoDeployEngine | None = None
        self.log_path = self._create_log_path()

        self.component_vars = {
            "openssh": ctk.BooleanVar(value=False),
            "tun": ctk.BooleanVar(value=False),
            "ble-cache": ctk.BooleanVar(value=False),
            "otbr": ctk.BooleanVar(value=False),
        }
        self.cards: dict[str, ComponentCard] = {}
        self.action_widgets: list[ctk.CTkBaseClass] = []

        self._build_ui()
        self._set_icon()
        self.after(80, self._drain_events)
        self.log(f"GUI {VERSION} ready")
        self.log(f"Log: {self.log_path}")
        self.log("双击刷新状态后，组件卡片会显示安装与运行状态。")

    def _create_log_path(self) -> Path:
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MiGateway2AutoDeploy" / "logs"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"gui-{time.strftime('%Y%m%d-%H%M%S')}.txt"

    def _set_icon(self) -> None:
        path = icon_path()
        if path:
            try:
                image = Image.open(path).convert("RGBA").resize((48, 48), Image.Resampling.LANCZOS)
                self._window_icon = ImageTk.PhotoImage(image)
                self.iconphoto(True, self._window_icon)
            except Exception:
                pass

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=252, corner_radius=0, fg_color=COLORS["sidebar"])
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        logo_path = icon_path()
        if logo_path:
            image = Image.open(logo_path)
            self.logo = ctk.CTkImage(light_image=image, dark_image=image, size=(72, 72))
            ctk.CTkLabel(sidebar, text="", image=self.logo).grid(row=0, column=0, pady=(28, 8))
        ctk.CTkLabel(
            sidebar,
            text="Xiaomi Gateway 2",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=1, column=0)
        ctk.CTkLabel(
            sidebar,
            text="OTBR 组件管理",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["muted"],
        ).grid(row=2, column=0, pady=(0, 26))
        ctk.CTkLabel(
            sidebar,
            text=f"GUI VERSION {VERSION}",
            height=28,
            corner_radius=14,
            fg_color=COLORS["card_alt"],
            text_color=COLORS["accent"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=3, column=0, padx=48, sticky="ew")

        self.connection_state = ctk.CTkLabel(
            sidebar,
            text="未连接",
            height=34,
            corner_radius=17,
            fg_color=COLORS["card"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.connection_state.grid(row=4, column=0, padx=28, pady=(24, 8), sticky="ew")
        self.admin_state = ctk.CTkLabel(
            sidebar,
            text="管理员权限：是" if is_admin() else "管理员权限：否",
            text_color=COLORS["green"] if is_admin() else COLORS["orange"],
            font=ctk.CTkFont(size=11),
        )
        self.admin_state.grid(row=5, column=0, pady=(0, 20))
        self.system_state = ctk.CTkLabel(
            sidebar,
            text="固件：未读取\n内核：未读取",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=10),
            justify="left",
            wraplength=208,
        )
        self.system_state.grid(row=6, column=0, padx=22, sticky="w")

        ctk.CTkLabel(
            sidebar,
            text="操作提示",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=7, column=0, padx=22, pady=(18, 0), sticky="w")
        ctk.CTkLabel(
            sidebar,
            text="先刷新状态，再勾选组件。\nOTBR 会自动包含 TUN、RCP mode\n和 RCP/openmiio。",
            justify="left",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=8, column=0, padx=22, pady=(8, 18), sticky="w")

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=24, pady=22)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        controls = ctk.CTkFrame(main, width=720, fg_color="transparent")
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 20))
        controls.grid_propagate(False)
        controls.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(controls, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="组件管理",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="安全部署、状态检查和原厂恢复",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        connection = ctk.CTkFrame(controls, fg_color=COLORS["card"], corner_radius=16)
        connection.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        connection.grid_columnconfigure(5, weight=1)
        ctk.CTkLabel(connection, text="网关 IP", text_color=COLORS["muted"]).grid(row=0, column=0, padx=(18, 8), pady=16)
        self.ip_var = ctk.StringVar(value="")
        self.ip_entry = self._entry(
            connection,
            self.ip_var,
            width=130,
            placeholder="输入网关 IPv4",
        )
        self.ip_entry.grid(row=0, column=1, padx=(0, 16), pady=16)
        ctk.CTkLabel(connection, text="Telnet", text_color=COLORS["muted"]).grid(row=0, column=2, padx=(0, 8), pady=16)
        self.port_var = ctk.StringVar(value="23")
        self.port_entry = self._entry(connection, self.port_var, width=72)
        self.port_entry.grid(row=0, column=3, padx=(0, 16), pady=16)
        ctk.CTkLabel(connection, text="root 密码", text_color=COLORS["muted"]).grid(row=0, column=4, padx=(0, 8), pady=16)
        self.password_var = ctk.StringVar()
        self.password_entry = self._entry(connection, self.password_var, width=112, show="*")
        self.password_entry.grid(row=0, column=5, sticky="ew", padx=(0, 10), pady=16)
        self.connect_button = ctk.CTkButton(
            connection,
            text="连接并刷新",
            width=112,
            height=34,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.connect_and_refresh,
        )
        self.connect_button.grid(row=0, column=6, padx=(0, 18), pady=16)
        self.action_widgets.append(self.connect_button)
        self.password_entry.bind("<Return>", lambda _event: self.connect_and_refresh())

        cards = ctk.CTkFrame(controls, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        for column in (0, 1):
            cards.grid_columnconfigure(column, weight=1, uniform="component")
        descriptions = {
            "openssh": ("OpenSSH", "端口 2223，支持 SFTP"),
            "tun": ("TUN 驱动", "IPv6 用户态虚拟网卡"),
            "ble-cache": ("BLE Spec Cache", "openmiio 离线产品规则缓存"),
            "otbr": ("OTBR / RCP 软件栈", "OTBR Host、RCP mode 与 openmiio"),
        }
        for index, key in enumerate(("openssh", "tun", "ble-cache", "otbr")):
            card = ComponentCard(
                cards,
                key,
                descriptions[key][0],
                descriptions[key][1],
                self.component_vars[key],
            )
            card.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=(0, 8) if index % 2 == 0 else (8, 0),
                pady=(0, 16) if index < 2 else 0,
            )
            self.cards[key] = card

        options = ctk.CTkFrame(controls, fg_color=COLORS["card"], corner_radius=16)
        options.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(
            options,
            text="可选项",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["muted"],
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(8, 0), sticky="w")
        self.reboot_var = ctk.BooleanVar(value=True)
        self.full_restore_var = ctk.BooleanVar(value=True)
        self.flash_rcp_var = ctk.BooleanVar(value=True)
        for index, (text, var) in enumerate(
            (
                ("操作完成后重启网关", self.reboot_var),
                ("恢复出厂时，刷回Zigbee固件（实验性）", self.full_restore_var),
                ("安装OTBR时自动刷入RCP固件", self.flash_rcp_var),
            )
        ):
            ctk.CTkCheckBox(
                options,
                text=text,
                variable=var,
                text_color=COLORS["text"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
            ).grid(row=1 + index // 2, column=index % 2, padx=16, pady=(4, 8), sticky="w")

        actions = ctk.CTkFrame(controls, fg_color=COLORS["card"], corner_radius=16)
        actions.grid(row=4, column=0, sticky="ew")
        buttons = [
            ("刷新状态", self.refresh_status, COLORS["action_green"], COLORS["action_green_hover"]),
            ("部署所选", self.deploy_selected, "#2f7bff", "#4c91ff"),
            ("更新 OTBR 配置", self.update_config, COLORS["action_green"], COLORS["action_green_hover"]),
            ("卸载并清理", self.uninstall_selected, COLORS["action_orange"], COLORS["action_orange_hover"]),
            ("恢复原厂", self.restore_stock, COLORS["action_red"], COLORS["action_red_hover"]),
        ]
        for column, (text, callback, fg, hover) in enumerate(buttons):
            button = ctk.CTkButton(
                actions,
                text=text,
                command=callback,
                fg_color=fg,
                hover_color=hover,
                width=100,
                height=38,
                corner_radius=11,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text"],
            )
            button.grid(row=0, column=column, padx=(16 if column == 0 else 6, 6), pady=14, sticky="ew")
            actions.grid_columnconfigure(column, weight=1)
            self.action_widgets.append(button)

        log_card = ctk.CTkFrame(main, fg_color=COLORS["card"], corner_radius=16)
        log_card.grid(row=0, column=1, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(2, weight=1)
        log_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        log_header.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(
            log_header,
            text="就绪",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ctk.CTkProgressBar(log_card, progress_color=COLORS["accent"])
        self.progress.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress.set(0)
        ctk.CTkButton(
            log_header,
            text="清空",
            width=64,
            height=26,
            fg_color=COLORS["card_alt"],
            hover_color=COLORS["border"],
            command=lambda: self.logbox.delete("1.0", "end"),
        ).grid(row=0, column=1, padx=(8, 0))
        self.logbox = ctk.CTkTextbox(
            log_card,
            corner_radius=0,
            fg_color="#0b1322",
            text_color="#c7d4e7",
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
        )
        self.logbox.grid(row=2, column=0, sticky="nsew", padx=1, pady=(0, 1))

        # Measure the complete controls area after Tk lays out the action row.
        self.update_idletasks()
        vertical_margin = int(main.grid_info()["pady"])
        pixel_height = controls.grid_bbox()[3] + 2 * vertical_margin
        window_height = self._reverse_window_scaling(pixel_height)
        if self._apply_window_scaling(window_height) < pixel_height:
            window_height += 1
        window_width = 1392
        self.geometry(f"{window_width}x{window_height}")
        self.minsize(window_width, window_height)
        self.resizable(True, False)

    @staticmethod
    def _entry(
        master: ctk.CTkBaseClass,
        variable: ctk.Variable,
        width: int,
        show: str | None = None,
        placeholder: str = "",
    ) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            master,
            textvariable=variable,
            width=width,
            height=34,
            show=show,
            placeholder_text=placeholder,
            fg_color="#0d1728",
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )

    def log(self, text: str) -> None:
        if threading.current_thread() is threading.main_thread():
            self._append_log(text)
        else:
            self.events.put(("log", text))

    def _append_log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        self.logbox.insert("end", line + "\n")
        self.logbox.see("end")
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _set_busy(self, busy: bool, text: str | None = None) -> None:
        self.busy = busy
        for widget in self.action_widgets:
            widget.configure(state="disabled" if busy else "normal")
        for card in self.cards.values():
            card.checkbox.configure(state="disabled" if busy else "normal")
        if text:
            self.status_label.configure(text=text)
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)

    def _connection_values(self) -> tuple[str, int, str]:
        host = self.ip_var.get().strip()
        ipaddress.ip_address(host)
        port = int(self.port_var.get().strip())
        if not 1 <= port <= 65535:
            raise ValueError("Telnet 端口无效。")
        return host, port, self.password_var.get()

    def _require_admin(self) -> bool:
        if is_admin():
            return True
        messagebox.showerror("需要管理员权限", "部署、恢复和端口转发需要管理员权限。")
        return False

    def _selected(self) -> set[str]:
        selected = {key for key, var in self.component_vars.items() if var.get()}
        if "otbr" in selected:
            selected.add("tun")
        return selected

    def _deploy_options(self) -> DeployOptions:
        return DeployOptions(
            reboot=bool(self.reboot_var.get()),
            full_restore=bool(self.full_restore_var.get()),
            flash_rcp=bool(self.flash_rcp_var.get()),
        )

    def _ask_from_worker(self, title: str, text: str) -> bool:
        if threading.current_thread() is threading.main_thread():
            return messagebox.askyesno(title, text)
        event = threading.Event()
        result: dict[str, bool] = {}
        self.events.put(("ask", title, text, result, event))
        event.wait()
        return result.get("value", False)

    def _start_operation(self, label: str, action: Callable[[AutoDeployEngine], str | None], require_admin: bool = False) -> None:
        if self.busy:
            return
        if require_admin and not self._require_admin():
            return
        try:
            host, port, password = self._connection_values()
        except Exception as exc:
            messagebox.showerror("连接参数错误", str(exc))
            return

        self._set_busy(True, label)
        self.connection_state.configure(
            text=f"连接中 {host}",
            fg_color=COLORS["card_alt"],
            text_color=COLORS["orange"],
        )

        def worker() -> None:
            engine = AutoDeployEngine(
                self.assets,
                host,
                port,
                password,
                self.log,
                self._ask_from_worker,
            )
            try:
                engine.connect()
                self.events.put(("connected",))
                outcome = action(engine)
                self.events.put(("done", outcome or "操作完成"))
            except Exception as exc:
                self.log("ERROR: " + str(exc))
                self.events.put(("error", "操作失败", str(exc)))
            finally:
                engine.close()

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def refresh_status(self) -> None:
        def action(engine: AutoDeployEngine) -> None:
            statuses = engine.status()
            self.events.put(("status", statuses, dict(engine.system_info)))

        self._start_operation("正在刷新组件状态...", action)

    def connect_and_refresh(self) -> None:
        self.refresh_status()

    def deploy_selected(self) -> None:
        selected = self._selected()
        if not selected:
            messagebox.showwarning("未选择组件", "请至少选择一个组件。")
            return
        options = self._deploy_options()
        self._start_operation(
            "正在部署所选组件...",
            lambda engine: engine.deploy(selected, options),
            require_admin=True,
        )

    def uninstall_selected(self) -> None:
        selected = self._selected()
        if not selected:
            messagebox.showwarning("未选择组件", "请至少选择一个组件。")
            return
        if not messagebox.askyesno(
            "卸载并清理",
            "将停止所选组件，并删除对应的程序、配置、缓存和运行文件。\n\n"
            "OpenSSH 会同时移除 sshd 服务账户；root 当前密码会保留。\n"
            "共享 openmiio 运行时不会因单独卸载 BLE 或 OTBR 而删除。\n\n"
            "继续吗？",
        ):
            return
        options = self._deploy_options()
        self._start_operation(
            "正在卸载所选组件...",
            lambda engine: engine.uninstall(selected, options),
            require_admin=True,
        )

    def restore_stock(self) -> None:
        options = self._deploy_options()
        self._start_operation(
            "正在恢复原厂状态...",
            lambda engine: engine.restore_stock(options),
            require_admin=True,
        )

    def update_config(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 OTBR YAML 配置",
            filetypes=[("YAML 文件", "*.yaml *.yml"), ("所有文件", "*.*")],
        )
        if not path:
            return
        selected = os.path.abspath(path)
        self._start_operation(
            "正在上传 OTBR 配置...",
            lambda engine: engine.upload_yaml(Path(selected)),
        )

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1])
                elif kind == "connected":
                    self.connection_state.configure(
                        text=f"已连接 {self.ip_var.get().strip()}",
                        fg_color="#173524",
                        text_color=COLORS["green"],
                    )
                elif kind == "status":
                    statuses: dict[str, ComponentStatus] = event[1]
                    info: dict[str, str] = event[2]
                    for key, status in statuses.items():
                        if key in self.cards:
                            self.cards[key].update_status(status)
                    self.system_state.configure(
                        text=(
                            f"固件：{info.get('firmware', 'unknown')}\n"
                            f"内核：{info.get('kernel', 'unknown')}"
                        )
                    )
                elif kind == "ask":
                    _, title, text, result, finished = event
                    result["value"] = messagebox.askyesno(title, text)
                    finished.set()
                elif kind == "done":
                    self._set_busy(False, event[1])
                elif kind == "error":
                    self._set_busy(False, "操作失败")
                    self.connection_state.configure(
                        text="连接或操作失败",
                        fg_color="#3b1e27",
                        text_color=COLORS["red"],
                    )
                    messagebox.showerror(event[1], event[2])
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _on_close(self) -> None:
        if self.engine:
            self.engine.close()
        self.destroy()


def main() -> None:
    app = GatewayApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        details = traceback.format_exc()
        log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MiGateway2AutoDeploy" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "startup-crash.log").write_text(details, encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror("GUI 启动失败", details)
        except Exception:
            if os.name == "nt":
                try:
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        details,
                        "MiGateway2AutoDeploy 启动失败",
                        0x10,
                    )
                except Exception:
                    pass
