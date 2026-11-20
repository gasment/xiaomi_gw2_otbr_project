# OTBR 程序安装包

## post_init 模块

本组件只增删 `otbr` 模块，并由 `/data/otbr/boot-manager.sh` 管理 OTBR、RCP mode 和 RCP/openmiio 前置条件。RCP mode 与 openmiio 安装器不再直接修改 `post_init.sh`。


包内只含程序、脚本、示例和公共 CA，**不包含实际 config.yaml/secrets.yaml**。Host 从网关 /data/otbr/config.yaml 读取运行配置，用户在网关编辑。

## 安装或升级

```sh
cd /tmp
tar -xzf otbr-deploy.tar.gz
sh /tmp/otbr-deploy/install.sh
```

已有有效的 /data/otbr/config.yaml 时，校验后保留原文件，更新程序并启用 --run、自启和崩溃重启。会停止已知 no-attach 测试，不杀其他 UART 使用者，不改变 BLE 参数，不刷 RCP。

首次缺少配置时，安装器从示例建立以下文件，且只创建缺失项：

```text
/data/otbr/config.yaml
/data/otbr/secrets.yaml
```

未填必要参数时会报待配置并保持无线未启动。用户通过 MobaXterm SFTP 或 SSH 填好现有 Thread Dataset、Web 密码以及需要的 HA 参数后执行；Native API Noise key 可选。现有配置不使用 !secret 时，不创建 secrets.yaml。

```sh
sh /data/otbr/restart.sh
```

以后修改 YAML 只需重启服务，不需要 WSL 文件、重新编译或重新打包。升级、程序回退均保留用户配置；`.example` 更新不影响实际文件。

## 状态

```sh
sh /data/otbr/check.sh
sh /data/otbr/status.sh
```

日志 /var/log/mi-otbr.log、mi-otbr-supervisor.log 自动轮转。CORE_RUNTIME_READY mode=run 后应看到 THREAD_STATE role=child/router/leader；READY 不代表真实附着或路由已经成功。

RCP 故障恢复已加入 supervisor：仅退出码 4/6，在进程结束、UART 空闲后，通过原厂 ISP/RESET 脚本做正常应用复位，回读 GPIO；10 分钟内最多 3 次，5/15/30 秒退避。普通启动、停止、升级和配置错误不产生复位脉冲。状态脚本显示最近一次恢复，日志检索 `RCP_RECOVERY`。详细策略、模拟验证和无需重新编译的仅脚本升级包见项目 `recovery/README.md`。尚未进行真实 RCP 故障注入或验证复位后网络全链路恢复。

默认 Web 为 http://GATEWAY_ADDRESS/，账号密码以网关 YAML 为准。HA 手动添加 ESPHome 集成，API 默认端口 6053；仅当网关配置 api.encryption 时填写对应 Noise key。没有 ESPHome 编译或 OTA。

WSL 统一验收 `sh test-deployed.sh` 会通过原 SSH 2223 在内存中读取网关的实际 YAML/secret，随后验证 Dataset、实际 Ping/拓扑、Native API 和 HA 状态；不会读取旧 WSL 副本，也不输出凭据。独立 Leader 且无其他节点证据时不会冒充加入已有网络。真实 Joiner、LAN 到远端 Thread 节点和物理 backbone 切换仍需相应设备验收。

## 停止与回退

```sh
sh /data/otbr/stop.sh
sh /data/otbr/rollback.sh
```

stop 临时停止，重启网关后仍自启；rollback 仅供有上一版程序时使用，保留用户 YAML/证书。若首次安装需要回退，执行：

```sh
sh /data/otbr/uninstall.sh
```

卸载恢复先前启动链和 IPv6 sysctl，保留用户配置/状态/备份，不删除 BLE/TUN/SSH，也不自动刷回 Zigbee。若启动钩子后来被别人改动，会保留并报错，避免覆盖。

服务启动保存并启用 IPv6、forwarding 和 LAN accept_ra=2，停止恢复原值；不重配 IPv4。复用原 RCP/BLE 隔离链。HA 查询在独立线程，HTTP/HTTPS、响应上限、5 分钟缓存、冲突拒绝与失败退避均已接入。HTTPS 校验证书，用户在网关维护自签名 CA。完整 BBR/MLR 组播与 NAT64 尚未启用。
# 0.3.0 可选功能

版本以包内 VERSION 为准。thread_proxy_api 始终编入 Host，但只有网关配置中存在同名顶层映射时才启动；缺省不启用。完整参数和节点/HA 验证见源码 THREAD-PROXY.md。端口默认 TCP 6065、Thread 内 UDP 6064，独立于网关实体 Native API 6053。旧配置无需修改即可继续运行。

