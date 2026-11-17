# Thread Proxy API：0.2.0

代理始终编入 mi-otbr-host，不引入 ESPHome 运行时。运行时只读取网关用户配置，缺少顶层 thread_proxy_api 时不创建代理对象、线程、UDP/TCP 监听或 mDNS 服务。修改配置后重启服务即可。现有 6053 网关实体、Web、BLE、SRP、BBR 保持独立。

## 配置

在网关原有配置中添加与 thread_br 同级的块；省略整个块即禁用，`thread_proxy_api: {}` 按默认值启用。null、false、放在 thread_br 内以及未知字段均拒绝。

```yaml
thread_proxy_api:
  port: 6065
  max_connections: 2
  status_interval: 30s
  # encryption:
  #   key: !secret proxy_noise_key
  udp:
    queue_groups: 16
    queue_bytes: 131072
    # encryption:
    #   key: !secret node_udp_key
```

TCP Noise 与 UDP AES-256-GCM 独立，可分别启用。两种 key 均为非全零、32 字节 Base64；UDP key 必须与节点相同，不能自动使用网关 Native API 的 key。凭据只在网关编辑，不复制进项目。TCP 端口不得与 Native API、Web 冲突；当前节点协议使用固定 UDP 6064。

max_connections 范围 1..4，status_interval 为 1s..5min，queue_groups 为 1..128，queue_bytes 为 32768..1048576。配置检查只输出模式和限额，不输出密钥，不启动任何服务。

## 协议和并发

LAN 通过 `_thread-proxy._tcp` 发布代理，TXT 包含 component=thread_proxy_api、version=1、稳定 BR MAC ID 和独立 encryption 模式。DeviceInfo 报告 Xiaomi、OTBR VERSION，不要求 ESP32。6053 的设备实体不会从 6065 暴露；代理最多允许一个 HA 会话消费报文队列，其余连接只能订阅管理状态。

管理协议沿用消息 34/35/40 及 thread_proxy.info/status/packet、uplink、delivery_ack/reject、request_schema。原始节点 Native API 记录作为不透明载荷转发，不在 BR 创建节点业务实体，不执行节点业务控制。

Thread 内使用 OpenThread 内部 UDP socket，不使用 LAN UDP 或节点 SRP。TSD2 为 48 字节头、768 字节分片、最大 32768 字节一组；DATA、DISCOVER、SLEEP、HEARTBEAT 与描述交换保持 ESP32/nRF52 客户端兼容。发现回复来自 BR Mesh-Local 单播地址；ACK 使用节点当次投递目标地址作为源地址，携带匹配的 wake/group。

OpenThread 回调只复制到八项有界接收环形队列。解密、重组、去重和 RAM 入队在独立工作线程；eventfd 唤醒 OpenThread 主循环发送 ACK，提交失败在 400ms 窗口内重试，不等待 HA。TCP 客户端使用独立传输线程，慢连接不会占用 Thread 线程。

完整报文有效且进入 RAM 队列后才发节点 ACK；重复组在确认相同内容后重发 ACK。最多四组并行重组，队列按组数和总字节限额约束。队列满时不发送成功 ACK，让节点按原策略重试或重新发现。HA 断线保留 RAM 队列；TCP 重连或 5 秒未确认后使用相同 delivery token 重发，HA 跨 BR 去重。HA delivery_reject 也移除对应队首，与原 ESP 实现一致。BR 重启、服务退出会丢失未交付的 RAM 数据；不承诺永久或精确一次投递。

backbone 切换只更新 LAN 发现，保留 Thread 会话和待投递队列。Thread 未附着时 data_plane_ready=false；UDP 关闭并在重新附着后恢复。`--no-attach` 模式只允许管理状态，没有 Thread UDP 业务端点。删除 YAML 块并重启即停止全部代理资源，不卸载其他功能。

## 源码来源

协议参考本项目配套 ESP 工程中的 thread_proxy_api/thread_proxy_api.cpp、udp_relay.cpp，以及 ESP32 thread_proxy_client 和 nRF52 thread_proxy_client_nrf52。HA 对应 custom_components/thread_proxy，协议 v1 / tsd2-v1。参考实现：[项目仓库](https://github.com/gasment/esphome_openthread_enhance_project)。客户端帧/实体生成留在节点，HA 原有设备与实体映射无需改成 Linux 版本。

## 构建与升级

从主项目根目录执行，使用已配置好 aioesphomeapi/PyYAML 的 Python。完整构建会包含原有检查、代理协议测试和代理互通测试。编译仍由用户执行。

```sh
cd 5-otbr/src
sh build.sh
```

新包位于 `5-otbr/src/otbr_host/otbr-deploy-bbr.tar.gz`，相对于项目根目录。新包带 VERSION；当前 `5-otbr/deploy/mi-gw2-otbr-0.2.0.tar.gz` 已同步用户构建并核对网关的发布件；旧 0.1.0 包已删除。

通过 SFTP 将新包上传到网关临时目录，然后执行：

```sh
cd /tmp
tar -xzf otbr-deploy-bbr.tar.gz
sh otbr-deploy/install.sh
```

在网关配置中添加上述顶层块，然后执行：

```sh
sh /data/otbr/check.sh
sh /data/otbr/restart.sh
```

日志 `THREAD_PROXY_RUNTIME_ENABLED` 表示代理对象已创建；监听成功还应看到 TCP 6065 日志和 `_thread-proxy._tcp` 发布。不能只凭端口开放判断节点代理全链路通过。

## 验证

完整构建自动执行代理测试；单独执行时，从主项目根目录进入 Host：

```sh
cd 5-otbr/src/otbr_host
sh build-proxy.sh
sh test-proxy.sh
```

协议测试不创建真实 Thread/UDP，覆盖明文/GCM、AAD/标签篡改、发现/ACK、去重、满队列、乱序分片、唯一上行消费者。TCP 互通使用官方 aioesphomeapi：独立明文/Noise、错误 key 拒绝、管理元数据、空实体列表、节点载荷分块、相同 token 重传及 HA ACK。

实机顺序：先让 HA Thread Proxy 集成发现并绑定 Linux BR，再使用既有节点客户端验证描述和状态，随后验证事件、睡眠节点 ACK、加密、HA 断线缓存/重连补发、满队列和多 BR 切换。已有 HA 和节点协议不要求改变；各端仍须使用一致的 UDP 加密模式。HA 的 BR 诊断设备若显示 ESPHome，是 HA 组件现有的硬编码展示，不影响数据协议。

从 Host 源码目录可执行 `sh test-thread-proxy.sh GATEWAY_ADDRESS` 进行默认只读管理验收。该脚本只在内存读取网关凭据，校验 6065 的设备身份、空实体列表和管理元数据，不争抢现有 HA 消费者，不向节点发包；输出的管理成功不等于节点到 HA 的完整验收成功。

运行后的 proxy_ready 只代表管理协议握手成功；data_plane_ready 代表 UDP 已附着可用。二者都不能单独证明节点状态已进入 HA。需要同时观察节点 ACK、HA 节点实体和重复事件行为。
