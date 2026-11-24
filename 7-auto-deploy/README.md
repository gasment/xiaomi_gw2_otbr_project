# Windows 图形化部署

当前自动部署入口是 Python 单文件程序：

```text
MiGateway2AutoDeploy-0.3.2.exe
```

程序运行在 Windows，不需要目标电脑安装 Python、PowerShell 模块或 FTP 工具。网关侧业务仍使用各部件 `deploy` 目录中各自版本的安装包。

## 使用

1. 从 Release 下载 `MiGateway2AutoDeploy-0.3.2.exe` 和对应的 `.sha256` 文件。
2. 可选地核对文件哈希：

   ```powershell
   (Get-FileHash .\MiGateway2AutoDeploy-0.3.2.exe -Algorithm SHA256).Hash.ToLower()
   ```

3. 启动 EXE，接受管理员权限提示。
4. 输入网关 IP、Telnet 端口和 root 密码，点击“连接并刷新”。
5. 选择需要安装的组件，执行一键部署。
6. 需要修改 OTBR 配置时，使用界面中的 YAML 上传功能写入 `/data/otbr/config.yaml`。
7. 部署完成后检查 OTBR 状态、HA 自动发现和实际业务数据。

刷写 RCP 前，应先停用 HA 中 Xiaomi Gateway 3 对目标网关的串口占用。恢复原厂 Zigbee 固件后，原厂 Zigbee 应用会重新使用无线串口。

## 组件范围

- OpenSSH
- TUN
- BLE Spec Cache
- OTBR/RCP 软件栈，包含 Host、Web、Native API、RCP 隔离及 openmiio 共存。随 OTBR 更新部署配套资源。

界面会区分组件的“已安装”和“已运行”状态，并提供单独卸载、配置上传、重启后重连验证以及原厂恢复。

## 源码与构建

源码、开发运行和单文件构建说明见：

```text
gui-python/README.md
```

构建脚本从项目各部件 `deploy` 目录汇集并校验运行资源，不依赖额外的 Windows 部署 ZIP。
