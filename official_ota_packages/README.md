# 手动 OTA

- 适用于 Windows PowerShell
用于有 root 空密码 Telnet 权限的 `lumi.gateway.mcn001` 网关。输入原厂 MIOT OTA`.bin` 包，不能使用拆出的 kernel、rootfs 或 Zigbee/RCP GBL 固件。<br>
- 官方OTA在执行逻辑上没有限制降级或升级顺序，项目进行的测试有：1.0.3->1.0.8_0015升级成功，1.0.8_0015->1.0.8_0013降级成功，其他跨版本降级未测试，请谨慎操作，本项目对设备损坏概不负责
- 本项目需求版本为1.0.8_0015，其他版本会因为内核校验不通过而拒绝启动



## 上传并开始更新

把脚本和选定 OTA 包放在同一个目录，在该目录打开 PowerShell，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Push-Ota.ps1 -Gateway 192.168.x.x -Package .\lumi.gateway.mcn001_1.0.8_0015_MIOT.bin
```

将IP修改为对应的你的网关IP，换版本时，修改 `-Package`后面的文件名。

流程：登录 → 检查工具与空间 → Telnet 分块上传 → 核对大小和 MD5  → 后台运行 `fw_manager.sh -u -s`。

如果网关上已有同 MD5 的包，直接复用，不重复上传。优先使用 `/data/firmware/firmware_ota.bin`，上传中间文件为 `/data/firmware/manual_ota.uploading`。

当 `/data` 无法同时容纳上传包和解包余量时，自动改用 `/tmp/mi-gw2-manual-ota/firmware_ota.bin` 暂存，中间文件也放在该目录。仍要求 `/data` 留出至少一份包大小的安装余量，并检查 `/tmp` 空间和 `MemAvailable`，为上传包及解包镜像预留容量。不会绕过原厂空间检查，也不会删除已有组件。

`/tmp` 暂存包会随重启消失，但本流程是在安装完成后才由原厂脚本重启，不需要跨重启续传。

显示 `OTA_STARTED` 仅代表安装流程已触发。安装成功会自动重启，期间保持供电。脚本不会在连接中断后自动重试安装。

## 只上传，不安装

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Push-Ota.ps1 -Gateway 192.168.x.x -Package .\lumi.gateway.mcn001_1.0.8_0015_MIOT.bin -UploadOnly
```

此模式不启动安装，也不会要求安装确认。

正常更新时，若检测到已安装 OTBR/RCP，脚本会先显示警告，再要求输入大写 `YES` 二次确认。输入其他内容或直接回车即取消，不上传包、不触发安装。确认后继续执行原有上传、校验和安装流程。

原厂 OTA 可能改变内核、使现有 TUN 模块和启动隔离失效，也可能更新无线固件；本工具不负责这些组件的迁移或修复。

## 查看结果

安装期间通过 Telnet 查看：

```sh
tail -n 60 /tmp/manual-ota.log
agetprop sys.dfu_progress
```

成功重启后 `/tmp` 日志会消失。重连后检查实际版本：

```sh
agetprop ro.sys.mi_fw_ver
agetprop ro.sys.mi_build_num
cat /proc/version
```

若上传中断或校验失败，脚本不会安装；确认已没有上传任务后，可删除中间文件再重试：

```sh
rm -f /data/firmware/manual_ota.uploading
```

若输出的暂存路径位于 `/tmp`，对应的中间文件为：

```sh
rm -f /tmp/mi-gw2-manual-ota/manual_ota.uploading
```

若两个暂存位置都不满足容量检查，脚本停止，不自动删除旧包、用户数据或组件。

