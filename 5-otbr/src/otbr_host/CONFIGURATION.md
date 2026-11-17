# 网关运行时 YAML

唯一正式配置是网关上的：

```text
/data/otbr/config.yaml
/data/otbr/secrets.yaml
```

用户使用 MobaXterm SFTP 或 SSH 编辑，Host 每次启动直接读取配置。secrets.yaml 可选：只有使用 !secret 才需要该文件；也可以在 config.yaml 内直接填写。整值 ${substitution} 从 substitutions 解析。任何 WSL 配置都不自动同步到网关，也不参与程序打包。

修改后，在网关执行：

```sh
sh /data/otbr/restart.sh
```

只校验、不启动无线：

```sh
sh /data/otbr/check.sh
```

| YAML | 行为 |
| --- | --- |
| device / api | 设备身份、Native API 端口（默认 6053）；encryption 可省略，此时使用明文；配置 key 后仅允许 Noise |
| backbone | 可省略或设 auto；也支持包含 interfaces、policy、switch_delay 的映射，动态选择 Wi-Fi/以太网；兼容旧 backbone_config，不能同时使用两种映射 |
| rcp | 可整体省略，默认 /dev/ttyS1、460800、hardware；仅需要覆盖默认参数时填写 |
| output_power | thread_br 下可选整数，单位 dBm，范围 -26～20；省略则不覆盖 RCP 功率；0 和负数有效 |
| rcp_connectivity | thread_br 下的 Connectivity 实体；兼容旧 rcp 内嵌写法，不能重复定义 |
| web | Web 端口、Basic 用户名与密码 |
| commissioner | 后端开关、ID；启用页面不等于自动打开配网窗口 |
| thread_network_config | --run 下应用/保留 Dataset 并启动 Thread；force_dataset:true 时配置差异在启动时应用 |
| omr_prefix | 自定义 OMR；省略则由核心自动选择 |
| ha_url / ha_token | 后台 HTTP/HTTPS HA 身份名称查询、冲突/过期保护 |
| ha_ca_file | 网关上的 CA 路径，默认 /data/otbr/certs/ca-certificates.crt；用户可放置自己的 CA 文件 |
| thread_identity 及诊断项 | Native API 实体 ID、名称、图标、类别 |
| thread_interface / state_directory / update_interval | 可省略，分别默认 wpan0、/data/otbr/state、15s |
| used_psram | 兼容项，明确警告 Linux 使用普通内存 |

ESP32 GPIO 不用于 Linux UART；已验证硬件配置为 /dev/ttyS1、460800、hardware。secret 与字段错误在无线初始化前拒绝，不把测试值代替用户配置。校验报告不输出密钥或令牌。

程序包只有公开 `.example` 文件。首次缺少配置时创建待填写的示例；现有 config.yaml 不使用 !secret 时，不补建 secrets.yaml。升级只更新程序和示例，不替换实际配置。程序回退也保留当前用户 YAML，旧版本不认识新增字段时由用户编辑解决。证书默认仅在缺少时创建，后续保留用户版本。

项目中的实际 YAML 和私密副本已移除。正式配置通过网关 SSH/SFTP 管理，与构建分离。

## 发射功率

在网关 `/data/otbr/config.yaml` 现有 `thread_br:` 下增加一行，不要重复创建整个配置块：

```yaml
thread_br:
  output_power: 20
```

填写整数，不带 `dBm` 后缀。安装支持此字段的新版本后，运行 `sh /data/otbr/check.sh` 校验，再执行 `sh /data/otbr/restart.sh` 生效。省略该字段时 Host 不发送功率覆盖请求，不强制设置为 0、5 或 6。

Host 通过 Radio URL 的 `tx-power` 参数设置 Spinel/RCP，并由上游 Spinel 恢复逻辑在 RCP 恢复时重新应用。启动日志分别记录 `requested` 请求值和 `readback` 回读值；请求被驱动拒绝时按上游初始化失败处理，不伪装成成功。

Web 发射功率始终来自 `otPlatRadioGetTransmitPower()` 的实时 RCP 回读。量化或通道限制可能使回读与 YAML 不同，不将设定值当作测量值；读取失败显示 `-`。该读数是 RCP 的报告值，不是射频仪器测得的天线端功率或 EIRP。
