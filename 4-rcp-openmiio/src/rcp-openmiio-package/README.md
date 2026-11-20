# 网关侧 RCP 与 Xiaomi Gateway 3 蓝牙共存

## post_init 边界

RCP/openmiio supervisor 由 OTBR boot manager 启动，不再直接拥有或替换 `post_init.sh`。


仅修改网关 /data 下的启动管理。HA 集成不改；openmiio 以 1.2.1 为最低版本，高于或等于该版本的现有二进制会保留，低于时才替换。当前已实测：openmiio 1.2.1 使用 miio mqtt cache central 时，HA 收到新的蓝牙数据，RCP Spinel 探测正常且 UART 空闲。

## 安装

将 rcp-openmiio.tar.gz 上传到网关 /tmp，用 SSH 执行：

```sh
cd /tmp
tar -xzf rcp-openmiio.tar.gz
sh /tmp/rcp-openmiio/install.sh
sh /data/rcp-openmiio/start.sh --now
```

现有干净参数的 openmiio 会被接管监控，无须为了安装而先停止它。无需禁用 HA 网关条目。安装器要求此前的 RCP 启动隔离已部署，且 openmiio 为已通过 BLE 实测的确切二进制；不匹配会拒绝安装。不要安装此前撤回的 HA 端补丁。

## 检查

```sh
cat /var/log/rcp-openmiio.log
ps | grep '[o]penmiio_agent'
ps | grep '[m]Z3GatewayHost_MQTT'
fuser /dev/ttyS1
/tmp/spinel-probe
```

ps 将看到真实的守护脚本 openmiio_agent.guard.sh，以及使用 miio mqtt cache central 的 openmiio 子进程。守护脚本不是 Zigbee 主机。实际 openmiio 不应含 z3 或 --zigbee.tcp，无 Z3 主机，UART 空闲，探测通过，HA 仍接收蓝牙新状态。

验证自动恢复可执行一次：

```sh
killall openmiio_agent
sleep 5
ps | grep '[o]penmiio_agent'
/tmp/spinel-probe
```

也可使用 HA 中的 OpenmiIO reload 功能，再检查新进程仍无 Zigbee 参数。最后执行 reboot 验证持久化。重启后 /tmp/spinel-probe 若已丢失需重新上传。

## 启动和恢复机制

新入口先启动守护脚本，再运行保存的 RCP→TUN→SSH→原厂服务启动链。守护脚本在原厂初始化返回成功后才启动 openmiio，避免与原厂启动过程争用内部接口。进程退出后隔两秒按固定无 Zigbee 参数重启。

原版集成会先检查 openmiio 二进制校验，再通过 ps 文本中是否含 openmiio_agent 判断是否需要启动。守护脚本的实际名称也含这个字符串，因此在子进程退出和恢复的空窗期，集成仍能发现网关侧的管理进程，不再按硬编码的 Zigbee 参数另起实例。这个方案利用现有集成的进程检测行为，所有变更均在网关；如果以后集成修改检测方式，需要重新验证。

本包未伪造二进制哈希、未替换原二进制，也不拦截 Telnet。守护脚本本身被杀死、启动失败或与外部管理程序冲突时，不能保证原版 HA 不再启动 Zigbee 参数。安装后需验证守护进程持续运行；不要在 RCP 工作期间手动终止守护脚本。

HACS/集成更新可能要求下载新版 openmiio。守护脚本只启动已验证的 SHA256 版本，检测到变化会记录 ERROR 并暂停子进程重启，不会默默运行未知版本。更新时需协调停止/恢复网关管理，重新验证二进制后更新包；不要用哈希伪装绕过校验。长时间运行的应用日志仍沿用 /var/log/openmiio.log，持久运行时应观察 /var 内存占用。

本包不创建 Thread 网络，不启动 OTBR，不改变串口波特率。后续 OTBR 运行时不得并行执行 spinel-probe。

脚本已在本地完成语法、包校验及模拟行为检查，实际 BusyBox 上的安装、自动恢复与重启验证仍待用户操作。

## 撤销

```sh
sh /data/rcp-openmiio/uninstall.sh
```

这只恢复安装前的 RCP 启动入口，不停止当前守护脚本或蓝牙进程，重启后生效。若 RCP 固件仍在，重启前暂时禁用 HA 的该网关条目，以免 HA 重新按 Zigbee 参数启动 openmiio。

完全刷回 Zigbee 时：先停止未来的 OTBR，按原生刷写包流程刷回 Zigbee，撤销本包后再撤销 /data/rcp-mode 的启动隔离，最后重启。必须按外层到内层的顺序恢复启动入口；不要直接覆盖后续已修改的 hook。
