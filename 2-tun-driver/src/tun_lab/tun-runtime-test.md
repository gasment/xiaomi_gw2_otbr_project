# TUN 临时运行验证

最小模块已能加载/卸载，TUN 已能加载并注册 10:200。该系统未自动创建 /dev/net/tun；BusyBox ip 也不含 tuntap 子命令。

在 WSL 执行 `sh build-tun-smoke.sh`，将生成的 tun-smoke 上传到网关 /tmp。不要将它放入启动脚本。

网关上，若 TUN 已卸载，先执行：

```sh
insmod /tmp/tun.ko
```

然后逐行执行：

```sh
mkdir -p /dev/net
mknod /dev/net/tun c 10 200
chmod 600 /dev/net/tun
chmod 755 /tmp/tun-smoke
/tmp/tun-smoke
```

如果设备节点已存在，跳过 mknod，先确认它是字符设备且主次设备号为 10、200。

测试程序使用非持久接口 mgtun0，若同名接口已存在会拒绝运行。它配置专用 ULA /64，向模拟对端发 ICMPv6，再从 TUN 读取请求并写入构造的回复，确认内核 ICMPv6 socket 收到回复。测试不会向物理网卡发送报文或改变默认路由；不测试真实外部 Thread 设备。

正常退出/进程结束关闭 TUN fd 后，临时接口及附属地址路由应自动消失。仅用于该驱动的受控实验，内核 ABI 尚未经完整证明；保留 Telnet 和重启恢复方式。

成功标志：TUN_IPV6_ROUNDTRIP_PASS。之后检查 `ip link show mgtun0` 应找不到接口，并检查 dmesg 有无新的 Oops、BUG、WARNING。此结果仍不等于 OTBR 已可用，也不代表所有 TUN 模式均兼容。
