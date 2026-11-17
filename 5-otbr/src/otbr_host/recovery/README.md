# RCP 硬件复位恢复：仅脚本升级包

本包仅更新 `/data/otbr/supervisor.sh`、`rcp-recovery.sh`、`status.sh`，不替换 Host 二进制，不修改用户 YAML，不刷 RCP，不改变 BLE 隔离链。安装会正常停止并重新启动 OTBR，现有注册和在线时长会随 Host 重启重新建立。

## 安装

将 `rcp-recovery-update.tar.gz` 上传至网关 `/tmp`，在网关执行：

```sh
cd /tmp
tar -xzf rcp-recovery-update.tar.gz
sh /tmp/rcp-recovery-update/install.sh
sh /data/otbr/status.sh
```

安装器检查包内校验和、已验证的 common/start/stop 与原厂 GPIO 脚本版本，以及 supervisor 是否具有独立修改。检查失败时不会为了绕过检查直接覆盖。旧脚本备份在 `/data/otbr/rcp-recovery-backup`，安装过程发生错误会尝试恢复旧脚本。

## 恢复策略

- 仅 Host 已退出、退出码为 4（RCP 异常重置）或 6（RCP 无响应）时排队硬件恢复。正常退出、配置/通用错误、协议不兼容、平台软件复位 8 和信号退出不触发硬件脉冲。
- 等待 Host 结束，确认 UART 无使用者、BLE/RCP 隔离启动完成、配置有效、服务没有正在停止；不终止其他 UART 使用者或 BLE 服务。
- 正常启动模式：调用原厂 `/bin/zigbee_isp.sh 1` 并回读 GPIO43 为 out/1。不会拉低 ISP 进入 bootloader。
- 复位：原厂 `/bin/zigbee_reset.sh 1` → 100ms → `/bin/zigbee_reset.sh 0`，回读 GPIO44 的 out/1 和 out/0；释放后等待 500ms，再允许 Host 启动。
- 第 1/2/3 次尝试分别等待至少 5/15/30 秒。滚动 600 秒内最多 3 次，失败尝试也占用预算。达到上限后保持 Host 不启动，等待预算过期后再试。预算存于 `/tmp`，同一次开机内重启 supervisor 不清空预算。
- 复位脉冲中收到停止信号会尝试释放 RESET；无法确认释放时停止 supervisor，不继续启动 Host。GPIO/时钟/预算或 UART 检查失败会记录原因，不宣称恢复成功。

这是“明确 RCP 故障退出后的恢复”，不是检测所有进程卡死的独立看门狗。GPIO 脉冲完成不代表 RCP、Thread 或路由已经恢复；后续仍需实际初始化及网络验收。

## 查看日志

```sh
grep 'RCP_RECOVERY' /var/log/mi-otbr-supervisor.log
sh /data/otbr/status.sh
```

没有遇到相关故障时，`none this boot` 是正常现象，普通安装/启动不会主动复位。不要用 `kill -6` 模拟退出码 6：它发送 SIGABRT，进程退出状态并不是程序主动返回 6。

测试阶段仅在 WSL 临时文件系统模拟 GPIO/UART/时钟和 TERM；尚未人为制造真实 RCP 故障或验证硬件复位后的 Thread/SRP/mDNS/BBR 全链路恢复。实际故障后需核对恢复日志、OTBR 在线时长、Thread 角色、SRP/mDNS、BBR 和 HA 蓝牙更新。

## 回退

```sh
sh /data/otbr/rcp-recovery-backup/rollback.sh
```

回退会停止 OTBR、恢复升级前脚本并重新启动；Host 程序和用户配置不变。没有旧辅助脚本时，新 helper 可留在目录中，但旧 supervisor 不会调用它。

## 源码和以后打包

同样的恢复脚本已接入正式 `deploy/payload`，后续完整 BBR 发布包自动包含该功能。此次无需编译，只需在 WSL 生成仅脚本升级包：

```sh
cd ./5-otbr/src/otbr_host
python3 tools/package_rcp_recovery.py
```

此命令先执行模拟回归，再打包公开脚本，不读取网关 YAML 或私密信息。
