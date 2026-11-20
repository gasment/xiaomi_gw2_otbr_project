> GitHub 源码版：大型构建依赖和预构建包不随仓库提供。构建前按 [BUILD-RESOURCES.md](../BUILD-RESOURCES.md) 补齐资源并恢复链接；安装包从 Release 获取。

## post_init 边界

RCP mode 是 OTBR 的内部前置步骤，不再拥有或替换 `post_init.sh`。


# 3 — RCP 本机刷写与原厂 Zigbee 启动隔离（项目版本 0.3.0）

## 部件说明

本部件补齐两个连续阶段：先将 MHCZ01P/EFR32MG21 刷成 OpenThread RCP，再隔离原厂 Zigbee 主机/监控/已检查 OTA 路径。刷写全部在网关执行。

发行 RCP：`lumi-gateway-mgl001_opentread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_460800.gbl`，来自 darkxst/silabs-firmware-builder 的 20250627 发行。硬件 UART `/dev/ttyS1`，460800、RTS/CTS；Gecko Bootloader 1.9.2。附 Zigbee `6.6.6.0 build218` 应用 GBL 供回退，不包含 bootloader 镜像和量产整片擦除步骤。

`src/rcp_lab/native-tools` 是本项目 C 刷写器/探测器、PTY 回归和构建源码；`src/rcp-mode-package` 是隔离脚本源码

## 打包版本部署方法

先完成 1、2；首次刷写阶段暂时禁用 HA Xiaomi Gateway 3 的该网关条目，避免串口被重新占用。上传 deploy 下两个 tar.gz 和 `deploy/tools/spinel-probe` 到网关 `/tmp`。

```sh
cd /tmp
tar -xzf rcp-native-0.3.0.tar.gz
tar -xzf rcp-mode-0.3.0.tar.gz
sh /tmp/rcp-native/prepare-local.sh
sh /tmp/rcp-native/probe-bootloader.sh
sh /tmp/rcp-native/flash-rcp.sh
chmod 755 /tmp/spinel-probe
/tmp/spinel-probe
sh /tmp/rcp-mode/install.sh
reboot
```

逐条检查成功结果后继续。原厂服务暂停期间不要执行 restore-services.sh 来拉起 Zigbee 主机。原生 prepare-local 要求原厂 monitor 与 openmiio 存在且未暂停；已改造系统不应为了重新验收而直接再刷。隔离安装器支持 `LUMI_VERSION >= 1.0.8_0015`：保存当前原厂脚本后，按已知结构自动屏蔽 Zigbee 启动和协调器 OTA；结构无法识别时拒绝安装。

## 验证方法

```sh
cat /var/log/rcp-mode.log
ps | grep '[m]Z3GatewayHost_MQTT'
ps | grep '[m]zigbee_agent'
fuser /dev/ttyS1
```

隔离应成功，Zigbee 主机/agent 不应运行；在 OTBR 尚未启动时 UART 应空闲。重启会清空 /tmp，必要时重新上传 spinel-probe，再运行；要求版本 2.5.3.0、协议 4.3、RCP API 10、最低 Host API 4 和 `SPINEL_RCP_PROBE_PASS`。OTBR 运行后不要并行执行探测器。

恢复 Zigbee 时先卸载/停止外层 OTBR，使用一份新解压的原生包进入准备和 flash-zigbee 流程，保持 Zigbee 服务隔离；再撤销第 4 部件、第 3 部件启动入口，最后重启。数据不保证继承，完整顺序见根 README。

## 手动构建步骤简易说明

1. 把 ARM musl 工具链复制到 src/toolchains/armv7-musl。
2. 用户执行以下命令构建网关本机刷写器/探测器；入口从 0-build-src/firmware 校验两份 GBL 作为测试和打包输入，不修改固件：

```sh
cd ./3-rcp-mode/src
sh build.sh
```

输出在 `src/build-output/`；其中 rcp-mode 仅重新打包 Shell，不需要编译。

若要重建无线固件本身，另行复制 silabs-firmware-builder 和 Simplicity SDK 2024.6.3 至 external 对应目录，参考 `references/rcp-manifest.example`、rcp-project.slcp 与上游工具要求。构建目标 EFR32MG21A020F512IM32，非本项目自有完整 SDK
