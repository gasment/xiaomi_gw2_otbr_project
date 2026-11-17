# Web 移植来源与当前范围

总览系统信息在 OpenThread 版本下方显示“OTBR在线时长”：`App:Uptime` 为当前 Host 进程的单调计时，格式 DDd:HHh:MMm，进程重启后归零，不因重新附着 Thread、切换 backbone 或刷新网页而重置。`App:UptimeSeconds` 同时提供秒级原始值。Linux 开机时长仍由 `System:Uptime` 单独提供。

页面来自用户提供的 `components/esp32/thread_br/thread_br_web/frontend` 快照；初始文件指纹保存在项目根目录 `source-manifest.json`。保留页面的原有版权与来源说明。Linux HTTP、任务队列和 OpenThread 查询适配器为本项目新增代码，不依赖 ESP-IDF 或 ESPHome 框架。上游相关许可见 `licenses/LICENSE.espressif`。

`prepare-web.sh` 获取 OTBR 已锁定的 cJSON、cpp-httplib 子模块，将页面确定性 gzip 后生成 C++ 资源。页面嵌入 Host，无需额外传输页面目录或安装 Web 服务器。依赖各自许可证也随测试包部署。

已接入：Basic 鉴权；静态页面；总览、节点、角色、地址、RLOC、Leader 信息、Border Agent ID、SRP 主机与服务查询。HTTP 工作线程通过有限队列提交查询，全部 OpenThread 调用在原主循环执行。队列满/超时/停止均返回错误，不占用 Spinel 事件循环等待 HTTP。

尚未接入：重启控制、HA 名称映射。不能将本阶段视作完整 Web 移植完成。Commissioner 状态与控制见 `COMMISSIONER.md`；异步 Ping 与 Active Dataset GET 见 `TOOLS.md`。用户已验证这些功能的 no-attach 查询和拒绝操作，真实配网和 Ping 尚未验收。新增异步拓扑见 `TOPOLOGY.md`，尚待编译与运行验收。Commissioner 在 YAML 禁用时对应页面和接口返回 404。网络参数继续由 YAML 定义。

`System:Uptime` 显示 Linux 开机时长，格式为 DDd:HHh:MMm（天数不截断）；`System:AvailableMemory` 读取 `/proc/meminfo` 的 `MemAvailable` 并显示 MiB，读取失败显示 `-`。页面使用用户提供的小米 Logo `icon.png`；关于页移除 IDF 栏目，相关资源列出本项目内核构建基线、RCP 固件和实际开源依赖。内核链接是 TUN 的候选 BSP 基线，不代表小米发布的原厂内核源码。保留源文件中的上游版权、SPDX 与许可证。其余查询来自当前 OpenThread 实例，不用 YAML 假装实时数据。`--no-attach` 下仍不导入 Dataset 或启用 Thread。

用户执行顺序：

```sh
cd ./5-otbr/src/otbr_host
sh prepare-web.sh
sh build-web.sh
sh test-web.sh
sh build-host.sh arm
sh package-noattach.sh
```

前三项只在 WSL 获取源码、编译并测试本地 HTTP。后两项生成 ARM Host 与临时测试包，不上传、不运行网关。上传新包并以之前的 no-attach 流程运行后，Native API 为 6053，测试 Web 为 18080；账号为测试 YAML 的 `test`，密码见测试包 `secrets.yaml` 中 `web_password`。测试包使用随机临时密码，不是正式部署配置。
