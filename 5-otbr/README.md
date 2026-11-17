> GitHub 源码版：大型构建依赖和预构建包不随仓库提供。构建前按 [BUILD-RESOURCES.md](../BUILD-RESOURCES.md) 补齐资源并恢复链接；安装包从 Release 获取。

# 5 — Xiaomi GW2 OTBR Host

## 部件说明

当前版本 **0.2.5**，与根目录 VERSION 一致。静态 ARMv7/musl Host，适配原厂 Linux 4.9.84、MHCZ01P RCP 和 TUN，保留 BLE/openmiio 共存。包含 Web、Native API 七项网关实体、SRP/mDNS、Commissioner、拓扑/Ping/节点重启、用户态 BBR、RCP 复位恢复及可选 Thread Proxy。

Thread Proxy 始终编译，运行时由顶层 thread_proxy_api 配置启用；缺省不创建代理线程、端口或发现服务。详见 [代理说明](src/otbr_host/THREAD-PROXY.md)；网关实体与 LED 规则见 [实体说明](src/otbr_host/GATEWAY-ENTITIES.md)。共享依赖已经迁入 0-build-src，无需重复复制。

## 打包版本部署方法

已有 1～4 部件的网关直接升级本部件。上传 **deploy/mi-gw2-otbr-0.2.5.tar.gz** 到网关临时目录，逐行执行：

```sh
cd /tmp
tar -xzf mi-gw2-otbr-0.2.5.tar.gz
sh otbr-deploy/install.sh
```

不需要额外叠加安装 rcp-recovery-update；完整 0.2.5 包已包含恢复脚本。安装器保留网关 config.yaml、secrets 和已有证书，升级会重启 Host。首次安装需在网关完成配置。

完整config配置参考：
```yaml
# Gateway-owned runtime YAML. Edit this file, then sh /data/otbr/restart.sh.
device:
  name: migateway2-threadbr
  friendly_name: 小米Thread边界路由

api:   #esphome api，提供esphome集成接入
  port: 6053
  # encryption:
  #   key: !secret api_key

thread_br:
  backbone:
    interfaces: [eth0, wlan0]   #可同时配置双出口，程序自动切换
    policy: follow_default_route
    switch_delay: 3s
  id: thread_br_main  
  ha_url: http://homeassistant.local:8123 #HA连接信息，用于Web端拓补查看功能增强
  ha_token: "mytoken"     #HA连接信息，用于Web端拓补查看功能增强
  commissioner:
    enabled: true
    commissioner_id: br-migw2
  rcp_connectivity:
    id: rcp_connectivity
    name: RCP Connectivity
  output_power: 20  #射频功率，最大20
  web:
    port: 8080
    user: admin
    passwd: admin
  thread_network_config:
    channel: 20
    network_name: "my-thread"
    network_key: 
    pan_id:
    ext_pan_id: 
    pskc: 
    mesh_local_prefix: 
    omr_prefix: 
    force_dataset: true
  thread_identity:
    id: thread_identity
    name: Thread ID
    icon: mdi:identifier
    entity_category: diagnostic
  ipv4:   #文本传感器
    name: "IPv4"
    entity_category: "diagnostic"
    icon: "mdi:ip"
  uptime: #文本传感器
    name: "Uptime"
    entity_category: diagnostic
    icon: "mdi:clock-start"
  reset:  #按钮
    name: "Reset"
    entity_category: "diagnostic"
    icon: "mdi:restart"
  fw_ver: #文本传感器
    name: Gateway Fw
    entity_category: "diagnostic"
    icon: "mdi:cog-play"
  sys_led: #开关
    name: "SYS LED"


thread_proxy_api:  #要开启代理，在网关原配置顶层添加
  port: 6065
  max_connections: 2
  status_interval: 30s
  udp:
    queue_groups: 16
    queue_bytes: 131072

```
部分配置说明参阅：[Thread边界路由-HOST固件](https://esphome-openthread-enhance-pj.netlify.app/Thread%E8%BE%B9%E7%95%8C%E8%B7%AF%E7%94%B1/HOST%E5%9B%BA%E4%BB%B6.html)

其他传感器通用配置参照ESPHome文档

然后在网关执行：

```sh
sh /data/otbr/check.sh
sh /data/otbr/restart.sh
```

Native API 默认 6053；代理 TCP 默认 6065、Thread 内 UDP 固定 6064；Web 端口和账号以网关 YAML 为准。代理 Noise、节点 UDP AES-GCM 与网关 Native API 密钥各自独立且可选。先在 HA Thread Proxy 集成绑定该 BR，再使用节点客户端。

## 验证方法

网关检查：

```sh
sh /data/otbr/status.sh
grep 'OTBR_HOST_VERSION' /var/log/mi-otbr.log
grep 'THREAD_PROXY_RUNTIME_ENABLED' /var/log/mi-otbr.log
```

从项目根目录进入 Host，在有 aioesphomeapi/PyYAML 的测试环境中执行：

```sh
cd 5-otbr/src/otbr_host
sh test-thread-proxy.sh GATEWAY_ADDRESS
sh test-gateway-entities.sh GATEWAY_ADDRESS
```

## 手动构建步骤简易说明

保持项目内部相对软链接与 0-build-src 完整，准备 C/C++、CMake/make、Python 及测试依赖，见根 DEPENDENCIES.md。无需 ESPHome 运行时，Python 测试环境也不限定 ESPHome 虚拟环境。

```sh
cd 5-otbr/src
sh build.sh
```

输出 src/otbr_host/otbr-deploy-bbr.tar.gz，含 VERSION 和通用配置示例。
