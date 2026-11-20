# 小米多模网关 2：RCP 启动隔离

## post_init 边界

RCP mode 是 OTBR 的内部前置步骤，不再拥有或替换 `post_init.sh`。


本包用于当前已验证的网关系统及既有 OpenSSH、TUN 部署。RCP 已刷入，并已通过本机 Spinel 探测；本包不刷固件、不创建 Thread 网络、不包含 OTBR。

## 安装

先保持 Home Assistant 的 Xiaomi Gateway 3 集成禁用，避免它重新启动带 z3 参数的 openmiio_agent 或原厂 Zigbee 主机。该集成在当前阶段不能继续管理此 Zigbee 串口。第三方脚本同样不得占用 /dev/ttyS1。

将 rcp-mode.tar.gz 上传到网关 /tmp，在网关 SSH 中执行：

```sh
cd /tmp
tar -xzf rcp-mode.tar.gz
sh /tmp/rcp-mode/install.sh
reboot
```

安装器先备份当前 `/bin/fw_manager.sh` 与 `/bin/app_monitor.sh`，再根据已知代码结构生成兼容隔离副本，保留当前固件的其他启动逻辑。适用于 `LUMI_VERSION >= 1.0.8_0015`；无法识别脚本结构时拒绝安装。安装只写 /data，下一次启动生效；不会恢复当前暂停的原厂进程。不要执行原生刷写包的 restore-services.sh。

## 重启检查

```sh
cat /var/log/rcp-mode.log
ps | grep '[m]Z3GatewayHost_MQTT'
ps | grep '[m]zigbee_agent'
ps | grep '[o]penmiio_agent'
grep '^tun ' /proc/modules
ls -l /dev/net/tun
```

日志应显示 RCP startup isolation active，前两项进程查询应无输出。检查 openmiio_agent：如果存在带 z3 参数的实例，先停止后续操作并排查外部集成。确认 SSH 2223 和 TUN 正常。

/tmp 文件重启后通常丢失。重新上传此前已验证的 spinel-probe，再执行：

```sh
chmod 755 /tmp/spinel-probe
/tmp/spinel-probe
```

应再次得到 SPINEL_RCP_PROBE_PASS，版本 2.5.3.0、协议 4.3、RCP API 10、最低主机 API 4。这仅证明固件与串口通信，射频收发需 OTBR 入网实测。

## 工作方式及边界

启动入口先用 mount -o bind 将 /data/rcp-mode 中的两个脚本副本挂载到 /bin/fw_manager.sh 与 /bin/app_monitor.sh，再执行安装时保存的 TUN 启动入口。原有 TUN→SSH→原厂启动链继续运行。

副本屏蔽原厂 Zigbee 主机和 mzigbee_agent 的启动、监控拉起，以及 fw_manager 中的 coordinator_ota。只读系统分区未被改写；停止这些 Zigbee 组件会使原有 Zigbee 自动化失效。其他小米功能是否完全正常仍需实际观察。

若启动隔离校验或挂载失败，为保留系统可恢复性仍会继续原启动链，并在日志记录 ERROR。此时可能拉起原 Zigbee 服务，不能视作隔离成功。禁止对这台改造网关执行原厂 OTA：本包仅屏蔽已检查脚本中的协调器 OTA，不覆盖所有外部升级路径。系统升级后脚本哈希可能改变，需要重新评估。

本包已完成脚本语法、内容差异和校验清单检查；尚未在网关上执行安装和绑定挂载，重启验证由用户进行。

## 回退到 Zigbee

先停止未来部署的 OTBR。重新上传原生刷写包，按其说明使用 prepare-local.sh、flash-zigbee.sh 刷回已验证版本的 Zigbee GBL。回刷期间保持 Zigbee 服务关闭；若 prepare-local.sh 因旧状态拒绝执行，先检查状态，勿盲删。

确认回刷上传成功后，恢复旧启动入口：

```sh
sh /data/rcp-mode/uninstall.sh
reboot
```

当前 bind mount 保留至重启；重启后只读原脚本自然恢复。卸载器不会擦除固件、删除备份或立即恢复原厂进程。SSH、TUN 的原启动链保留。原 Zigbee 配网数据不保证可继承，可能需要重新配对。
