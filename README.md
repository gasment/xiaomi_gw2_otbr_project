# Xiaomi Multimode Gateway 2 OpenThread Border Router

# 小米多模网关 2 OTBR 项目 
* 当前版本 **0.3.0**（以根目录 [VERSION](VERSION) 为准）
* 关联项目：[ESPHome OpenThread & Thread BR Enhance Project](https://github.com/gasment/esphome_openthread_enhance_project)

## 项目介绍

本项目将小米多模网关 2 改造为本地运行的 OpenThread Border Router：保留原厂 Linux 系统，将 MHCZ01P 无线模块刷为 OpenThread RCP，通过 UART 连接本机 OTBR Host，在 Thread 网络与家庭局域网之间转发 IPv6 通信。

同时提供 Web 管理、Home Assistant 接入和可选的 Thread Proxy API，并通过网关侧启动管理保留 Xiaomi Gateway 3 集成使用的蓝牙／BLE Mesh 功能。

主要功能：

- **本地边界路由**：静态 ARMv7 Linux Host、TUN、运行时 YAML 配置，以及 Ethernet / Wi-Fi backbone 自动选择与切换。
- **Web 管理**：查看网络状态、拓扑、SRP 注册、真实 RCP 发射功率，提供 Ping、Commissioner 和兼容节点的远程重启功能。
- **Home Assistant 接入**：兼容 ESPHome Native API 与 mDNS 自动发现，提供 RCP 连接、Thread ID、IPv4、运行时间、原厂固件版本、网关重启和系统 LED 等实体。
- **Thread 服务发现**：SRP Server 与局域网 mDNS 服务发布。
- **多播支持**：适配原厂内核的实验性用户态 BBR 后端，已完成基础 MLR 注册和双向多播实测。
- **Thread Proxy API**：可选的 Thread 节点到 HA 转发代理，兼容项目配套的 ESP32 / nRF52 客户端；不配置时不启用，修改配置后重启服务即可应用。
- **运行维护**：服务自启动、进程监督、RCP 复位恢复及 BLE / RCP 串口隔离。

项目按五个部件组织，各部件保留构建源码、部署模板和说明文档，预构建发布件从 Release 或 deploy 目录获取。GitHub 源码不包含大型工具链、SDK 。


## 使用前提
- **网关型号**：必须为`lumi.gateway.mcn001`，SSD222D 主处理器、MHCZ01P 无线模块和原厂 Linux 4.9.84内核
- **网关接入**：必须提供Telnet访问权限，使用Xiaomi Gateway3集成接入HA即可开启（固件版本低于1.0.7），并保存好设备KEY，参阅 [Xiaomi Gateway3](https://github.com/AlexxIT/XiaomiGateway3)
- **网关固件**：必须不低于 `1.0.8_0015`。该版本及以上允许安装；高于该版本的长期兼容性尚未逐版验收。低于此版本时，先接入 XiaomiGateway3 并保存设备 KEY，再进行 OTA 更新。
## 使用说明

- **原厂访问前提**：部署前需自行取得 root Telnet / FTP 访问权限，本项目不提供解锁流程。SSH 是部署链的第一个部件。
- **Zigbee 与 Thread 的取舍**：无线模块改为单协议 RCP 后，原厂 Zigbee 功能会停止。附带恢复原厂 Zigbee 应用固件的路径，但不保证继承原 Zigbee 网络配置；不提供现有无线 Flash 的完整免拆备份。
- **蓝牙共存范围**：通过网关侧 openmiio 管理保留 Xiaomi Gateway 3 的 BLE / Mesh 通道，不需要修改 HA 集成。实际蓝牙上报仍需以 HA 收到设备新状态为准。
- **可信局域网使用**：为兼容现有原厂访问及 Xiaomi Gateway 3 工作方式，默认保留 root 空密码。Telnet、SSH、MQTT 和管理接口应仅供可信局域网访问，不应直接暴露到公网。Native API 的 Noise 加密可选，Web 支持 Basic 认证。如需为root设置密码，需要为Xiaomi Gateway 3集成打补丁，参阅[XiaomiGateway3 密码补丁](xiaomi_gateway3_patch/README.md)
- **配置归网关所有**：用户直接编辑网关 `/data/otbr/config.yaml` 与需要的 `secrets.yaml`，检查通过后重启服务；项目和通用部署包不携带用户凭据、Thread Dataset 或 SSH 主机私钥。
- **兼容范围**：Native API 是用于 HA 接入的独立实现，不包含完整 ESPHome 框架。Thread Proxy 需配套 HA 集成和节点客户端（详情见[ESPHome OpenThread & Thread BR Enhance Project - Thread 代理](https://esphome-openthread-enhance-pj.netlify.app/Thread%E4%BB%A3%E7%90%86/Thread%E4%BB%A3%E7%90%86.html)）；节点远程重启也需要节点支持相应协议。
- **验证范围**：已实测基本 Thread 接入、指定本 BR 的 LAN 路由、SRP / mDNS、BBR 基础双向多播及代理上报；
- **恢复出厂与OTA**： 执行官方固件的恢复出厂，会清空data目录，本项目也会被清除；安装本项目后，data分区容量不足以支持官方双区OTA，因此米家更新会报错，本项目本身也不支持OTA

## 自动部署
自动部署仅适用于首次安装，如果网关存在已安装的组件，请不要使用自动部署，应参照手动部署独立更新。

自动部署使用 Windows 单文件程序，不需要安装 Python，也不需要解压组件 ZIP。

0. 确保网关固件**不低于 1.0.8_0015**；TUN 通过 `/etc/os-release` 的 `LUMI_VERSION` 判断。
1. 从 Release 下载 `MiGateway2AutoDeploy-0.3.0.exe` 及对应 `.sha256` 文件。
2. 先暂时停用 HA Xiaomi Gateway 3 中对应的网关条目，避免原 Zigbee 串口被重新占用。
3. 运行 EXE，输入网关 IP、端口和 root 密码，点击“连接并刷新”，选择组件后执行一键部署。
4. 使用界面中的 YAML 上传功能创建或更新 `/data/otbr/config.yaml`，详细字段参照项目文档内的 `5-otbr/README.md`。
5. 修改完成后在网关执行如下命令来启动OTBR

    ```sh
    sh /data/otbr/check.sh
    sh /data/otbr/restart.sh
    ```
6. 进入网关的Web后台查看Thread状态，进入HA检查是否自动发现设备



## 手动部署

首次部署请按下表顺序进行。每一步先完成该部件文档中的验证，再进入下一步；刷写 RCP 前按说明暂时停用可能占用 Zigbee 串口的 HA 网关条目。

| 顺序 | 部件 | 部署内容 | 部署说明 |
| --- | --- | --- | --- |
| 1 | OpenSSH | SSH 2223、internal-sftp、启动管理 | [OpenSSH 部署](1-openssh/README.md) |
| 2 | TUN 驱动 | 匹配内核的 `tun.ko`、设备节点与自启动 | [TUN 部署](2-tun-driver/README.md) |
| 3 | RCP 与 Zigbee 隔离 | 网关本机刷写、固件恢复路径、原厂 Zigbee 启动隔离 | [RCP 部署](3-rcp-mode/README.md) |
| 4 | BLE / openmiio 共存 | 保留蓝牙上报，释放 RCP UART | [共存部件部署](4-rcp-openmiio/README.md) |
| 5 | OTBR Host | 本地 BR、Web、Native API、可选 Thread Proxy | [OTBR 部署与配置](5-otbr/README.md) |

** 本项目提供的openssh预构建版本，编译时使用最新的`10.6p2`，官方已修复"sshole" 密码认证绕过漏洞（CVE-2026-123158）

各部件的发布包从对应目录的`deploy`获取，已改造的网关应按目标部件说明更新，不要重复运行底层首次安装器覆盖现有启动链。

部署前可从项目根目录进行离线校验：

```sh
python3 verify-release.py
```

安装完成后，可经 SSH 只读核对发布文件与网关的一致性。将 `GATEWAY_ADDRESS` 替换为实际网关 IP：

```sh
python3 verify-installed.py --gateway GATEWAY_ADDRESS
```

网关上检查 OTBR 运行状态：

```sh
sh /data/otbr/status.sh
```

修改网关配置后，先检查再重启：

```sh
sh /data/otbr/check.sh
sh /data/otbr/restart.sh
```



## 自行构建
本项目提供已编译好的静态二进制程序，如你需要重新编译，可参阅[构建准备](BUILD-PREPARATION.md)和各部件 README 的“手动构建步骤简易说明”


## 依赖许可

本项目使用多个独立上游项目。下表列出主要依赖及随源码保留的许可入口；依赖内部的其他第三方文件仍以各自版权和许可证声明为准。

| 依赖 | 用途 | 许可／来源说明 |
| --- | --- | --- |
| OpenThread Border Router | Linux BR 基础 | [BSD-3-Clause](dependencies/licenses/OTBR-LICENSE) |
| OpenThread | Thread 协议栈及 POSIX 平台 | [BSD-3-Clause](dependencies/licenses/OpenThread-LICENSE) |
| Linux / SigmaStar 候选 BSP | TUN 驱动构建基线 | [GPL-2.0](dependencies/licenses/Linux-LICENSE)；该 BSP 不代表小米公开的原厂完整内核源码 |
| OpenSSH Portable | SSH 与 internal-sftp | [BSD 等宽松许可，详见 LICENCE](1-openssh/src/openssh-portable/LICENCE) |
| OpenSSL | TLS 与密码库 | [Apache-2.0](5-otbr/src/otbr_host/licenses/LICENSE.openssl) |
| Mbed TLS | 上游协议栈密码依赖 | [Apache-2.0 OR GPL-2.0-or-later](dependencies/licenses/MbedTLS-LICENSE) |
| Noise-C | Native API / Thread Proxy 的可选 Noise 加密 | [MIT](dependencies/licenses/Noise-C-LICENSE) |
| yaml-cpp | 运行时 YAML 解析 | [MIT](dependencies/licenses/yaml-cpp-LICENSE) |
| cJSON | JSON 处理 | [MIT](dependencies/licenses/cJSON-LICENSE) |
| cpp-httplib | HTTP 服务 | [MIT](dependencies/licenses/cpp-httplib-LICENSE) |
| Web 前端移植部分 | 管理页面 | [来源说明](5-otbr/src/otbr_host/web/SOURCE.md)与随附 [Apache-2.0 文本](5-otbr/src/otbr_host/licenses/LICENSE.espressif) |
| GCC、musl 与交叉工具链 | 编译及静态运行库 | 保留各工具链的原始许可；发布包附带相关许可证与 GCC Runtime Library Exception 文本 |
| openmiio_agent / XiaomiGateway3 | 原厂消息通道与 HA 蓝牙共存 | 独立外部依赖，参见 [依赖说明](4-rcp-openmiio/README.md)，许可按上游声明 |
| Silicon Labs RCP / Zigbee 固件及 SDK | 无线协处理器应用 | 参见 [固件来源与构建范围](3-rcp-mode/README.md)，许可按固件、SDK 及所含依赖的上游条款分别处理 |

精确依赖修订与关键文件指纹见 [共享依赖清单](dependencies/lock.json)和 [Host 依赖锁定文件](5-otbr/src/otbr_host/deps.lock.json)。部署包内的 `licenses` 目录保留对应发布件的第三方许可文本。

项目自有代码沿用本仓库已有的 [MIT License](LICENSE)。第三方源码、固件和工具链仍分别遵循各自许可证，不因本项目的 MIT 授权而改变。


## 免责声明
- 本项目全部代码由AI生成
- 因使用本项目程序造成的设备损坏，本项目概不负责
- 本项目仅供个人学习与研究，其他不合规用途与本项目无关
- 若有侵权立即删除
