# Integrated Host no-attach runtime test

本包复制用户构建的 mi-otbr-host，不重新编译。测试 TUN=mgotbr0，普通 OT 设置和临时统计目录=/tmp/mi-otbr-noattach/state，Native API 使用标准端口 6053。请不要同时运行其他 Native API 测试服务。

## 网关端

上传 host-noattach-probe.tar.gz 到网关 /tmp，用 SSH 执行：

```sh
cd /tmp
tar -xzf host-noattach-probe.tar.gz
sh /tmp/host-noattach-probe/start.sh
```

脚本在前台等待，显示运行日志。保持它运行，不要同时启动其他 Agent 或 spinel-probe，也不必停止无 Zigbee 参数的 openmiio 蓝牙服务。

正常应出现 CORE_RUNTIME_READY mode=no-attach、thread_if=mgotbr0 和 Native API 6053 监听日志。仅 READY 行不代表 API 已成功绑定，必须继续执行下面的客户端检查。CLI socket 使用 /var/run/openthread-mgotbr0.sock；核心与 ot-ctl 共用该目录。

## WSL 端验证真实状态

在另一个 WSL 终端执行：

```sh
cd ./5-otbr/src/otbr_host
sh test-host-noattach.sh
```

默认连接 GATEWAY_ADDRESS:6053，使用本机 host-noattach-probe/secrets.yaml 的临时随机 Noise key，不在控制台输出 key。该脚本使用现有开发环境的官方 aioesphomeapi，网关不需要 Python。

预期 HOST_NOATTACH_API_PASS：正确设备身份、九个诊断实体、真实 RCP 版本、RCP Connectivity=true、Thread Role=disabled、Attached=false、Thread Identity=missing。邻居与子节点数也应为 0。脚本本身不修改任何实体或网络。

同时检查 HA 原有蓝牙设备仍收到新状态。尚未实现 _esphomelib mDNS 广播，这一步不依赖自动发现，也不需要把临时测试设备添加进 HA。

## 停止及清理核验

网关运行 start.sh 的终端按 Ctrl+C，或另一个网关 SSH 终端执行：

```sh
sh /tmp/host-noattach-probe/stop.sh
```

然后检查：

```sh
ip link show mgotbr0
fuser /dev/ttyS1
ps | grep '[o]penmiio_agent'
```

临时接口应消失，UART 应释放，原蓝牙 openmiio 与守护脚本继续存在。日志保留在 /tmp/mi-otbr-noattach.log，测试状态文件也保留，不自动删除。

## 行为边界

本包会初始化 RCP，创建实际 TUN 和 OT Host 基础设施，可能创建临时设置、统计及本地 CLI socket。关闭自动附着，不调用 YAML Dataset 应用，不启用 Thread，因此测试 YAML 中的虚构网络参数不会用于入网。脚本不修改 sysctl、自启、生产 /data/otbr/state 或原厂网络配置。

这不是单纯 GET 查询，也不能证明射频入网、LAN↔Thread 路由或完整 BBR 组播已工作。BBR 当前关闭。Web 已接入静态页面、Basic 鉴权以及总览/节点/地址/SRP 查询；拓扑诊断与 HA 名称映射仍待迁移。Commissioner 后端已接入，实际配网需另行验收。异步 Ping 与 Dataset 查询已接入源码，见后面的 Tools 验收。

## Web 查询验收

看到 `[web] Basic-auth listener started on port 18080` 后，在 WSL 执行：

```sh
sh test-host-web.sh
```

预期 `HOST_NOATTACH_WEB_PASS`。脚本只读 HTTP：核对鉴权、嵌入首页、真实 RCP 版本、disabled 角色、IPv6 地址列表与 SRP 结构，不请求任何控制操作。也可以浏览器打开 `http://GATEWAY_ADDRESS:18080`，账号 `test`，密码见本包 `secrets.yaml` 的 `web_password`。

## Commissioner no-attach 验收

本版测试 YAML 启用 Commissioner 页面，但不会自动启动配网窗口或 Thread。日志应新增 `COMMISSIONER_BACKEND_READY`。在 WSL 执行：

```sh
sh test-host-commissioner.sh
```

脚本查询状态，并发送非法或必须因未附着而被拒绝的开始请求。预期 `HOST_NOATTACH_COMMISSIONER_PASS`。这一步含负向 POST 验证，不请求成功开始配网或取消，不应用 Dataset，不启用 Thread。实际候选发现、角色申请、认证和配网仍需后续附着验收。

## Tools no-attach 验收

日志应新增 `ASYNC_PING_DATASET_BACKEND_READY`。在 WSL 执行：

```sh
sh test-host-tools.sh
```

预期 `HOST_NOATTACH_TOOLS_PASS`。它检查只读 Active Dataset 接口、非法 Ping 参数，以及合法 Ping 在未附着时被拒绝；不会开始 ICMP 请求或启用 Thread。实际 Ping 回复与丢包统计留待附着后验收。

## Topology no-attach 验收

日志新增 `ASYNC_TOPOLOGY_BACKEND_READY`。在 WSL 执行：

```sh
sh test-host-topology.sh
```

预期 `HOST_NOATTACH_TOPOLOGY_PASS`：拓扑接口要求鉴权，只支持查询方法，Thread disabled 时返回 409，不发送诊断请求、不返回伪造的空拓扑。实际扫描、路由/子节点信息和部分结果仍待附着后验证。

本包的随机 key 只用于本轮协议测试，不是生产凭据。重新打包时会保留当前包的 key 以便 WSL 与网关两端匹配；如果换包，请保持两端来自同一份压缩包。

助手完成了脚本语法、文件哈希和配置字段隔离核对，没有运行这个网关测试。实际 Linux 4.9 的完整 Host/TUN 初始化与状态验收由用户执行。
