# 0.2.0

- 主版本统一从项目根目录 VERSION 读取；Web、Native API 和新构建部署包同步报告 0.2.0。
- 内置可选 Thread Proxy API：顶层运行时 YAML，缺省不启用，变更后仅需重启 Host。
- 独立 TCP 6065 明文/Noise、专用 mDNS、管理状态与单一上行消费者。
- Thread 内 UDP 6064 TSD2、可选 AES-GCM、分片重组、队列 ACK、去重和 schema 请求。
- 保留原始节点记录、HA delivery 确认、同 token 重传，兼容现有 ESP32/nRF52 客户端与 HA Thread Proxy 协议 v1。
- 增加协议与官方 aioesphomeapi 互通测试入口；实机数据链路、SED ACK 时延及多 BR 故障切换仍需用户验收。
- 系统 LED 开关使用乐观更新与真实反馈同步。使用 HA 接管时关闭米家的“指示灯勿扰”时段规则。

0.2.0 已由用户构建和部署，节点到 Linux BR 再到 HA 的基本代理通信通过用户验收。当前发布包已同步 deploy 并核对网关；旧 0.1.0 包已删除。本次晋级未重新编译或修改网关。
