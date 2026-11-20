# Xiaomi Gateway 2 OTBR Python GUI 0.3.0

使用 Python、CustomTkinter 和 PyInstaller 重构的 Windows 管理端。发布版本是无控制台、请求管理员权限的单文件 `MiGateway2AutoDeploy.exe`。

## 功能

- 刷新 OpenSSH、TUN、BLE Spec Cache、OTBR/RCP 的安装与运行状态；
- root 密码右侧提供“连接并刷新”，登录成功后立即读取一次组件状态；
- 一键部署所选组件；“卸载并清理”会删除对应程序、配置、缓存和运行文件；
- OTBR/RCP 自动探测和固件刷写；
- 上传或覆盖网关 `/data/otbr/config.yaml`；
- 软恢复原厂启动或完整恢复原厂 Zigbee；
- 重启后自动重连并复查 SSH 或出厂清理结果；
- 日志同步显示并保存到 `%LOCALAPPDATA%\MiGateway2AutoDeploy\logs`。

## 开发运行

PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

源码模式下，程序优先使用同目录 `assets`；没有 `assets` 时直接从项目各部件 `deploy` 目录汇集并校验资源。

## 单文件构建

在完整项目的 `auto-deploy/gui-python` 目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

构建脚本优先使用 `-AssetsDirectory`；未指定时从各部件 `deploy` 目录汇集资源。因此仓库不需要重复保存一份组件资源。

输出：

```text
deploy/MiGateway2AutoDeploy-0.3.0.exe
deploy/MiGateway2AutoDeploy-0.3.0.exe.sha256
```

PyInstaller 会把 Python、Tcl/Tk、CustomTkinter、Pillow、图标和全部部署资源打入单文件。构建不依赖目标电脑安装 Python。

## RCP 中断标记

`/data/mi-gw2-gui/rcp-flash-in-progress` 表示上一次刷写没有正常完成验证，并不代表当前固件仍是 RCP。部署 OTBR 时程序先执行 Spinel 探测：RCP 已正常响应时自动清除过期标记；探测失败时，只有用户明确确认已通过原生流程恢复为已知 NCP 后，才允许清除并继续。

## 边界

- 组件程序和协议仍使用项目已验收的 shell 包；
- Windows 防火墙规则只在传输期间存在；
- root 密码不写入配置或日志；
- Telnet 为明文协议，仅在可信局域网使用。
