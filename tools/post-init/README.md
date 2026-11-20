# post-init 工具

`post-initctl.sh` 只维护 API 1 模块清单；组件失败不会跳过最后的原厂启动锚点。

`factory-reset.sh` 用于可重复执行的恢复：

- `--prepare-flash`：停止 OTBR/BLE 运行时并恢复上一次暂停的原厂服务，为原生 UART 刷写释放资源；
- `--restore-hook`：移除项目模块并恢复原厂 `post_init.sh`，保留程序目录；
- `--remove-all`：恢复启动入口、停止项目进程、解除 TUN/RCP 绑定挂载、移除 OpenSSH 服务账户并删除项目目录；
- `--verify`：只读复查目录、进程、内核模块和启动入口；
- `--status`：输出详细状态，最后执行同样的只读复查。

在 POSIX 系统运行 `sh tools/post-init/test-post-initctl.sh` 可测试模块清单；该测试使用临时路径，不会访问 `/data` 或执行原厂启动器。
