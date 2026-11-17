# Combined Host: OTBR + real Native API diagnostics

Native API 协议验证已由用户完成：NATIVE_API_INTEROP_PASS，涵盖正确/错误 key、三类实体、心跳和重连。本阶段在独立进程中接入实际 OTBR 核心，不引入 ESPHome 框架。

## 当前源码新增

- mi-otbr-host 从运行时 YAML 读取 UART、实体、Dataset、骨干策略。
- 所有 OpenThread 操作在主事件循环执行；API 线程只读互斥锁保护的 Snapshot 缓存。
- 实际采样 RCP 存活、无线版本、Thread 附着/角色、邻居、子节点、RLOC16 与 ot1 身份字符串。未附着时身份缺失，避免发布伪造身份。
- 初始骨干自动选择，周期性跟踪链路和默认路由；切换时重建基础接口/ICMPv6/边界路由绑定，保留同一 Thread 实例及 UART。当前按 1 秒采样，未接入额外的 netlink 唤醒优化。
- no-attach 与 run 两种显式入口，见下文。

**源码尚未编译或实机验证。动态切换、TUN 实际流量和 Thread 入网均待测试。Web Linux 后端、Commissioner 控制、SRP 视图和 HA 名称映射尚未接入；不宣称完整移植完成。**

## 构建

用户执行：

```sh
cd ./5-otbr/src/otbr_host
sh build-host.sh arm
```

预期输出 HOST_BUILD_PASS，产物 build/host-arm/mi-otbr-host。使用单独构建目录，保留此前 core-arm 和 api-native 的成功产物。

可选先在本机验证编译及更新的骨干策略测试：

```sh
sh build-host.sh native
```

native 模式不自动运行 Host。没有网关 RCP 的开发机也可只检查编译与两项逻辑测试。

## 首轮运行入口（本轮暂不直接执行）

```sh
mi-otbr-host config.yaml --no-attach
```

这会初始化实际 Host 和 TUN，但关闭自动附着，不调用 apply_dataset，不应用 YAML Dataset，也不启用 Thread。普通 OT 平台设置和临时统计文件仍可能被访问，所以首轮应使用独立 /tmp 状态目录与独立 Thread 接口名，后续另行准备受控测试包。

运行时会独占 UART，不能并行运行 spinel-probe、otbr-agent 或其他 RCP 程序。现有无 Zigbee 参数的 openmiio 蓝牙服务继续保留。

实际运行模式：

```sh
mi-otbr-host config.yaml --run
```

仅在后续确认配置与网络条件后使用。此模式按 YAML 应用/保留 Dataset、设置 OMR，启用 Thread IPv6 和 Thread。force_dataset=false 优先保留已存的完整 Dataset；true 且字段一致时保留时间戳等元数据，字段变化时应用 YAML 网络字段。不会输出密钥。

## 当前内核限制

只读检查发现网关没有 /proc/net/ip6_mr*，IPv6 forwarding 为 0。因此本阶段的集成构建同时关闭 OTBR_BACKBONE_ROUTER 与 OT_BACKBONE_ROUTER_MULTICAST_ROUTING，避免默认依赖尚未确认可用的内核 BBR 组播转发。上游要求 BBR 和其组播功能成对启用，不能保留 BBR 却关闭该组播选项。

普通 Border Routing（OTBR_BORDER_ROUTING）继续启用，SRP/mDNS 与 Commissioner 编译支持保留；关闭 BBR 不等于关闭普通 Thread 边界路由。但当前不具备 BBR/MLR 组播转发能力，不能按完整 Thread BBR 部署，实际单播与本地服务仍需运行验收。

系统 forwarding、RA 接收策略、组播转发与最终防火墙还没有配置。本阶段没有改动 sysctl 或网关原启动链。不要以构建成功或 HA 实体出现认定 LAN↔Thread 路由已经可用。

Core 仍沿用已锁定依赖版本。热切换接入使用该固定版本的内部 InfraNetif 生命周期，因此升级依赖后必须重新审查；没有修改上游源码或跳过版本检查。

编译修正记录：首次集成构建因 BBR=ON/MR=OFF 被上游 backbone_router.h 拒绝。现配置在内核组播档位关闭时强制 BBR=OFF/MR=OFF，在启用档位时强制两者 ON，重新配置时会覆盖旧缓存，无需手动编辑 CMakeCache.txt。

内部头文件依赖修正：host_main.cpp 使用固定版本的 posix/platform/infra_if.hpp，故 mi-otbr-host 显式继承 ot-config-ftd、ot-config、ot-posix-config，并使用与上游 POSIX 目标一致的 FTD=1/MTD=0/RADIO=0。这样同时获取 src/core 等内部 include 路径和功能宏，不能只补一条头文件搜索路径。

运行目录修正：Linux 上游默认 /run/openthread-%s，但原厂网关没有 /run。现通过共用 ot-posix-config 将 daemon 与 ot-ctl 的 basename 统一为 /var/run/openthread-%s，不要求修改只读根分区。测试配置和客户端统一使用 Native API 标准端口 6053。

重新构建后，在 WSL 执行 sh package-noattach.sh 生成新的 host-noattach-probe.tar.gz；上传新包后再运行原测试入口。打包器检查二进制本身包含修正后的 CLI 路径，不把仅更新了 CMake 标志的旧产物误打包。测试启动失败会完整打印日志，避免 tail 进程未及时刷新时只显示退出码。

## 生命周期

SIGINT/SIGTERM 请求主循环停止，API 线程退出后由 OTBR 清理 TUN 与接口对象。上游不可恢复错误可能直接结束进程；平台复位请求以状态码 8 退出，避免跨活跃 C++ 线程 longjmp。尚未添加自启或自动重启服务。
