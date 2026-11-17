# SRP 实机验收

使用现有 ESP32-C6 的 ESPHome OpenThread SRP 客户端，脚本只负责读取目标网关的 `/srp`。不需要为了测试先刷新固件，不改 Dataset、不强制开启服务器、不操作其他 BR。

WSL 先检查当前服务状态：

```sh
cd ./5-otbr/src/otbr_host
sh test-srp.sh
```

默认目标 `GATEWAY_ADDRESS`，Web 端口与凭据只从该网关的运行时 YAML 读入内存，不保存到项目。

如果输出 `SRP_NOT_SERVING`（stopped/disabled/端口 0），先定位服务器和 Network Data 发布选择问题；客户端为零不会导致 SRP 自动停止。多个 BR 中被选为 Primary BBR，不等于该 BR 同时被选中提供 SRP。此时可在网关读取日志：

```sh
grep -E 'SrpServer|NetDataPublshr|AdvertisingProxy' /var/log/mi-otbr.log | tail -n 80
```

如果状态为 running 且端口非零，启动针对实际 C6 hostname 的观察。以下名称来自此前节点日志，若已改名请替换：

```sh
sh test-srp.sh --expect-host simple-usb-switch-b26890 --wait 180
```

看到 `WAITING_FOR_HOST` 后手动重启现有 C6 节点，保留串口或无线日志。脚本要求该网关注册表存在未删除的匹配主机、IPv6 地址和 `_esphomelib._tcp`、6053 服务记录。节点若实际配置了不同 Native API 端口，本脚本的 6053 验收条件需相应调整。

`SRP_REGISTRATION_PRESENT` 表示首次查询已有记录；`SRP_REGISTRATION_OBSERVED` 表示观察期间出现匹配记录。两者都不代表已验证更新、租约续期、失效移除或 LAN mDNS 发布。

完整端到端验收还要确认节点实际注册成功，并从 LAN 用 zeroconf/mDNS 浏览发现相应服务且能解析节点地址。HA 已连接或有日志中的一次 TCP 连接不能单独证明本机 SRP 和后续发布链路正常。在多 BR 网络中，节点可能选择其他 SRP 服务器，不能将其他 BR 的成功当作小米网关的验收结果。

脚本仅 GET `/srp`，SSH 仅读取配置；不发送控制请求、不打开 Commissioner、不启动或停止网关服务。

## 已定位的多 BR 停止原因

2026-11-16 只读实机查询：小米 `RLOC16=0x6800`，SRP 模式 `unicast`、状态 `stopped`、auto-enable 为 Disabled。Thread Network Data 已有其他 BR 的两条 DNS/SRP 单播服务（enterprise 44970、service 0x5d），分别来自 `0x9000` 和 `0x2c00`。当前锁定 OpenThread 的默认单播 SRP 目标数量为 2，本机因服务发布选择保持停止；不是未实现接口，也不是等待客户端。

## 临时启用本机服务以做定向注册测试

以下命令由用户按需在 WSL 执行。`ot-cli.sh` 通过短时 SSH 转发访问已运行的 Host Unix socket，不需要编译、上传工具或重启 Host。下列设置会临时改变本机 SRP 发布状态，也可能触发其他 BR 重新评估服务记录；不应将该测试模式作为部署默认策略。

```sh
cd ./5-otbr/src/otbr_host
sh ot-cli.sh srp server disable
sh ot-cli.sh srp server addrmode unicast-force-add
sh ot-cli.sh srp server enable
sh test-srp.sh
```

每一步应返回 Done，否则停止后续步骤，按下方恢复。force-add 用于绕过本机 Publisher 的竞争等待、直接启动服务，不保证 C6 自动选择这台服务器；下一步需要明确将测试节点的 SRP 客户端指向本机公布的地址和端口。仅看到本机 running 尚未完成真实注册验收。

只读获取本机地址及服务端口：

```sh
sh ot-cli.sh ipaddr mleid
sh ot-cli.sh srp server port
```

测试后恢复此次实机查询得到的原始配置（普通 unicast，server enabled，auto-enable Disabled）：

```sh
sh ot-cli.sh srp server disable
sh ot-cli.sh srp server addrmode unicast
sh ot-cli.sh srp server enable
sh test-srp.sh
```

恢复后再次 stopped 可以是正常竞争结果。`ot-cli.sh` 本身可执行配置命令，只有 state、addrmode 不带参数、netdata show 等查询为只读；不要将设置命令当作查询执行。

## C6 定向注册组件

`esp_components/thread_srp_test` 是独立测试组件，不改动 `thread_multicast_test` 或 ESPHome 的原 openthread 组件。它等待 ESPHome 已设置主机名和服务后，停止原 SRP 自动选择，再用显式地址启动同一个客户端。原有主机、服务、TXT、密钥与回调均沿用，不创建假注册记录。组件只记录服务状态，不替换 ESPHome 错误回调。

在 C6 现有 external_components 的对应本地 source 中，将 `thread_srp_test` 加入 components 列表；不要重复同名顶层块。WSL 示例：

```yaml
external_components:
  - source:
      type: local
      path: ./5-otbr/src/otbr_host/esp_components
    components: [thread_multicast_test, thread_srp_test]

thread_srp_test:
  server: "EXAMPLE_IPV6_ADDRESS"
  port: 53537
```

上述目标来自本轮用户实际查询，不是长期固定参数。若重启/重建 Host 或重新启用 SRP 后地址、端口变化，以 `sh ot-cli.sh ipaddr mleid` 和 `sh ot-cli.sh srp server port` 的新结果为准。

用户自行编译并更新 C6。助手只进行 Python 校验，不执行 ESPHome 编译或刷机。观察 C6 日志：

- `TARGET_STARTED`：只表示客户端已开始使用指定服务器，尚未证明注册成功。
- `SRP_TARGET_PENDING`：查看主机/服务状态及 ESPHome 自身的 SRP 错误日志，例如超时或冲突。
- `SRP_TARGET_REGISTERED`：指定目标仍匹配，主机和 `_esphomelib._tcp` 均处于 registered；再与网关 `/srp` 注册表相互核对。

WSL 观察脚本中的 hostname 请使用 C6 日志里 `host=` 的实际值：

```sh
sh test-srp.sh --expect-host simple-usb-switch-b26890 --wait 180
```

要验证新注册，建议先启动观察脚本，再让更新后的 C6 启动；`SRP_REGISTRATION_PRESENT` 仅表示已存在记录，不能单独证明本轮更新发生。真实节点状态和本机注册记录同时匹配后，SRP 定向注册这一段才算通过；LAN mDNS 发布另行检查。

清理时从 C6 配置移除 `thread_srp_test:`，由用户重新编译并更新；新启动后恢复 ESPHome 原有 SRP 自动选择。再执行上述网关恢复命令。单独重启仍含该组件的 C6 会继续定向选择，不会恢复自动模式。

## 本轮首次注册失败的已确认事实

2026-11-16，C6 使用 `simple-usb-switch-b26890` 向 53537 发起更新。网关日志已显示收到并解析更新，且包含真实 OMR 地址；随后 `SrpAdvProxy` 的 host/key/service 注册回调返回 `Duplicated`，SRP Server 回复 DNS 错误 6。该次更新被拒绝，不能记录为成功注册。冲突是在 LAN mDNS 广告阶段发现的，具体响应者尚未定位，不能仅凭此判断为本机 SRP 表存在重复项。

同一轮 supervisor 记录 `Host exited: 6`，当前锁定源码将退出码 6 定义为 `OT_EXIT_RADIO_SPINEL_NO_RESPONSE`。Host 随后重启，本机模式变回普通 unicast、端口改为 53536。该时刻旧 C6 的固定目标 53537 已失效。RCP 无响应的具体原因尚未定位，不将它直接归因于 SRP 重名。

C6 原日志 `addresses=0` 是 SRP 静态地址列表数量；自动地址模式下不能由此推断报文没有 IPv6 地址。新组件日志对自动地址模式显示 `addresses=auto`。

观察脚本现在会输出失败类别（HTTP 状态或网络异常类型），在 `--wait` 期限内重试暂时失败，并提示端口变化；401/403 不重试。使用 `--expect-port` 可以尽早发现 C6 目标已经过期：

```sh
sh test-srp.sh --expect-host gw2-srp-c6-test --expect-port 53536 --wait 180
```

下一轮先核对网关最新端口，使用一个没有在其他服务端发布过的测试身份来隔离重名，例如在 C6 原 `esphome:` 映射内调整以下两项：

```yaml
esphome:
  name: gw2-srp-c6-test
  name_add_mac_suffix: false

thread_srp_test:
  server: "EXAMPLE_IPV6_ADDRESS"
  port: 53536
```

这是本轮查询值，更新节点前仍需确认 `sh ot-cli.sh srp server state` 与 `sh ot-cli.sh srp server port`。修改身份用于测试隔离，可能使 HA 视为新设备；同名节点在多个 BR 之间迁移、旧广告撤销的兼容性仍需单独验证，不能将改名成功当作该项已修复。

## 常规单播 SRP 退让目标提高为 8

项目 `core/CMakeLists.txt` 通过共享 `ot-config` 编译定义将
`OPENTHREAD_CONFIG_NETDATA_PUBLISHER_DESIRED_NUM_UNICAST_DNS_SRP_SERVICE_ENTRIES`
从上游默认 2 改为 8。保持普通 unicast 的服务发布选择逻辑，不把 force-add 写成默认模式；不改已锁定的 vendor 源码。该改动同时适用于普通和 BBR Host 构建。

此值表示本机 Publisher 对 Thread Network Data 中单播 DNS/SRP 服务记录的目标数量，不是 SRP 客户端容量。网络记录未超目标时，本机不再因为已经存在两条记录而退让。其他 BR 的配置不会被修改；超过目标数量时仍可能按上游策略退让，Host/RCP 故障退出也不会因此被修复。

需要用户重新编译并安装 BBR 部署包，不需要重刷 RCP 或增加 YAML 字段：

```sh
cd ./5-otbr/src/otbr_host
sh build-release-bbr.sh
```

上传新生成的 `otbr-deploy-bbr.tar.gz` 至网关 `/tmp` 后，在网关执行：

```sh
cd /tmp
tar -xzf otbr-deploy-bbr.tar.gz
sh /tmp/otbr-deploy/install.sh
```

新 Host 启动后由普通 unicast 模式启用服务。WSL 查询：

```sh
sh ot-cli.sh srp server addrmode
sh test-srp.sh
```

要求 addrmode 为 unicast，`/srp` 返回 `desired_unicast_servers: 8`；Thread 附着、服务发布选择收敛后应运行并出现真实非零端口。启动日志包含 `SRP_UNICAST_PUBLICATION_TARGET=8`。

升级重启后先核对 SRP 端口。C6 测试组件显式固定了端口，不能假设升级前的 53537 仍然有效；需与新端口一致才能继续定向注册。端口保持策略与服务器退让目标是不同功能。

## 2026-11-16 LAN mDNS 实机验收通过

在新 Host 的单播发布目标数 8 生效后，用户更新 C6 目标端口并完成注册。本轮只读检查 `/srp` 确认为 running、53538，主机 `gw2-srp-c6-test.default.service.arpa.`，地址 `EXAMPLE_IPV6_ADDRESS`，未删除的 `_esphomelib._tcp` 服务端口 6053。

从 LAN 查询端 `GATEWAY_ADDRESS` 发出标准 mDNS 查询，分别完成了服务解析和报文源归属验证：

| 记录 | 实测值 |
| --- | --- |
| PTR | `_esphomelib._tcp.local.` → `gw2-srp-c6-test._esphomelib._tcp.local.` |
| SRV | `gw2-srp-c6-test.local.:6053` |
| TXT | 已收到非空记录；解析结果包含 mac、network、platform 等键，测试不打印完整 TXT 值 |
| AAAA | `EXAMPLE_IPV6_ADDRESS`，与本机 SRP 表一致 |
| 回答源 | `GATEWAY_ADDRESS:5353`，即小米网关 LAN 地址 |

`test-srp-mdns.sh` 只接受指定网关源 IP、UDP 5353 的 mDNS 回答，并核对上述四类记录；其他 BR 的回答不计为本次成功。成功输出 `SRP_LAN_MDNS_PUBLICATION_PASS`。

复测命令（WSL，同一 LAN）：

```sh
cd ./5-otbr/src/otbr_host
sh test-srp.sh
sh test-srp-mdns.sh --name gw2-srp-c6-test --address EXAMPLE_IPV6_ADDRESS
```

`--port` 默认 6053，是节点 Native API 服务端口，不是 SRP 服务器的 53538；`--address` 应取当前 SRP 表的真实节点地址。默认要求回答来自 GATEWAY_ADDRESS，可用 `--gateway` 修改。本脚本无需安装到网关或重新编译 Host，仅在 LAN 发出 DNS 查询并接收响应。

本轮证明了真实 C6 → 小米 SRP 注册 → 小米 LAN mDNS 发布链路。未在此轮验证服务撤销、租约续期/过期清理、同名节点跨 BR 迁移、Native API 连接或重启后的自动恢复；之前的同名冲突和 RCP 无响应退出不因此视为解决。
