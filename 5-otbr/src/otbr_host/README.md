> 开发资料说明：本文件保留原项目开发阶段记录；正式部署和本版验收边界以 [部件 README](../../README.md) 为准。本发布使用用户态 BBR，手动构建入口为 src/build.sh，不要把历史 stable/no-attach 示例当成本版部署步骤。

# Xiaomi Gateway 2 standalone OTBR Host

独立 Linux C++ OTBR，提供 Native API、Web、Commissioner、异步 Ping/拓扑、SRP 与 HA 名称映射。backbone 随 Linux 链路/默认路由动态选择；保留既有 BLE/RCP 隔离。

RCP 硬件故障恢复已接入 supervisor：明确 RCP 故障退出后，在 Host 结束且 UART 空闲时，调用原厂复位线控制并回读电平；带退避和每 10 分钟 3 次的预算。源码模拟测试已通过，真实故障后全链路恢复仍待用户实机验收。本次可用只更新脚本的 `rcp-recovery-update.tar.gz`，无需重新编译或替换当前 Host；见 [recovery/README.md](recovery/README.md)。

## 配置归网关所有

**实际 YAML 只从网关 `/data/otbr/config.yaml` 读取，由用户通过 SSH/SFTP 编辑。** 私密值可直接填写；使用 `!secret` 时才需要同目录的 `secrets.yaml`。修改后执行 `sh /data/otbr/restart.sh`，不需要编译、打包或从 WSL 同步。

首次安装只在文件不存在时创建示例；升级和程序回退均保留用户 YAML、secrets 与证书。发布包只含程序、脚本、公开配置示例和公共 CA。项目中的实际 YAML、私密配置副本和旧测试包已清理。

Native API 默认端口为 6053。省略 `api.encryption` 时使用明文连接；配置有效 Noise key 后只允许加密连接，不自动生成 key。backbone 支持直接填写动态选择映射；默认 RCP 参数无需填写。

## 程序发布

```sh
cd ./5-otbr/src/otbr_host
sh build-release.sh
```

该命令不接收配置文件，自动构建、运行本地验证并生成通用 `otbr-deploy.tar.gz`。构建由用户执行。已经编译好对应 ARM 程序时，只更新部署脚本可用 `python3 tools/package_deploy.py` 重新打包。

上传程序包到网关 /tmp：

```sh
cd /tmp
tar -xzf otbr-deploy.tar.gz
sh /tmp/otbr-deploy/install.sh
```

已有有效网关配置时直接启用 Thread 并注册自启；首次新建的空 secrets 不会启动无线，用户在网关填写后重启服务。完整说明见 [deploy/README.md](deploy/README.md)。

## 运行与验收

```sh
sh /data/otbr/check.sh
sh /data/otbr/restart.sh
sh /data/otbr/status.sh
```

以上均在网关执行。WSL 的 `sh test-deployed.sh` 通过现有 SSH 2223 在内存中读取网关当前 YAML/secret 后验收，不使用 WSL 副本，不输出凭据。

字段映射见 [CONFIGURATION.md](CONFIGURATION.md)。原 no-attach 工具保留用于开发。当前完整 BBR/MLR 组播和 NAT64 未启用；真实 RF 附着、远端流量、Joiner 与物理链路切换须部署后验收。

## ESPHome 自动发现

Host 通过现有 OpenThread mDNS 引擎发布 `_esphomelib._tcp.local.`，与 Thread `_meshcop._udp` 共存。实例名和端口来自网关 YAML，MAC 与 Native API 保持一致。配置 Noise key 时发布加密类型；未配置时使用明文，不发布密钥或宣称支持密钥配置。API 监听成功后才发布，服务停止时撤销；backbone 切换后重新注册。Native API 在支持 IPv6 时使用 IPv4/IPv6 双栈监听。

更新源码后，用户执行 `sh build-release.sh`，将新程序包上传网关 `/tmp` 并执行 `sh /tmp/otbr-deploy/install.sh`。安装保留网关 YAML。然后在与网关同一局域网的 WSL 中执行：

```sh
sh test-mdns.sh
```

默认检查 GATEWAY_ADDRESS:6053；自定义地址或端口可执行 `sh test-mdns.sh 地址 端口`。该测试验证实际 DNS-SD 地址、SRV 端口与 TXT，不修改网关或发起 Thread 无线操作。WSL 和 HA 所在网络需要能接收局域网 mDNS 组播；实际 HA 自动发现以部署后结果为准。


## 拓扑页远端节点重启

Linux /node_restart 后端已改为与 ESP 节点内置 EHR1 UDP 协议兼容，不重启网关本机的 Thread 栈。用户编译并部署新版后，在拓扑页选择目标、核对地址和扩展地址，再点击确认重启。仅支持实现 EHR1 的节点；发送前执行诊断身份核对，发送后等待最多 15 秒确认，整体操作可能需要约 45 秒。未收到节点确认不会报告成功。

本次源码修复尚未由助手编译或实机测试。用户执行 build-release.sh 会构建并运行 node-restart-protocol 回归测试，再生成程序包；升级保留网关当前 YAML。


## BBR 用户态实验版

网关内核已实测不提供 MRT6 多播路由 API。默认稳定版保持 BBR 关闭；独立 AF_PACKET 实验适配见 bbr/README.md。用户执行 sh build-release-bbr.sh 生成 otbr-deploy-bbr.tar.gz，使用单独构建目录，不覆盖稳定程序包。用户已完成实验版基础 MLR/双向多播实测，详见 bbr/ACCEPTANCE.md；角色切换、MLR 过期和实验后端链路切换仍待验证。

## 网关系统实体扩展

新增 ipv4、uptime、reset、fw_ver、sys_led 的配置、实现边界与升级验收见 [GATEWAY-ENTITIES.md](GATEWAY-ENTITIES.md)。当前 0.2.5 发布件已包含这些更新。

## 0.2.5 Thread Proxy

完整的可选代理实现与使用说明见 [THREAD-PROXY.md](THREAD-PROXY.md)。默认不启用，配置变更只需重启服务。用户已完成构建、部署和基本代理上报验收，当前包已同步至第 5 部件 deploy。
