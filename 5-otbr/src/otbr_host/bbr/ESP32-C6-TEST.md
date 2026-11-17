# ESP32-C6 真实 MLR / 双向多播测试

适用当前小米网关用户态 BBR 实验版。用户已验证本机 Primary、forwarder_ready=true，但 listeners 为空、收发计数为 0，因此尚未证明真实多播收发。

本测试使用独立 ESPHome 外部组件 thread_multicast_test，不修改原 openthread 组件，也不配置或改写 Dataset、密钥、SRP、BBR 角色或 RCP。只在用户为 C6 添加该组件后运行。助手不创建实际 YAML、不编译、不烧录或重启任何设备。

## 1. 为现有 C6 配置添加外部组件

将下面这一项合并到已有 external_components 列表，不要覆盖原来的 openthread 来源。WSL 本地组件目录：

```text
./5-otbr/src/otbr_host/esp_components
```

```yaml
external_components:
  - source:
      type: local
      path: ./5-otbr/src/otbr_host/esp_components
    components: [thread_multicast_test]

thread_multicast_test:
  group: "ff15::1234"
  port: 18515
  send_interval: 5s
  send_count: 10
```

保留该节点当前有效的 esp32、ESP-IDF、openthread、Dataset、logger、api 等配置。若用 Windows 而非 WSL 执行 ESPHome，path 可改为可访问的 UNC 路径：

```text
.\5-otbr\src\otbr_host\esp_components
```

组件仅支持 ESP32-C6 + ESP-IDF，依赖已有 openthread。用户自行选择运行配置校验、编译和烧录；助手未执行这些操作。

## 2. 功能与报文

- 成功附着后订阅 ff15::1234（临时、site-local 多播组），在 Thread 内部 UDP 18515 端口接收测试消息。
- SUBSCRIBED 仅表示本地组订阅成功，不代表 MLR 已成功；必须查看网关 listeners。
- 每 5 秒发送一次，最多成功发送 10 条，随后停止发送、保留接收。每条带启动 session 和递增 seq，便于识别丢包、重复，避免相同负载被去重。
- 发送使用优先的 ULA/global IPv6 地址并排除 Thread mesh-local/link-local，通常是节点 OMR；没有合适地址时输出 WAIT_SOURCE，不用错误的 mesh-local 源地址。
- 发送载荷为 MI-BBR-TEST/1;source=node;session=...;seq=...。LAN 发包使用 source=lan；节点收到后只记录日志，不应答或执行命令。
- OT 接收回调仅写入小型有界队列，在 ESPHome 主线程输出日志；不在回调里输出日志或发送测试数据。
- 所有 OT API 访问持有 ESP-IDF OpenThread 锁。该测试组件不更换网络实例或接管网络启动。

## 3. 确认 MLR

用户烧录 C6 并查看日志，等待出现：

```text
[thread_multicast_test] SUBSCRIBED group=ff15::1234 port=18515
```

然后 WSL 的 otbr_host 目录执行：

```sh
sh test-bbr.sh
```

要求网关 state=primary、forwarder_ready=true，listeners 中出现 ff15::1234。MLR 可能稍有延迟，可等待约 30 秒后重查。若仍为空，先提供 C6 日志和网关状态，不手工伪造监听表或强制启动转发。

## 4. Thread → LAN

在 Windows PowerShell 开始接收。网卡索引 22 来自用户当前以太网；若网卡变化，先用 Get-NetIPAddress 确认。使用 Windows 本机，避免 WSL NAT 对 IPv6 组播的限制。

```powershell
& '.\5-otbr\src\otbr_host\bbr\lan-multicast.ps1' -InterfaceIndex 22 -Mode receive
```

看到 LISTEN 后，由用户按 C6 的 EN/复位按钮重新开始一轮有限发送（或在首次烧录自动重启前先开启监听）。窗口默认监听 90 秒；预期收到 source=node、session/seq 与 C6 TX 日志一致的 10 条。接收窗口不发送任何包，退出会关闭 socket 并退出 LAN 多播组。

## 5. LAN → Thread

确认 C6 仍在线、网关 listeners 中仍有测试组。另一个 Windows PowerShell 执行：

```powershell
& '.\5-otbr\src\otbr_host\bbr\lan-multicast.ps1' -InterfaceIndex 22 -Mode send
```

默认每秒发送一条，共 10 条，Hop Limit=16，并绑定该 LAN 网卡可用的非链路本地 IPv6 源地址。C6 应出现对应 source=lan、session/seq 的 RX 日志。仅有 Windows TX 输出不算通过。

## 6. 核对实际经过小米 BBR

WSL 再执行 sh test-bbr.sh，比较测试前后的计数：

- Thread→LAN：captured_thread、injected_lan 增长，Windows 实际收到对应节点报文。
- LAN→Thread：captured_lan、injected_thread 增长，C6 实际收到对应 LAN 报文。
- 检查 errors、丢失或重复序号。两个方向都有实际收包且小米注入计数对应增长，才能记录双向多播通过；不能只依赖其他 BR 或发送端日志。

## 7. 清理

Windows 脚本退出自动关闭 socket，不增加主机路由或修改接口。将 thread_multicast_test 配置从 C6 移除并由用户重新编译/更新即可彻底移除测试；不要删除已有 openthread/Dataset 配置。正常关机回调会释放本组件创建的 UDP socket 和自身订阅；掉电时 MLR 表按协议超时清理。

2026-11-16 已由用户在 C6 编译部署并验证双向多播，实测记录见 ACCEPTANCE.md。组件是短期诊断工具，不作为生产广播接口，也不替代低功耗终端的组订阅和投递机制设计。


## Windows 入站规则（本轮实际排查步骤）

本轮最初 Windows 收包为 0，但网关已显示 injected_lan=10；添加以下针对性入站允许规则，并确认先启动接收窗口后再复位 C6 后，Windows 收到完整 10 包。管理员 PowerShell 执行：

```powershell
New-NetFirewallRule -Name 'OTBR-BBR-Test-18515' -DisplayName 'OTBR BBR multicast test' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 18515 -RemoteAddress 'EXAMPLE_IPV6_ADDRESS' -InterfaceAlias '以太网 2' -Profile Any
```

RemoteAddress 应按实际 Thread 测试节点的 OMR 前缀填写，InterfaceAlias 使用测试电脑的 LAN 网卡，不关闭整个防火墙。本轮实际测试结束后已删除规则；以后重测若需要，请重新添加并在完成后删除：

```powershell
Remove-NetFirewallRule -Name 'OTBR-BBR-Test-18515'
```

网关注入计数只表明进入网卡发送路径，必须结合端点实际收包判断，不能单凭 sendto 成功宣称 LAN 已收到。
