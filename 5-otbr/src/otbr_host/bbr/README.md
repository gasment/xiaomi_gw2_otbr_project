# BBR 内核能力核查

当前普通 IPv6 边界转发已通过用户实测，但 Linux 集成构建仍为 BBR=OFF、Multicast Routing=OFF，不能把它作为 ESP thread_br 的完整能力对齐版本。

标准 Linux 转发后端依赖 MRT6_INIT、MRT6_ADD_MIF、MRT6_ADD_MFC。候选 Linux 4.9 配置没有启用 CONFIG_IPV6_MROUTE，但候选配置不等于网关实际配置。应先查询运行内核，避免直接启用 BBR 或刷写内核。

本工具只打开一个 IPv6 raw socket 并查询 MRT6_VERSION，不调用 MRT6_INIT，不注册多播路由器身份，不加入组、不发送数据包、不读写 UART、不修改 sysctl、接口或服务。以 root 执行。编译只由用户执行。

## 使用步骤

WSL 项目目录执行：

```sh
sh build-bbr-probe.sh
```

上传生成的 bbr-kernel-probe.tar.gz 到网关 /tmp，然后在网关执行：

```sh
cd /tmp
tar -xzf bbr-kernel-probe.tar.gz
sh /tmp/bbr-kernel-probe/probe.sh
```

无需安装或停止现有 OTBR，执行后把完整输出贴回。

## 结果解释

- BBR_KERNEL_MROUTE_API_PRESENT：运行内核提供只读多播 API；仍需进一步验证标准后端的初始化与转发。
- BBR_KERNEL_MROUTE_API_UNSUPPORTED：标准内核接口不可用；不要直接把构建开关改为 ON。下一步评估用户态多播后端。
- BBR_RAW_SOCKET_UNAVAILABLE / INCONCLUSIVE：权限或环境不足，不能据此判定支持情况。

## 缺少内核支持时的适配方向

锁定 OpenThread 源码已有非 Linux 平台的用户态多播实现，包含 Primary BBR 门控、MLR 监听过滤、作用域/源地址/Hop Limit 校验、去重和限速。可评估将其 BPF 抓包/注入层替换为 Linux AF_PACKET，保留上游转发策略。该 Linux 适配现已接入独立实验构建档位，由用户编译、部署，基础 MLR 与双向多播已实测通过；完整验收范围见 ACCEPTANCE.md。助手没有运行编译或部署。

不把任意 LAN 组播无条件注入 Thread，也不把 realm-local ff03 组播跨 LAN 转发。适配需要验证 Primary/Secondary 切换、MLR 注册/过期、双向组播、多个 BR 防重复以及 Wi-Fi/Ethernet 切换。


## 用户态 BBR 实验版

实机 MRT6_VERSION 查询已返回 ENOPROTOOPT/92，且 /proc/net/ip6_mr_vif 和 ip6_mr_cache 缺失。当前采用 AF_PACKET 用户态后端，不改原厂内核或 RCP 固件。Thread 核心的 BBR/MLR 状态机保持上游实现，仅适配 packet tap 平台层。构建时生成严格匹配锁定源码的副本，不修改 vendor checkout。

### 构建

```sh
cd ./5-otbr/src/otbr_host
sh build-release-bbr.sh
```

这是用户执行的编译/验证流程。实验程序位于 build/host-bbr-arm，程序包为 otbr-deploy-bbr.tar.gz；不会覆盖稳定版 build/host-arm 或 otbr-deploy.tar.gz。普通 build-release.sh 仍生成 BBR 关闭的稳定版。

### 部署

将 otbr-deploy-bbr.tar.gz 上传网关 /tmp，在网关执行：

```sh
cd /tmp
tar -xzf otbr-deploy-bbr.tar.gz
sh /tmp/otbr-deploy/install.sh
```

安装保留网关 YAML、Dataset 状态和 BLE 隔离；已有安装会保存上一版程序以供 rollback。实验版不新增 YAML 字段，不更改密钥，不刷写内核、TUN 或 RCP。

### 第一轮核查

WSL 执行：

```sh
sh test-deployed.sh
sh test-bbr.sh
```

test-bbr.sh 只 GET /bbr，不强制抢占 Primary、不注册多播监听、不发送测试包。Web 认证沿用网关 YAML，在内存解析，不保存或打印凭据。

- state=secondary：候选已启用，当前有其他 Primary。open_taps=0、forwarder_ready=false 是预期状态，不代表故障。
- state=primary 且 open_taps=2：用户态抓包和注入通道已建立，仍需真实多播验证。
- state=disabled：查看日志中的 [bbr] 和 McastRtMgr。AF_PACKET/BPF 不可用时不启用本机 BBR 候选，但保留普通 Thread/单播服务。
- listeners 为本机 Primary 持有的 MLR 表；没有终端订阅时为空，不能把空表当作协议故障。
- packet_counters 中 captured_* 是捕获帧数，injected_* 是成功注入另一接口的帧数，均不等于终端应用已收到或已执行。

启动日志应出现 BBR_BACKEND=userspace-af-packet；原内核仍不会出现 ip6_mr* 文件。成功不能以这些内核文件判断。

### 多播验收范围

只有本机承担 Primary 时才转发，Secondary 不复制 Primary 的流量。已有多个 BR 时，先报告 /bbr 状态，再安排受控窗口验证本机 Primary；当前脚本不会停用其他 BR 或强制本机注册。

在真实终端订阅一个 scope>=4 的测试组后，分别验证 LAN→Thread 和 Thread→LAN 的应用收包、源地址/负载、低速连续包丢失情况；观察 MLR 注册/过期和 injected_* 增长。realm-local ff03、link-local、单播、Hop Limit<=1、mesh-local/链路本地源地址不跨 LAN 转发。然后验证 Primary/Secondary 角色切换、多 BR 防重复以及 eth0/wlan0 切换。

抓包层不会开启混杂模式或 all-multicast，LAN 组成员关系沿用上游根据 MLR 表建立的 IPV6_JOIN_GROUP。经典 BPF 在内核中过滤 IPv6 多播 scope>=4；每次主循环最多读取 32 帧，转发沿用上游的去重和限速。当前进入 Thread 默认总速率限制为 30 包/秒、每组 10 包/秒；这不是无线吞吐能力保证。policy 日志计数每 10 秒汇总一次。

### 回退

在网关执行：

```sh
sh /data/otbr/rollback.sh
```

回退到安装前保存的程序，保留用户 YAML。也可重新安装此前保存的稳定版 otbr-deploy.tar.gz。助手未运行编译、上传或启用此实验版；实机结果由用户后续验证。


补充：锁定版本的 IPv6 核心已经把多播交付 Host；无需调用已移除的 otIp6SetMulticastPromiscuousEnabled。只有 Primary 打开用户态转发通道，降为 Secondary 后关闭通道。这不修改物理网卡的混杂模式。Linux PACKET_AUXDATA 标记校验和尚未完成时，用户态会补全 UDP/ICMPv6 校验和；无法安全补全的分片/其他协议会丢弃并计入 errors，不对普通接收包“修复”校验和。独立黄金报文回归加入用户构建流程，助手未运行 C++ 编译或这些 C++ 测试。


## 最新实测状态

2026-11-16：用户已验证 MLR 注册、Primary BBR 用户态双向多播和实际两端收包，详情见 [ACCEPTANCE.md](ACCEPTANCE.md)。仅状态查询脚本无法自动判断应用收包，不会据此输出完整多播通过。
