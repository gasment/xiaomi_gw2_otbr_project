# 网关系统 Native API 实体

从项目根目录执行文中的本机构建路径命令。配置仍由用户在网关编辑，不复制到源码树。五个实体均为可选项，未配置不向 HA 发布；旧有实体的 ID/键保持不变。

| YAML 名称 | HA 类型 | 数据或行为 |
| --- | --- | --- |
| ipv4 | text_sensor | 当前 OTBR backbone 的真实 IPv4；切换 eth0/wlan0 后更新，无可用地址时报告 missing state |
| uptime | text_sensor | Linux 整机开机时长，例 `3d:18h:02m`；不是 Host 进程在线时长 |
| reset | button | 重启整个网关，Thread、BLE、SSH 会短暂中断；不恢复出厂、不清理 Dataset |
| fw_ver | text_sensor | 原厂 build.prop 的系统固件版本及构建号，例 `1.0.8_0013`；不是 OTBR 版本 |
| sys_led | switch | 原厂系统指示灯使能；on=允许原厂状态灯工作，off=关闭，不强制常亮或指定颜色 |

## 网关 YAML

在已有 `thread_br` 下添加以下字段，保持已有网络、凭据与其他配置：

```yaml
  ipv4:
    name: IPv4
  uptime:
    name: Gateway Uptime
    icon: mdi:timer-outline
  reset:
    name: Restart Gateway
    icon: mdi:restart
  fw_ver:
    name: Gateway Firmware
  sys_led:
    name: System LED
    icon: mdi:led-on
```

默认 ID 就是字段名。reset/sys_led 默认属于 config 分类，其余默认 diagnostic；均支持显式 id、name、icon、entity_category。

## 系统 LED 介入方式

实机没有标准 LED sysfs 类接口。原厂 mha_basis 管理 GPIO/PWM 及状态灯事件；其二进制包含 system_lampoff/system_lampgrade。使用 GPIO 强制写值容易与原厂事件处理竞争，所以 Host 通过现有本机 openmiio/MQTT 转发原厂 MIoT get_properties/set_properties，属性为 siid=6、piid=1，整数 0=允许亮灯、1=关闭。

依据：AlexxIT/XiaomiGateway3 的同型号设备转换定义。原厂属性的 get、set、再次 get 已实机验证，测试后已恢复原值。它验证了属性读写链路，不等于新 Host 的 HA 开关已实机验收。

Host 仅连接本机 MQTT，独立连接 ID，不替换 HA 连接，不启动或改写 openmiio。设备标识只在内存使用，不打印或写入配置。LED 读写在独立工作线程，避免阻塞 OpenThread；约每 10 秒重新读取原厂值。收到有效开关命令后立即乐观发布目标值；原厂 get 返回后同步实际状态。LED 单独读取线程安全缓存，状态变化约 250ms 内推送给其他订阅客户端，不等待 OTBR 指标采样周期。命令使用递增版本，早于最新命令的查询/写入反馈会被丢弃，避免快速连续操作时旧反馈覆盖新目标。当前命令失败或状态超过 30 秒仍无有效更新时 missing state，不无限保留乐观值。乐观值仅用于开关交互，不改变 Web/RCP 等真实测量值。米家或 XiaomiGateway3 改变灯光属性后也会同步。原厂程序缺失或型号不支持时开关无有效状态。

源码参考：

- [上游设备转换](https://github.com/AlexxIT/XiaomiGateway3/blob/65f7249901803b40ef0c58e717754f5220c9f273/custom_components/xiaomi_gateway3/core/devices.py)
- [openmiio v1.2.1 命令转发](https://github.com/AlexxIT/openmiio_agent/blob/v1.2.1/internal/miio/miio.go)

## 构建与升级

使用安装了 aioesphomeapi 与 PyYAML 的 Python 环境；先激活该环境，或设置 OTBR_API_TEST_PYTHON。保持工具链及 0-build-src 目录完整。

```sh
cd 5-otbr/src
sh build.sh
```

成功后新包在 `5-otbr/src/otbr_host/otbr-deploy-bbr.tar.gz`（路径相对于项目根目录）。原 `5-otbr/deploy` 的已验收冻结二进制不被构建覆盖，本次源码变更尚未编译或替换冻结程序。

将新包通过 SFTP 上传到网关临时目录，然后在网关执行：

```sh
cd /tmp
tar -xzf otbr-deploy-bbr.tar.gz
sh otbr-deploy/install.sh
```

编辑网关已有配置，添加上述字段，然后执行网关命令：

```sh
sh /data/otbr/check.sh
sh /data/otbr/restart.sh
```

HA 重新连接后应共显示七个已配置实体。不会自动读取、改写用户的网关 YAML。

## 验证边界

升级并添加配置后，从项目根目录执行默认只读验收，将 GATEWAY_ADDRESS 替换为网关地址，Python 环境需含 aioesphomeapi 与 PyYAML：

```sh
cd 5-otbr/src/otbr_host
sh test-gateway-entities.sh GATEWAY_ADDRESS
```

脚本仅在内存读取网关配置和凭据，比较真实系统版本、IPv4 与 Linux 开机时间，核对按钮/开关类型和有效状态，不发送开关或重启命令。

构建入口包含原有配置回归、系统版本/时长逻辑回归及官方 aioesphomeapi 互通检查。协议检查服务拒绝所有系统动作，只记录经过准确实体键和类型匹配的命令；不重启、不访问 LED/MQTT。按钮没有状态消息；开关使用自己的 missing_state 字段。

`--no-attach` 模式拒绝整机重启与 LED 写入。正式运行模式只有收到已配置 reset 按钮的准确键才安排整机 reboot；不会在发现实体或订阅状态时执行。当前 Native API 允许明文，这是受信任局域网中的管理操作。

升级后先核对 IPv4、uptime、fw_ver，再测试 sys_led 的开/关和米家侧状态同步，最后在允许中断网络服务时手动按 reset。整机 reboot 未在此次开发中触发。新 C++ 编译、Native API 互通和新 Host 实机验收仍由用户执行。

## HA 设备信息

制造商发布为 Xiaomi，型号保留 mi_gateway2_otbr。Native API 的版本字段取项目根目录 VERSION，不发布 project_name/project_version 或编译时间，避免 HA 用项目作者覆盖制造商并拼接 ESPHome 固件后缀。mDNS 同步移除旧项目字段。实体键、MAC 和设备名称不变。升级后等待集成重连；若页面仍显示旧元数据，重新加载该 ESPHome 集成条目，无需删除实体。

使用前提：由 HA sys_led 接管时，请关闭米家“指示灯勿扰”及其时间段规则。该规则会影响实际灯光；属性反相映射保持 0=允许、1=关闭，米家侧变更也会同步回 HA。
