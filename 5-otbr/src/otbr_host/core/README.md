# OTBR 核心基线：构建入口

上一阶段用户已用 GCC 15.2.0 完成 native 构建，配置解析和骨干策略两项测试全部通过。本阶段先建立可交叉构建的上游核心基线，再接入独立 Native API 与原 Web，不把基线 Agent 当作最终 Host 程序。

源码在 deps.lock.json 锁定：OTBR 285bcb549edcfe6823269b4df2f0982298bc1e56；OpenThread 3de409682fa2a28452d91ec00c2614b70f986b75。TLS 来自其固定 mbedTLS 子模块，不依赖网关安装 TLS 包。

源码规则：Host API 12、最低 RCP API 4；已测无线固件 API 10、最低 Host API 4。因此双方版本门槛满足，具体能力与运行时兼容仍需验证。没有修改版本常量强行跳过检测。

## 用户执行构建

WSL 若缺工具，安装：

```sh
sudo apt install cmake make g++ git pkg-config python3
```

检查与准备固定源码（当前工程已下载，脚本会复核）：

```sh
cd ./5-otbr/src/otbr_host
sh prepare-core.sh
```

ARM 静态构建：

```sh
sh build-core.sh arm
```

构建结束脚本检查 ELF32 ARM、无 PT_INTERP、无 DT_NEEDED，以及未启用 D-Bus/systemd 等依赖，输出 CORE_BUILD_STATIC_CHECK_PASS 和实际文件位置。不会运行产物或访问网关。

也可选本机上游基线构建：

```sh
sh build-core.sh native
```

native 基线不会自动运行。这一轮不必重复上一阶段已通过的配置测试；只有代码变化或新失败才补测。

## 明确的构建范围

保留 Thread 1.4 Host、UART HDLC、TUN、边界路由、Backbone Router、SRP Server、内置 mDNS、SRP Advertising/Discovery Proxy 和 Commissioner。

关闭 D-Bus、OpenWrt、上游 Web/REST、外部 mDNS 服务、TREL、NAT64、DHCPv6-PD、上游 DNS 转发和上游 firewall/ipset 功能。原 Web 与独立 Native API 将接入自有进程；并未因此取消用户要求的 Web/Native API 功能。

禁用 firewall 仅用于当前受控构建/兼容性基线，**不是最终部署防火墙方案**，目前不要接入自启或对外开放生产 Thread 网络。IPv6 路由与组播运行时条件仍需在网关检查。

系统的 systemd、DBus pkg-config 检测被隔离，避免误链接 WSL x86_64 库。跨编译的 C/C++、binutils 均使用已有 ARM musl 工具链。

## 下一步验证边界

先提供构建输出；之后再准备网关上的受控 RCP 初始化测试。此阶段不要直接启动 Agent、导入真实 Dataset、启用自动附着或改动网关网络。Agent 不是此前 GET-only spinel-probe，初始化可能复位/配置无线芯片。

动态 backbone 仍由自有运行时层控制。上游 Agent 的候选接口切换会走退出/恢复路径，尚未替换为保持 Thread 实例的接口重绑。此阶段不宣称完成热切换。

本阶段尚未由助手或用户运行 core 构建；只完成了固定依赖下载、源级兼容检查、脚本语法和清单检查。构建及实机结果需逐步记录。
