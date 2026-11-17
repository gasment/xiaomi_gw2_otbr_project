# Windows 一键部署

普通用户只需要 Windows 自带的 PowerShell 5.1 和本地网络，**不需要 Python、FTP 软件或手工登录 Telnet**。


当前发布件验证基线为原厂 **1.0.8_0004** 及包内锁定的完整内核构建标识。**1.0.3_0028 不在当前验证范围**；仅同为 Linux 4.9.84 不足以通过 TUN 检查。`check` 会先核对精确内核和原厂脚本，失败时显示实际与目标信息，不加载模块或刷写。

## 使用方法

1. 下载 `mi-gw2-windows-deploy-0.2.5.zip` 并解压到 Windows 本地目录。
2. 先暂时停用 HA Xiaomi Gateway 3 中对应的网关条目，避免原 Zigbee 串口被重新占用。
3. 在解压目录打开终端，执行一条命令，将 `GATEWAY_ADDRESS` 换成网关 IPv4：

```bat
.\Deploy-Gateway.cmd GATEWAY_ADDRESS
```

也可双击 `Deploy-Gateway.cmd`，根据提示输入 IP。如果需要创建临时防火墙规则，脚本会请求 Windows 管理员权限；请允许系统 UAC 提示。部署期间保持电脑与网关联网，不要关闭部署窗口。

脚本会自动完成：本地包校验 → 启动临时只读 FTP → root 空密码 Telnet 登录 → 控制网关 wget 从电脑拉包 → 网关校验 → 按顺序安装 → RCP 验证 → 重启 → 限时重连 → 跟踪／启动续装 → 核对最终安装文件。

临时 FTP 默认使用电脑 TCP 2121 / 2122，访问仅允许目标网关 IP，文件仅限当前完整包及其校验文件；使用随机临时凭据，不提供上传、删除或任意目录浏览。部署结束或失败后关闭 FTP 并删除本次创建的防火墙规则。已有防火墙规则不会被修改。

默认整体时间上限 20 分钟，重连间隔 5 秒。高级参数直接传给 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Deploy-Gateway.ps1 -Gateway GATEWAY_ADDRESS -TimeoutMinutes 30
```

有多个网卡时，可增加 `-LocalAddress PC_LAN_ADDRESS` 指定网关能访问的电脑 IPv4；FTP 控制端口可用 `-FtpPort` 修改，数据端口为该值加一。`-NoFirewallRule` 仅供已自行放行端口的环境使用，不会自动提权。

## 状态与故障处理

脚本会显示当前部署阶段。重启后会持续限时尝试 Telnet 登录，等待原厂启动及 RCP 隔离就绪，再跟踪续装。已有匹配进度时可重新运行同一条命令继续；不会自动重刷状态不明的无线模块，也不会把普通已改造网关当成原厂设备重新安装。

完成后仍需用户在网关编辑 `/data/otbr/config.yaml` 及需要的 `secrets.yaml`，填入自己的 Thread Dataset，然后执行 `check.sh`、`restart.sh` 并验证实际接入。脚本只会报告文件／启动链校验完成，不会将其当成 Thread 已入网。

## 无安装验证

下面命令会进行真实 Telnet 登录、FTP 拉包及 SHA256 校验，**不会解压、安装、访问 UART 或重启**：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Deploy-Gateway.ps1 -Gateway GATEWAY_ADDRESS -TransportTest
```

增加 `-CheckOnly` 则会拉包、解压并执行原厂首次安装前置检查，但仍不安装或刷写。当前已安装本项目的网关可能因首次安装容量门槛而无法通过此检查，不应改用正式安装绕过。

本地回环协议／模拟重启测试，无需网关或管理员权限：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Deploy-Gateway.ps1 -SelfTest
```

Windows 5.1 协议与模拟重启续装测试、真实网关 Telnet／FTP 拉包校验已验证。完整原厂机安装和真实重启续装仍需实机验收。

---

# 维护者打包与网关手动上传入口

本流程适用于尚未安装本项目部件的原厂小米多模网关 2。无需网关访问 GitHub 或使用 HTTPS 下载；整个流程使用本地上传文件。

## 准备 Release 文件

在项目根目录执行：

```sh
python3 tools/prepare-release.py
```

输出在项目同级的 `release` 目录，不进入 GitHub 源码目录。目录包含七个部件发布包、spinel-probe、openmiio 依赖、完整自动部署包和 SHA256 清单。部件包沿用 deploy 中的已验证字节，不重新编译。

## 网关部署

前提：已取得 root Telnet / FTP 访问权限，确认目标硬件及原厂系统匹配；先暂时停用 HA Xiaomi Gateway 3 中该网关条目，避免它在刷写期间重新占用串口。保留 root 空密码。

将 `mi-gw2-auto-deploy-0.2.5.tar.gz` 以及对应 `.sha256` 文件上传到网关 `/tmp`。在 Telnet 中逐行执行：

```sh
cd /tmp
sha256sum -c mi-gw2-auto-deploy-0.2.5.tar.gz.sha256
tar -xzf mi-gw2-auto-deploy-0.2.5.tar.gz
sh /tmp/mi-gw2-auto-deploy/install.sh check
sh /tmp/mi-gw2-auto-deploy/install.sh install
```

`check` 只读检查本地包、型号、内核版本、工具和空间，不安装、不访问 UART。首次部署建议 `/data` 至少空闲 40000 KiB、`/tmp` 至少空闲 28000 KiB；完整内核构建字符串和原厂启动脚本在安装前再次精确校验。

`install` 将自动完成以下步骤：

1. 校验所有外层资源以及各部件包内部的文件清单。
2. 安装 OpenSSH、TUN，检查已安装文件并执行真实 IPv6 TUN 双向测试。
3. 暂停原厂 Zigbee 串口使用者，先安装下次启动的 Zigbee 隔离，再通过网关本机工具刷入 RCP，并读取 Spinel 版本验证。
4. 将余下约 4 MiB 的资源和状态保存在 `/data/mi-gw2-auto`，安装一次性续装入口，自动重启网关一次。Telnet / SSH 连接会断开。
5. 重启后恢复普通 RCP 启动链、确认串口隔离和 RCP 响应，再自动安装 BLE/openmiio 和完整 OTBR Host。
6. 核对 45 个公开驻留文件及最终启动入口；清理续装资源缓存，保留日志和进度。

此操作会用 Thread RCP 替换原厂 Zigbee 应用。部署过程中失败即停止，刷写已开始但未确认完成时不会自动重刷。已有本项目部件或未知启动包装的设备不走首次自动部署，继续使用各部件的手动升级流程。

如希望自行决定重启时机，可用下面一条替代 `install`：

```sh
sh /tmp/mi-gw2-auto-deploy/install.sh install --no-reboot
```

脚本会停在等待重启阶段；随后手动执行 `reboot`，仍会在启动后自动续装。

## 重启后的状态与配置

重连网关后执行：

```sh
sh /data/mi-gw2-auto/install.sh status
cat /data/mi-gw2-auto/resume.log
```

`STAGE=complete` 表示部署文件与启动链验证完成，不代表已附着 Thread。首次安装需要由用户在网关编辑 `/data/otbr/config.yaml` 及需要的 `secrets.yaml`，填写自己的 Thread 网络配置，然后执行：

```sh
sh /data/otbr/check.sh
sh /data/otbr/restart.sh
sh /data/otbr/status.sh
```

配置由网关用户维护，自动部署包不携带实际 Dataset、HA Token 或 SSH 私钥。配置有效但尚未完成业务验证时也不会伪报 Thread 接入成功。确认部署完成后重新启用 HA 网关条目，并确认蓝牙设备收到新状态。

再次只读核对部署文件：

```sh
sh /data/mi-gw2-auto/install.sh verify
```

如果重启后的续装因临时条件失败，先查看 `/data/mi-gw2-auto/resume.log` 和 `last-step.log`，排除原因后执行：

```sh
sh /data/mi-gw2-auto/install.sh resume
```

`radio-in-progress` 状态必须人工检查无线模块／bootloader 并使用原生恢复包处理；脚本不会自动覆盖不明刷写状态。其他未知启动链、包损坏、文件不匹配或 UART 占用同样不会被强行跳过。

本流程在本地进行脚本和模拟流程校验；在真实原厂设备上完成一次完整安装和重启续装前，不视作整机自动部署验收通过。
