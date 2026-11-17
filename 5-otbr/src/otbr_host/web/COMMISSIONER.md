# Commissioner 主机移植阶段

沿用用户 ESP32 项目 `commissioner.cpp` 的状态机与页面 JSON：空闲、申请角色、等待 Joiner、认证、完成、取消、超时和失败。去掉 FreeRTOS/ESPHome/ESP-IDF 依赖，回调事件改为有限队列，HTTP、回调处理与 OpenThread 操作都在 Host 主循环执行。只在明确收到并接受 `action:start` 后申请 Commissioner 角色，不随 Host 启动打开配网窗口。

保留候选节点列表、120 秒候选有效期、32 个候选上限、PSKd/EUI64/窗口验证、Dataset 与 YAML 一致性检查；配网结束显示凭据交换完成，不声称设备已经附着。没有 EUI64 时授权范围是持有对应 PSKd 的任意 Joiner；选择候选只保留原项目的界面关联语义，不能将扫描随机地址当作工厂 EUI64。

保留用户项目的实验性发现 TLV 241（OUI FFFFFF、ESJ1），用于识别设备 ID 与名称；普通 Joiner 仍走公开发现回调。TLV/UTF-8 解析器从用户项目移植。构建时只替换构建目录中的 `mle_ftd.cpp` 副本，不改已锁定的上游 checkout；源文件锚点不匹配会中止构建。上游源码版权声明随副本保留。

测试包将 `commissioner.enabled` 设为 true，以便访问原页面；**enabled 只启用页面和后端，并不启动 Thread 或 Commissioner 配网窗口**。测试仍使用 `--no-attach`，虚构 Dataset 不会应用到无线网络。

用户在 WSL 执行：

```sh
cd ./5-otbr/src/otbr_host
sh build-host.sh arm
sh package-noattach.sh
```

旧网关测试先 Ctrl+C 停止，再上传、解压新包并运行原 `start.sh`。预期日志新增 `COMMISSIONER_BACKEND_READY`，API 仍为 6053，Web 仍为 18080，账号密码沿用测试包 `secrets.yaml`。

保持网关前台测试运行，在另一个 WSL 终端执行：

```sh
sh test-host-noattach.sh
sh test-host-web.sh
sh test-host-commissioner.sh
```

最后一项只检查状态、非法请求和未附着时拒绝开始配网。预期 `HOST_NOATTACH_COMMISSIONER_PASS`；不会发送能被接受的开始或取消请求，不导入 Dataset、不启用 Thread。当前阶段仍不能验证实际候选发现、申请角色、Joiner 认证和成功入网；这些需要后续附着后的验收。

拓扑、Ping、Active Dataset JSON、HA 名称映射尚未迁移。没有改动 BLE、原启动链或网关生产配置。助手未运行编译或网关操作。
