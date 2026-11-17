# 异步拓扑诊断移植

本阶段源码接入 `/topology`（原包装格式）和 `/diagnostics`（原始节点数组）。页面和 TLV 字段沿用原 ESP32 项目：ExtAddress、Rloc16、Mode、Timeout、Route、LeaderData、IP6AddressList、ChildTable。OMRAddressList 根据当前 Network Data 中稳定的 SLAAC /64 前缀匹配，排除 Mesh-Local，不把所有非 Mesh-Local 地址都标成 OMR。

读取本机 RLOC 和 `ff03::2` 路由器诊断，按响应中 ChildTable 对子节点补查，每 500ms 最多一项；主循环不会等待网络响应。静默期为 3 秒，硬上限为 30 秒；一次仅允许一项 Web 扫描。对 192 个节点、128 项子节点查询、单节点 16KiB JSON、总节点 JSON 256KiB 设置上限。

未附着时直接返回 409，不发出诊断请求；没有响应返回 504。部分结果用 206，并在 `/topology` 的 `diagnostics` 字段报告响应路由器数、子节点缺失、查询错误、截断和超时信息；`/diagnostics` 保留数组格式，以 HTTP 206 表达部分结果。拓扑是收集时间窗内的尽力快照，不保证所有睡眠节点响应。重扫不使用旧的缓存节点，但 OpenThread 的共享诊断回调不能区分所有迟到响应，因此同一网络中迟到的有效响应也可能进入新窗口。扫描中掉网、分区或网络标识变更会终止本轮。

回调使用进程生命周期的入口，在管理对象停止时关闭，避免 CoAP 迟到回调访问已释放的管理对象。不通过额外发送无线报文来“取消”回调。退出释放等待中的 HTTP 工作线程。HA 名称映射和重启控制仍待移植。

用户在 WSL 执行：

```sh
cd ./5-otbr/src/otbr_host
sh build-host.sh arm
sh package-noattach.sh
```

停止旧网关测试，上传、解压新包并运行原 `start.sh`。新增日志应为 `ASYNC_TOPOLOGY_BACKEND_READY`；API=6053、Web=18080，原测试密码保留。仍为 no-attach，不启用 Thread。

在 WSL 执行：

```sh
sh test-host-topology.sh
```

预期 `HOST_NOATTACH_TOPOLOGY_PASS`：鉴权、方法限制，以及未附着时拒绝扫描，不发出诊断请求，不伪造空拓扑。并回归之前的 API、Web、Commissioner 和 Tools 脚本。用户仍需在后续附着后验证实际路由器/子节点收集、OMR、部分结果、并发 Ping 和退出清理。

助手只完成接口声明、字段和脚本静态检查；未编译、未运行诊断或改变网关配置。


## 远端节点重启修正

POST /node_restart 的参数为 address、ext_address（16 位十六进制）和 rloc16（整数）。原 Linux 处理器错误地只接受空对象并重启本地 Thread 栈，现已删除该行为。空对象或缺失身份字段返回 400，不改变本机 Thread 状态。

当前实现与 ESP 节点 components/esp32/openthread/remote_restart.cpp 的 EHR1 协议对齐：先通过异步拓扑诊断确认地址、扩展地址和 RLOC 属于同一节点，再使用 Thread 内部 UDP 向 18514 端口发送 21 字节请求。请求包含 EHR1、命令 1、8 字节扩展地址和 8 字节随机 nonce。只接受来自端口 18514、命令为 2 且身份/nonce 完整匹配的确认。

诊断最多 30 秒，随后等待节点确认最多 15 秒；HTTP 等待上限 50 秒。单次请求不重发，不阻塞 OT 主事件循环。网络变化、主机退出、并发重启或过期/不匹配目标会明确拒绝。未收到确认返回 accepted=false，不伪造成功。节点没有实现 EHR1 时不会因此具备远程重启功能。

本地协议回归测试加入 build-release.sh 的 CTest；助手未运行编译或发送任何重启请求。用户编译并部署后，在拓扑页选择一个已实现 EHR1 的目标节点，确认地址后点击“确认重启”。预期显示“节点已确认重启”，随后由用户确认该节点重启并恢复；同时网关 OTBR 进程、其他节点和蓝牙服务应继续运行。
