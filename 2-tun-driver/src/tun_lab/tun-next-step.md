# 单独构建 TUN

在 WSL 执行：

```sh
cd ./2-tun-driver/src/tun_lab
sh build-tun.sh
```

使用现有已测配置及 BSP 的原始 drivers/net/tun.c，在 tun/ 中作为单独外部模块构建，不构建完整内核或全部网络驱动。生成 tun/tun.ko，保留调试信息供后续分析。

脚本先核对模块 ABI 和已恢复的网络字段锚点，然后检查 TUN 的模块头与全部非弱导入符号。依赖以真实运行网关的 __ksymtab_* 快照为准；原 SDK 的 Module.symvers 不一定包含后来启用功能对应的符号，modpost 的缺失警告需结合实机检查判断，不能直接忽略。

报告：tun-static-report.txt；完整导入符号：tun-imports.txt。不上传、不加载驱动。出现 STATIC_SYMBOL_CHECK_FAIL 或 MISSING 时先分析，不要强制加载。即使 PASS，也尚未完整验证 sock、内联访问字段等全部 ABI，不构成运行安全保证。

下一步由用户选择受控实机验证，先核对当前网关与符号快照的固件版本一致；再讨论加载、创建临时 TUN 接口及数据收发测试。
