# TUN 模块实验：第一阶段

目标：先构建一个用于静态 ABI 测量的最小模块，核对原厂 ccm.ko 的模块大小、初始化和卸载函数偏移及 vermagic。不是完整的 TUN 兼容性证明。

全部命令在 WSL Ubuntu 执行，不在网关执行。脚本不会上传或加载任何模块。

```sh
sudo apt install -y build-essential flex bison bc libssl-dev libelf-dev curl xz-utils
cd ./2-tun-driver/src/tun_lab
sh fetch-toolchain.sh
sh build-probe.sh
```

fetch-toolchain.sh 下载 Arm 官方 GCC 9.2-2019.12 工具链，压缩包约 252 MiB；已核实下载地址可访问。原厂为 GCC 9.1.0，选同一主版本减少旧内核构建差异，不代表编译器版本相近就能保证 ABI 兼容。内核模块不链接 libc。

build-probe.sh 第一次会把 BSP 复制到独立 kernel-work，额外占用约 665 MiB；恢复 ZIP 中的可执行权限，然后运行 olddefconfig、modules_prepare 和最小外部模块构建。原始 source 目录不修改。首次保持候选自带配置，不提前猜测网络配置。

预期原厂基准：module 大小 0x200、init 偏移 0xe8、exit 偏移 0x1cc。输出报告保存为 probe-report.txt。匹配只代表第一关通过；不匹配时脚本返回失败，不要执行 insmod。

下一阶段根据报告调整配置，再启用 NET_CORE=y、TUN=m，构建 tun.ko。之后还要核对完整导入符号与运行内核导出、网络结构布局，最后才进行可控加载验证。没有启用 MODVERSIONS 只代表缺少 CRC 拦截，不能视为兼容性保证。

本目录创建时只检查了脚本语法，尚未实际执行准备和编译步骤。
