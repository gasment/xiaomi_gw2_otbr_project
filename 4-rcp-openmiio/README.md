> GitHub 源码版：大型构建依赖和预构建包不随仓库提供。构建前按 [BUILD-RESOURCES.md](../BUILD-RESOURCES.md) 补齐资源并恢复链接；安装包从 Release 获取。

## post_init 边界

RCP/openmiio supervisor 由 OTBR boot manager 启动，不再直接拥有或替换 `post_init.sh`。


# 4 — RCP 与 Xiaomi Gateway 3 BLE 共存

## 部件说明

随 OTBR 软件栈部署，包名后缀取自 [OTBR 版本](../5-otbr/VERSION)。

仅在网关管理 openmiio，启动参数固定为 `miio mqtt cache central`，去掉 z3/zigbee.tcp，让蓝牙继续向 HA 上报、UART 留给 OTBR。不修改 HA 集成文件，不伪造 openmiio 哈希，不改 root 空密码。

本项目源码是 src/rcp-openmiio-package 的启动入口、guard、卸载和兼容检查脚本。openmiio 是外部依赖，最低版本为 1.2.1：高于或等于 1.2.1 的现有版本会保留，低于 1.2.1 时才替换。1.2.1 基线的可执行文件已从当前网关只读归档至 deploy/dependencies/openmiio_agent 并核对 SHA256。它不是本项目重编译的产物；对应精确源码提交未确认，上游源码预留在 src/external/openmiio_agent。

## 打包版本部署方法

完成第 3 部件且确认隔离正常后，将 `deploy/rcp-openmiio-0.3.2.tar.gz` 上传 `/tmp`。安装器要求 `/data/openmiio_agent` 已是验证版本；若文件不存在，可先通过 SFTP 上传 deploy/dependencies 的可执行依赖到该路径，再 `chmod 755 /data/openmiio_agent`。已有运行中但版本不匹配时先协调 HA/原管理流程，不覆盖运行文件绕过校验。

```sh
cd /tmp
tar -xzf rcp-openmiio-0.3.2.tar.gz
sh /tmp/rcp-openmiio/install.sh
sh /data/rcp-openmiio/start.sh --now
```

之后重新启用 HA Xiaomi Gateway 3 对应条目。如当前正常网关已经安装本层，不需要重跑安装器。

## 验证方法

```sh
cat /var/log/rcp-openmiio.log
ps | grep '[o]penmiio_agent'
ps | grep '[m]Z3GatewayHost_MQTT'
fuser /dev/ttyS1
```

guard 和 `openmiio_agent miio mqtt cache central` 应存在，不含 z3/zigbee.tcp；无原 Zigbee 主机。OTBR 启动前 UART 空闲；启动后应只由 OTBR 使用。最后以 HA 收到蓝牙设备的新状态作为业务验收，进程存在本身不足以证明上报正常。该共存、自恢复和网关重启已经由用户实测过。

## 手动构建步骤简易说明

Shell 管理部件不需要编译。编辑源码包后重新打包：

```sh
cd ./4-rcp-openmiio/src
sh build.sh
```

新包在 src/build-output。重新构建上游 openmiio 需要自行复制其源码和 Go 环境，参照上游说明
