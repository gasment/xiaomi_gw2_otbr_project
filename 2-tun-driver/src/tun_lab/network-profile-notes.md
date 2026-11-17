# 网络布局验证

在 WSL 的 tun_lab 目录执行 `sh build-network-probe.sh`。该脚本不上传、不加载模块，也不构建完整内核。

已观察到原厂内核有 IPv6、Netfilter、conntrack、XFRM 及桥接过滤核心代码。默认 SDK 没有启用其中多项。候选配置启用 NET_CORE、IPV6、NETFILTER、NETFILTER_ADVANCED、NF_CONNTRACK，以及模块形式的 BRIDGE、BRIDGE_NETFILTER、TUN；olddefconfig 解析依赖。这是待验证候选，不是已经恢复出的原厂配置。其他网络开关不凭空开启。

原厂 bridge.ko 的 br_dev_init 中，dev 指针加 0x540 后被用作 netdev_priv(dev)。本 BSP 的 netdev_priv 定义是将 sizeof(struct net_device) 按 32 字节对齐；因此将其作为额外的布局锚点。偏移匹配仍不是整个结构体或全部 ABI 匹配的证明。

默认 BSP 初次实测 sizeof(net_device)=0x440，显著不匹配，不能据此构建后直接加载 TUN。执行后查看 probe-report.txt 和 network-layout-report.txt。脚本返回 MISMATCH 时属于诊断结果，不要使用强制加载绕过。

脚本保留 probe-report.baseline.txt 和 kernel-work/.config.before-network-profile。只修改独立的 kernel-work，不修改原始 source 或网关。

## 第二轮：PM 与字段偏移

运行内核导出了 __pm_runtime_*、pm_suspend、device_pm_wait_for_dev 等接口，而候选配置的 PM/SUSPEND 关闭。第二轮据此启用 PM、SUSPEND，并由 Kconfig 解析 PM_SLEEP 等依赖。不是通过填充结构体凑大小。

原厂 bridge.ko 的 br_dev_open 对 dev->_tx 的访问偏移为 0x280。br_dev_xmit 对 skb 的 data/head/len/dev/mac_header 访问偏移分别为 0xa8/0xa4/0x5c/0x14/0x9a。已加入测量与静态检查。全部匹配仍不能证明其余字段与运行时兼容。

重新执行 sh build-network-probe.sh。脚本仍不会上传、加载模块或改变网关电源状态。

纠正记录：先前把 br_dev_xmit 中写入 skb->cb 的 brdev 字段（偏移 0x18）误标成 skb->dev。原厂 br_handle_frame_finish 的入口明确从 r2+20（0x14）读取 skb->dev，与候选一致；不是通过调整结构体迁就错误偏移。
