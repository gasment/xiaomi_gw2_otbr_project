# Independent Native API: protocol-only verification stage

RCP 初始化已由用户在 Linux 4.9 网关实测通过（CORE_RADIO_INIT_PASS）。本阶段新增独立 Native API 服务端源码，不引入 ESPHome 框架。密码协议使用 noise-c 0.1.31 的固定提交 62c2fdca7a874ea898761147bb062ca1cde9f36d，MIT 许可；参考密码后端无需额外 libsodium/OpenSSL，随机数来自 Linux /dev/urandom。

## 当前实现边界

- Noise_NNpsk0_25519_ChaChaPoly_SHA256、Native API 加密帧和 Protobuf 消息子集。
- Hello、设备信息、三类诊断实体、状态订阅、心跳、重连、最多四个客户端。
- 从运行时 YAML 读取名称、实体 ID、显示名、图标、分类、API 端口和加密 key。
- entity key 由配置 id 稳定计算，启动时检查冲突。
- 对外声明 API 1.14、独立程序自身版本，不声称运行 ESPHome，不发布蓝牙代理、OTA、动态密钥配置等未实现能力。
- 独立类通过 SnapshotProvider 接收真实后端缓存，避免 API 线程直接访问 otInstance。

**当前 otbr-native-api-check 只有协议服务：不会打开 UART、创建 TUN、启动 Thread 或 Web。所有实体状态为 missing_state。** 尚未接入已验证的 OTBR 核心；不能把 HA 中发现实体视作边界路由已工作。

用户已完成 native 编译和两项配置/骨干测试。首次互通暴露 Noise prologue 比官方格式多一个 C 字符串 NUL，源码已修正；官方 Python 后端已复现旧格式失败并验证修正后的完整握手与双向加密。修正后的 C++ 端到端互通仍待用户重新构建执行。不要直接放入自启动。

## 用户执行

已有 WSL 工程文件已同步。Noise 源码已下载并固定，脚本会复核。

```sh
cd ./5-otbr/src/otbr_host
sh build-api.sh native
sh test-api.sh
```

build-api.sh 构建独立服务与检查工具，并补跑两项受配置变更影响的测试。test-api.sh 使用现有 python3（或设置测试脚本的 Python 环境变量） 中的官方 aioesphomeapi 与 PyYAML，创建临时配置、随机 Noise key 和四个覆盖三种类型的实体，启动本地 C++ 服务并进行真实加密互通。

检查包括：超长握手拒绝、错误 key 拒绝、正确握手、设备信息、实体枚举、缺失状态订阅、超过 30 秒的服务器心跳及重连后的实体 key 稳定性。不会读取真实 secrets.yaml，不改 HA，不访问网关。正常耗时约 35 秒，成功标志 NATIVE_API_INTEROP_PASS。

如果本地 Python 路径不同，可通过 OTBR_API_TEST_PYTHON 指定已有环境。此路径只用于开发机测试，网关运行程序不需要 Python。

native 互通通过后才构建 ARM：

```sh
sh build-api.sh arm
```

输出 build/api-arm/otbr-native-api-check。随后另行准备网关端协议检查，不直接启动完整 BR。

## 兼容性与身份

api.encryption 可省略，此时使用 ESPHome Native API 的明文帧；配置后仅接受 Noise 帧，不允许明文降级。配置的 key 必须是 Base64 编码的非全零 32 字节，不自动生成。test-api.sh 使用官方 aioesphomeapi 分别验证加密与明文连接、实体订阅、保活和重连；加密模式额外验证错误 key 被拒绝。测试配置只写入临时目录，不保留网关凭据。

device.mac_address 可选。未配置时按固定顺序读取 eth0/wlan0 等接口地址，与当前骨干选择分离。对于固定接口名的小米网关可避免插拔网线造成身份变化；若接口命名/硬件会变化，应明确填写网关真实、稳定的 MAC，避免 HA 生成重复设备。

网络只绑定 TCP API 端口。本阶段没有 mDNS 广播，原版 HA 可手动输入 IP/6053 测试，后续再统一接入服务发现。Web 端口虽然已解析，但协议检查工具不会监听它，因此设备信息也不宣称 Web 已启动。

Native API 的日志订阅请求可接收但本阶段不输出远程日志；没有实现任意执行命令、重启网关或更新无线固件的接口。

## 现阶段验证状态

已完成源文件、CMake 接入、脚本语法及依赖校验；用户已 native 构建成功。首次 C++ 互通失败已定位到 prologue 的末尾 NUL，修正后的 C++ 互通待执行。助手仅运行官方 Python Noise 后端的针对性复现，没有执行编译或启动 C++ 服务。

回归测试也已调整：必须先用正确 PSK 完成实体与状态订阅，再验证错误 PSK 被客户端明确报告为 InvalidEncryptionKeyAPIError，避免把任意握手失败当作负向验证成功。

后续：Native API 互通通过 → 将真实 OTBR 缓存接入 SnapshotProvider → 接入原 Web REST/Commissioner/SRP/HA 映射 → 动态骨干重绑定与无线入网实测。
