# 正式 YAML 的配置校验包

本包复制用户指定的 `config.yaml` 和同目录 `secrets.yaml`，不换成 no-attach 测试模板。包含私密凭据，请留在自己的设备上。

上传包到网关 `/tmp` 后执行：

```sh
cd /tmp
tar -xzf host-config-check.tar.gz
sh /tmp/host-config-check/check.sh
```

入口仅调用 `mi-otbr-host config.yaml --check-config`。可以在当前 no-attach 测试仍运行时校验：不会打开 UART、创建 TUN、监听端口、应用 Dataset、启用 Thread、修改 sysctl、自启或 BLE。输出只列配置路径与公开的运行参数，不打印密码、API key、HA token、Thread network key 或 PSKc。

退出码：0=配置字段有效；1=配置错误。HA 名称映射已接入，旧的 CONFIG_PARTIAL 状态已移除。此入口仍只用于文件校验；正式运行请使用 otbr-deploy 包的 install.sh。

此包没有启动服务或安装入口。完整 YAML 功能接入与验收完成后，再准备正常部署。修改配置需要重新校验及打包；修改网关包内文件会导致原 SHA256SUMS 校验失败。
