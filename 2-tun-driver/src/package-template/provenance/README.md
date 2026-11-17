# 来源与匹配范围

模块来自本项目 tun_lab/tun/tun.ko，保留调试信息，未重新编译或 strip，与已测试文件逐字节一致。

内核源码候选：https://github.com/linux-chenxing/linux-chenxing-vendor-slop/tree/ikayaki_dlm00v014
项目输入归档：linux-chenxing-vendor-slop-ikayaki_dlm00v014.zip。
TUN 源文件副本见 source/tun.c，构建配置见本目录 kernel.config。完整内核源码与头文件可从上述仓库获取。source/Makefile 是本项目外部模块构建入口。
模块工具链：Arm GNU 9.2-2019.12，arm-none-linux-gnueabihf-gcc 9.2.1。
运行内核原厂编译器为 GCC 9.1.0。没有修改运行内核镜像、设备树或无线芯片固件。

原厂匹配证据包括：vermagic、module 大小/初始化及卸载指针偏移、netdev_priv 偏移、_tx 和 skb 的多个字段偏移、125 个必需导入符号均存在于运行内核导出表。修正后的 skb->dev 偏移为 0x14，0x18 对应桥接控制缓冲区字段，原先的错误标注已纠正。

配置和这些锚点不代表完整恢复原厂配置；用户提供的实机测试补充了基本接口和 IPv6 收发验证。安装器及启动器均要求 /proc/version 与测试内核完全相同，不只检查 4.9.84。
