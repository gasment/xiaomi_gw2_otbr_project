# BBR 实机验收记录

日期：2026-11-16。以下为用户提供的实测结果，助手未替用户编译、部署或发送测试流量。

## 已验证

- 原厂 Linux 4.9.84 查询 MRT6_VERSION 返回 ENOPROTOOPT/92，ip6_mr_vif 和 ip6_mr_cache 缺失。
- 用户态 AF_PACKET 实验版成功构建部署，原厂内核和 RCP 不变。
- 普通 Thread Dataset 附着、远端 Router Ping、Native API/HA、Web、mDNS 及 HA 名称映射回归通过。
- 本机 Primary BBR，RLOC16=0x6800，sequence=53，MLR timeout=3600 秒。
- ESP32-C6 独立外部测试组件订阅 ff15::1234，UDP 18515；网关 MLR 表实际出现该组，最后一次查询剩余 timeout=3520 秒。
- LAN→Thread：C6 日志收到与 Windows session 匹配的 seq=1..10，10/10 到达。
- Thread→LAN：Windows 日志收到 C6 session=0ac0eb3f 的 seq=1..10，10/10 到达。
- 两次快照中 captured_thread/injected_lan 从 10/10 增长到 20/20，captured_lan/injected_thread 从 10/10 增长到 20/20；open_taps=2、errors=0。
- Windows 曾只显示 LISTEN 且计数为 0；允许来自 Thread 测试前缀的 UDP 18515 入站，并按先监听后复位的顺序重测后接收成功。测试规则已由用户删除。

结论：当前实验环境下，MLR 注册和经小米 Primary BBR 的基础双向 IPv6 多播已经实测通过。此结论依据两端应用日志与网关转发计数，不只是 socket 已打开或发送端返回成功。

## 尚未验证

- MLR 正常取消及自然超时后的组成员关系撤销、停止转发。
- Primary/Secondary 切换和多 BR 条件下的重复转发抑制。
- 此 BBR 用户态后端在 Wi-Fi/Ethernet 切换后的 MLR 恢复与双向多播。
- 不同休眠终端、突发流量、长时间运行、丢包和限速边界。
- DUA、不同 Thread 分区/Domain 等完整 BBR 能力；不能把基础多播通过当作全部功能或认证通过。
- ESP32-C6 日志曾有 SRP ResponseTimeout，仍需单独排查，不因多播测试通过而视为已解决。

## 后续顺序

先验证多播场景的 backbone 切换，再验证 MLR 撤销/超时与 Primary/Secondary 交接。测试端继续保留；test-bbr.sh 只做 GET 状态核查，不自动注册监听、改变角色或发包。
