# 异步 Ping 与 Active Dataset 查询

本阶段源码新增 `/ping` 与 `/node/dataset/active`。没有改动前端 URI 或响应字段，没有增加 ESPHome/ESP-IDF 依赖。

Ping 由 HTTP 工作线程提交，OpenThread 主循环启动并继续运行；Reply/Statistics 回调收集真实结果，后续主循环完成 HTTP 响应，不在主循环等待网络。只允许一个本机 Web Ping，count=1..10、size=4..512，间隔 1 秒，最后响应等待 3 秒；额外设置有界硬超时。回复列表最多保存 32 条，超出时返回 `truncated`，统计仍来自 OpenThread。超时、脱网和退出时清理本任务。未附着时拒绝开始。请勿同时通过其他客户端启动 CLI Ping，与 Web Ping 共用 OpenThread 的同一个发送器。

Web 队列支持延迟完成，保留总请求上限；等待 Ping 时其他查询仍可处理。退出释放所有排队和延迟请求；重复/迟到回调不会再次交付结果。WSL 并发测试检查普通查询不被延迟请求阻塞、退出唤醒等待线程和重复回调处理，不连接 UART。

Dataset GET 直接读取实际 Active Dataset，字段沿用原页面协议；不存在时返回 404，不把 YAML 视为已生效。只有通过 Web Basic 鉴权后能访问。接口仅提供 GET，不提供导入或修改 Dataset；测试不打印返回的网络凭据。

用户在 WSL 依次执行：

```sh
cd ./5-otbr/src/otbr_host
sh build-web.sh
sh test-web.sh
sh build-host.sh arm
sh package-noattach.sh
```

本地预期 `WEB_ASYNC_QUEUE_PASS` 与 `WEB_HTTP_TRANSPORT_PASS`。旧网关测试先 Ctrl+C 停止，再上传、解压新包，运行原 `start.sh`。新增日志标记 `ASYNC_PING_DATASET_BACKEND_READY`。原包 Noise key 与 Web 密码会被保留；API=6053、Web=18080。

网关前台保持运行，在 WSL 执行：

```sh
sh test-host-noattach.sh
sh test-host-web.sh
sh test-host-commissioner.sh
sh test-host-tools.sh
```

新增预期 `HOST_NOATTACH_TOOLS_PASS`：Dataset 查询、Ping 参数验证、未附着时拒绝合法 Ping 请求，保持 Thread disabled。它不发送 ICMP、不导入 Dataset、不启用 Thread。真正的 Echo 回复、丢包统计、边界路由、Commissioner 成功配网和拓扑扫描尚未验收。拓扑、重启控制、HA 名称映射仍待迁移。

本阶段助手只执行源码、依赖声明和脚本检查，编译及运行验证由用户执行。
