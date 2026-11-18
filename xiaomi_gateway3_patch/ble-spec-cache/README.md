# BLE Spec 产品规则离线补丁（首版）

这是 XiaomiGateway3/openmiio 的独立可选补丁，不依赖 RCP 或 OTBR，项目版本保持 0.2.5；暂不进入 Windows 自动部署主包。通过 openmiio 原有 Lua 扩展和一个本地 MQTT 时钟工作，不替换 openmiio 二进制、不修改 HA、不刷蓝牙或 RCP。

## 行为

- 所有原厂 `_sync.ble_spec_query_prod` 请求仍向云端发送。在线时等待云端应答，成功响应原样交给原厂，同时学习规则。
- 只把分页完整、格式校验通过的产品规格持久化；按 PDID 和 offset 隔离。只保存规格字段，不保存设备密钥或 HA Token。
- 已观察到断云时立即使用缓存；未知状态或连接静默失效时，等待约 2 秒后兜底。已进入离线应答的后续分页立即返回，避免原厂 10 秒查询缓冲超时。
- 离线合成响应的 TTL 为 120 秒，促使原厂约 60 秒后继续查询；正常云端响应的 TTL 不修改。迟到的成功云响应仍可更新缓存，但不会向原厂重复应答。
- 根据原厂真实 `local.query_status` / `local.status` 判断云状态，不使用被其他模块伪造后的状态。重连时分批主动查询已知产品，正常联网期间每约 5 分钟再检查。主动刷新只向云端取数据，不用旧缓存回答自己。
- 重连后的原厂下一次查询继续云端优先，不会因已有缓存就挡住新规则。原厂已使用离线规则时，通常会在约 60 秒内发起下一轮查询；实际还受云连接状态确认、查询成功与原厂未知产品等待期影响。
- 检测到明确拒绝、撤销（TTL=0）或不合法的完整响应时，不用缓存掩盖该响应；已识别的明确拒绝/撤销会使对应产品缓存失效。
- 完全没有学习过、或缓存不完整的型号，不会伪造规格。工具会报告冷缓存；必须恢复 WAN 学习。

## 部署

前提：XiaomiGateway3 使用的 openmiio 已安装运行，原厂 1.0.8_0013/0015，openmiio 1.2.1 二进制校验一致。已有自定义 `/data/openmiio_agent.lua` 时安装器会保留它并拒绝覆盖。

上传 `ble-spec-cache-0.2.5.tar.gz` 到网关 `/tmp`，执行：

```sh
cd /tmp
tar -xzf ble-spec-cache-0.2.5.tar.gz
sh /tmp/ble-spec-cache/install.sh
```

安装器检查包和二进制，保存原开机钩子，安装 Lua 加载器及本地时钟，保留当前启动参数，重启一次 openmiio；若原有服务管理已拉起进程则直接采用。这个过程会短暂中断 BLE/Mesh，并可能引起原厂蓝牙进程重连；不重启网关，不修改 root 密码，不接触 RCP UART。

开机钩子会先启动本地时钟，再执行原来的启动钩子。没有原钩子时安装器会创建钩子，卸载时恢复原先不存在的状态。补丁不要求安装任何 RCP/OTBR 组件；若与其他组件共用启动钩子，应先卸载本补丁，再更改原钩子。

## 查看与验收

```sh
sh /data/ble-spec-cache/status.sh
```

预期有 `LUA_LOADER_INSTALLED`、`CLOCK_RUNNING`，JSON 内的 `runtime_pid` 对应当前 openmiio。

默认使用系统 awk 将状态 JSON 缩进展开，产品列表、统计和最近响应分行显示；无需 jq。机器读取可使用 `sh /data/ble-spec-cache/status.sh --json`，只输出原始 JSON。系统没有 awk 时默认回退原始格式。

重要字段：

- `revision`：当前为 `4`。保留此前的 ID 映射、线协议 ID、事件字段及刷新队列修复，并提供按产品型号主动学习入口。
- `cloud_state`：查询状态；`unverified` 尚未成功取规则，`degraded` 表示查询失败或超时，`online` 表示成功取得规则，`offline` 表示原厂报告离线。这不是独立的 WAN 连通性探测。
- `reported_cloud_state`：原厂报告的云状态，断 WAN 后也可能仍显示 `online`，不能作为真实连通的证据。
- `complete_products`：已经完整学习并持久化的产品数。初次安装为 0 是冷缓存，不代表该型号可离线。
- `products`：PDID、规则总数、分页数、云端源 TTL。
- `statistics.cloud_pages` / `learned_products`：收到云端成功分页、完成规则集次数。
- `statistics.cache_replies`：已经实际发送的离线缓存回复数。
- `statistics.cache_misses`：当前产品/分页无可用缓存，不会使用其他型号数据代替。
- `statistics.refresh_ok` / `refresh_fail`：主动云端刷新结果。
- `statistics.errors`：本地缓存写入/回调等错误；应为 0。
- `statistics.ticks`、`observed_uptime`：确认定时回调及状态文件持续更新。
- `statistics.responses` / `invalid_responses` / `cloud_errors`：区分响应到达、格式被拒和云端报错；`last_response` 仅记录产品型号、分页、结果类别和结构信息，不记录完整响应或设备凭据。

首次冷启动时，先恢复 WAN 并触发目标设备。原厂可能仍有约 300 秒未知产品等待期；让它到期并重新查询。确认目标 PDID 出现在 `products`，并确认 HA 有新状态后，再阻断 WAN，测试超过该型号原始 TTL、以及离线重启。

触发设备并不一定产生产品查询：原厂已有规则时仍可正常上报，补丁却可能尚无机会学习。可以直接按产品 PDID 主动向云端查询，无需重启蓝牙进程：

```sh
/data/ble-spec-cache/ble-cache-clock --learn-product 6281
```

6281 是产品型号示例，换成待学习型号。`LEARN_REQUEST_SENT` 仅代表本地请求已发送，必须再查看 `manual_learn_requests`、`responses`、`last_response`、`products` 确认成功。该查询只学习云端规格，不伪造在线状态、不把缓存当作刷新结果，也不会强制重载原厂已生效的规则。

重新联网后确认 `cloud_pages` 或 `refresh_ok` 增长。改变云端规格时，应在后续成功查询中替换离线数据；测试用 Lua 用例覆盖了新旧规则内容不同的重连场景。日志和状态不输出完整产品响应或凭据。

持久化规则保存在 `/data/ble-spec-cache/products.json`；状态在 `/tmp/gw2-ble-spec-cache-status.json`，时钟日志在 `/var/log/ble-spec-cache-clock.log`。

## 撤销

```sh
sh /data/ble-spec-cache/uninstall.sh
```

恢复原开机钩子、移除本补丁的 Lua 加载器、停止时钟并按原启动参数重启 openmiio。保留产品缓存和安装目录以便检查/重装。引导或加载器被另行修改时会拒绝覆盖。

## 构建和测试

在完整项目中进入本源码目录：

```sh
sh build.sh
```

默认使用项目 `0-build-src` 的 ARM musl 工具链；也可设置 `MG_CROSS` 为交叉工具链前缀。只编译本地时钟，Lua 由现有 openmiio 加载。输出到本目录 `deploy`。`package.py --output` 可选择其他输出路径。

测试用 Go 1.20+，不参与网关运行，也不需要 ESPHome 或 Python 虚拟环境：

```sh
sh tests/run.sh
```

测试依赖固定为与 openmiio 1.2.1 一致的 gopher-lua、gopher-json，见 `tests/go.mod` / `go.sum`。测试直接加载生产 Lua 源码，覆盖冷缓存、完整/不完整分页、无响应超时、持久化、重连刷新、明确拒绝及撤销等场景。

本地测试通过不等于已完成真实网关离线验收。尤其要验证设备授权 TTL、不同产品格式和恢复 WAN 后的 HA 新状态。

参考：[openmiio Lua 扩展](https://github.com/AlexxIT/openmiio_agent/blob/master/internal/lua/lua.go)、[现有离线缓存](https://github.com/AlexxIT/openmiio_agent/blob/master/internal/cache/cache.go)。本补丁源码按本目录 MIT 许可证提供；第三方测试依赖遵循各自许可证。
