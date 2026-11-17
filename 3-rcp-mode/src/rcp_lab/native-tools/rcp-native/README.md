# 小米多模网关 2：网关本机刷入 RCP / 刷回 Zigbee

这份说明是本机刷写流程。刷写程序、RCP 镜像和 Zigbee 回退镜像都放在网关，直接通过 `/dev/ttyS1` 通信；实际刷写不需要 WSL、Python、TCP 串口桥或另一台 Linux 主机。WSL 仅在最初构建 ARM 工具时使用。

## 当前验证范围

- 已验证本机原厂 NCP 为 EmberZNet 6.6.6.0 build 218。
- 已通过 GPIO 进入 Gecko Bootloader 1.9.2，并返回原应用、重启恢复。
- 当前已生成原生 ARM 工具及 `rcp-native.tar.gz`；构建脚本要求模拟测试先通过才能打包。
- 本说明更新时，尚未收到原生工具的实机菜单读取、RCP 写入或原厂镜像实际刷回日志。新工具不是 Silicon Labs 官方工具，模拟测试不能替代实机验证。

本次用户接受 Zigbee 网络、密钥和配对配置可能丢失。回退指重新刷入原厂应用，不能保证恢复完整出厂状态。原厂恢复 GBL 来自社区提取，不是当前芯片的完整 Flash dump。

## 一、取得最新工具包

已经构建成功时，不必重新编译。使用：

```text
./3-rcp-mode/src/rcp_lab/native-tools/rcp-native.tar.gz
```

通过 FTP 或 SFTP 上传到网关 `/tmp`。后续命令全部在网关 SSH/Telnet 中执行。

如果此前还没成功构建，才在 WSL 执行以下命令：

```sh
cd ./3-rcp-mode/src/rcp_lab/native-tools
sh build-native-tools.sh
```

该脚本先运行本地模拟 Bootloader 测试，再交叉编译并打包，不操作实际网关。

## 二、开始前的状态

1. 保留已验证的 SSH/Telnet，root 空密码不变。
2. 暂时禁用会自动维护网关的 XiaomiGateway3 等集成，防止它重启原 Zigbee 服务。
3. 前一轮 TCP 桥接测试必须已恢复并重启；不要同时运行旧的 `rcp-preflight` 桥接会话。
4. 后续必须解压到 `/tmp/rcp-native`，脚本使用该固定路径。

网关执行：

```sh
cd /tmp
tar -xzf rcp-native.tar.gz
sh rcp-native/prepare-local.sh
```

安装包会先校验 SHA-256，然后临时暂停 openmiio_agent、app_monitor，停止占用 ttyS1 的原厂 Zigbee 主机程序。SSH、网络和硬件看门狗保持运行；不修改现有启动脚本。此准备步骤一次会话只执行一次。

如果提示旧 state 目录存在，不要手动删除状态继续；先按下文恢复服务并重启。

## 三、先验证原生 Bootloader 只读探测

```sh
sh /tmp/rcp-native/probe-bootloader.sh
```

脚本执行已经验证过的 ISP/RESET 序列，再由网关本机程序读取菜单。该命令不选择 upload、不写入固件。

应看到：

```text
Gecko Bootloader v1.9.2
BOOTLOADER_PROBE_PASS (no upload requested)
```

如果失败，停止刷写，保留输出；不要跳过版本检查或关闭校验。若通过，可在同一次会话继续下一步，不必重新 prepare。

## 四、网关本机刷入 RCP

下面的命令会实际写入 MHCZ01P 应用区。过程中保持供电和网络连接，不中断刷写进程。

```sh
sh /tmp/rcp-native/flash-rcp.sh
```

脚本会再次校验包内文件、通过 GPIO 进入 Bootloader，并上传固定镜像：

```text
lumi-gateway-mgl001_opentread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_460800.gbl
```

UART 刷写波特率固定为 115200、RTS/CTS，发送方式为 XMODEM-CRC 128 字节块。工具先验证 GBL 类型、CRC、允许的标签和应用编程范围；拒绝 Bootloader/security 更新标签。收到 Bootloader 的 `Serial upload complete` 和菜单后，才发送运行应用命令。

成功标志：

```text
APPLICATION_UPLOAD_PASS: bootloader accepted image; run command sent.
```

这仅表示 Bootloader 接受镜像并已发送运行命令，不代表 RCP 的 Spinel 通信和 Thread 无线功能已经验证。

## 五、RCP 刷入后的状态

RCP 应用使用 **460800**，Bootloader 仍使用 **115200**。波特率由使用串口的程序分别设置，不是永久修改 Linux 串口配置。

此时原 Zigbee Linux 服务仍处于暂停状态。**不要执行 restore-services.sh 去恢复 EZSP 服务，也先不要重启。** 原厂主机只支持 Zigbee EZSP，不能用于 RCP；下一步需要配置持久 RCP 模式及本机 OTBR/Spinel 验证。

当前原生工具只实现 Bootloader 探测和 GBL 上传，不包含本机 Spinel/RCP 应用探测器。刷写成功后保留完整输出，再进行后续应用验证。不要把旧的 WSL `probe-rcp.sh` 直接用于本流程：它要求另外存在 TCP 8899 桥接，而本流程没有启动网络桥。

## 六、网关本机刷回原厂 Zigbee

无论 RCP 是否能正常启动，都使用 GPIO 进入 Bootloader，不依赖应用协议。

如果还处于本次暂停会话，直接执行：

```sh
sh /tmp/rcp-native/flash-zigbee.sh
```

该脚本自行进入 Bootloader，并上传固定原厂候选：

```text
xiaomi_stock_ncp_6.6.6.0_build218.gbl
```

必须等到 `APPLICATION_UPLOAD_PASS` 后，再恢复 Linux 服务：

```sh
sh /tmp/rcp-native/restore-services.sh
reboot
```

重启后检查原厂服务：

```sh
ps | grep '[m]Z3GatewayHost_MQTT'
```

进程存在只能证明主机服务已启动，原厂无线应用的实际版本和通信仍需进一步探测确认，不能仅凭进程认定回退验证全部完成。

如果刷入 RCP 后已经重启，/tmp 里的工具和状态会消失。重新上传解压工具包，执行 `prepare-local.sh`，再执行 `flash-zigbee.sh`。无需另行切换 TCP 桥波特率。

## 七、只做了探测，未刷写时恢复

如果本次只执行了 probe、没有刷入 RCP，直接执行：

```sh
sh /tmp/rcp-native/restore-services.sh
reboot
```

`restore-services.sh` 只恢复 GPIO 和原 Linux 进程，**不会把 RCP 变回 Zigbee**。已经刷入 RCP 时，要先成功执行 `flash-zigbee.sh`，再用它恢复服务。

## 八、失败处理

- 出现 `ERROR`、重试耗尽或接收方取消时，保存完整输出，不把它当成成功。
- 保持供电；不要尝试整片擦除、改 IEEE 地址或升级 Bootloader。
- 串口进程退出后会释放 UART。可以重新运行 `probe-bootloader.sh`，确认 GPIO 入口仍可用，再用 `flash-zigbee.sh` 回退。
- 上传中断可能导致应用无法运行；已验证的 GPIO Bootloader 入口是主要恢复手段，但不能保证 Bootloader 或硬件损坏后仍可免拆恢复。

## 包内文件

```text
prepare-local.sh        暂停原 Zigbee 服务，释放 UART
enter-bootloader.sh     GPIO 进入 Bootloader
probe-bootloader.sh     本机读取菜单，不上传
flash-rcp.sh            本机刷入固定 RCP 镜像
flash-zigbee.sh         本机刷回固定原厂镜像
restore-services.sh    恢复 GPIO 和原 Linux 服务，不恢复固件
radio-flasher           静态 ARM UART/GBL/XMODEM 程序
firmware/               RCP 和原厂 Zigbee 两份 GBL
SHA256SUMS              文件校验清单
```

本流程不调用原厂 `zigbee_msnger zgb_ota`：该入口处理原厂 OTA，尚未验证可直接接受这里的第三方 GBL。
