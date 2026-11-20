# 小米多模网关 2：OpenSSH 部署

## post_init 模块

本组件只增删 `# BEGIN/END MI-GW2 POST-INIT MODULE: openssh` 块，不再替换整份 `/data/scripts/post_init.sh`。启动失败只写日志，最终原厂锚点仍会执行。


适用于已取得 root Telnet/FTP 权限、运行原厂系统的小米多模网关 2。资源来自本项目已验证的 ARMv7 静态 OpenSSH 10.6p2：SSH、MobaXterm SFTP 和重启自启动均已验证。本文仅包含部署，不包含编译。

## 部署后的连接方式

| 项目 | 设置 |
|---|---|
| 用户 | root |
| 密码 | 空，直接回车 |
| SSH 端口 | 2223 |
| MobaXterm 文件浏览协议 | SFTP protocol |
| 程序及配置目录 | /data/openssh |
| 开机启动入口 | /data/scripts/post_init.sh |

root 密码保持不变，以兼容原有 Telnet 与 openmiio_agent。配置使用 internal-sftp，不需要单独部署 sftp-server。当前资源构建未启用额外的权限分离沙箱，保留非 root 账户隔离及 chroot，适合作为本项目的实验部署版本。

## 最简单的部署方法

1. 用现有 FTP 将项目目录 `./` 下的 `mi_gateway_2_openssh_deploy.tar.gz` 上传到网关 `/tmp/`。不要上传私钥，也不用逐个编辑配置文件。
2. 在网关 Telnet 中逐行执行以下三条短命令：

```sh
cd /tmp
tar -xzf mi_gateway_2_openssh_deploy.tar.gz
sh mi_gateway_2_openssh_deploy/install.sh
```

看到 `Deployment complete` 后即可连接。脚本不会自动重启网关。

在 Windows PowerShell 中测试：

```powershell
ssh -p 2223 root@GATEWAY_ADDRESS
```

新设备请将地址换成该设备实际 IP。首次连接核对网关显示的主机指纹；密码询问时直接回车。

MobaXterm 新建 SSH 会话，填写地址、root 和端口 2223，在 Advanced SSH settings 中选择 SSH-browser type 为 SFTP protocol。验证打开文本文件、上传和下载。

3. 准备好后，在网关执行以下命令，验证自启动：

```sh
reboot
```

等待网关重新联网后，按相同地址和端口连接。不要手动执行 post_init.sh，它会再次调用原厂业务启动器。

## 兼容性验证

已在本项目网关的 BusyBox 1.20.2 上确认安装脚本所需工具均存在，并在独立 /tmp 目录通过了解压、哈希校验、复制、权限设置、文件替换及账户选择逻辑预演。压缩包采用已实测的 GNU tar 格式。此次未执行完整安装，也未修改网关现有账户、启动脚本或服务。详细范围见 COMPATIBILITY.txt。

## 安装脚本会做什么

- 检查 root 权限、网关型号、包内 SHA-256 和可用存储空间。
- 部署 4 个静态程序、sshd_config 和 start-ssh.sh。
- 备份原账户文件、已有配置和启动钩子到 /data/openssh/backups/时间戳/；这些备份不含旧版程序，不是完整版本回滚包。
- 保留已有 SSH 主机私钥；首次部署才在该网关生成唯一的 Ed25519 主机密钥。
- 添加不可登录的 sshd 权限分离账户，不修改 root 密码。该用途只需要 passwd 中的数字 UID/GID，无须修改只读的 /etc/group。
- 每次启动创建 /var/empty，随后启动 SSH，同时继续调用原厂 /bin/fw_manager.sh -r。
- 识别本项目之前的简单 SSH 钩子；若发现不相关的自定义 post_init.sh，会停止安装，避免覆盖其他业务。
- 保留运行中的 OpenSSH 进程和会话；重新部署后重启才能确保所有服务端进程使用新程序和配置。

包内没有任何设备主机私钥、root 密码哈希、token 或网关密钥。不要将运行设备的整个 /data/openssh 目录复制给其他设备。

## 查看配置和日志

```sh
cat /data/openssh/etc/sshd_config
cat /var/log/openssh-start.log
cat /var/log/openssh.log
```

日志在 /var 中，重启后清空。自启动异常时使用原有 Telnet 检查。若需手动启动 SSH，只执行：

```sh
sh /data/openssh/start-ssh.sh
```

启动前可以单独检查配置：

```sh
/data/openssh/sbin/sshd -t -f /data/openssh/etc/sshd_config
```

## 关闭开机启动

若 /tmp 中的解压目录还在，可执行：

```sh
sh /tmp/mi_gateway_2_openssh_deploy/disable-autostart.sh
```

或者直接执行以下两条命令：

```sh
chmod 644 /data/scripts/post_init.sh
sync
```

这不会立即断开 SSH；下次开机不再运行该钩子，rcS 会走原厂默认启动分支。程序、配置和主机密钥保留。本包提供开机启动，不提供进程异常退出后的自动重启。

## 资源目录

```text
install.sh                 安装脚本
disable-autostart.sh       关闭本包管理的自启动
scripts/start-ssh.sh       可单独执行的 SSH 启动器
scripts/post_init.sh       原厂启动钩子模板
payload/sbin/sshd          服务端监听程序
payload/libexec/sshd-session
payload/libexec/sshd-auth
payload/bin/ssh-keygen     主机密钥生成工具
payload/etc/sshd_config    已验证配置
SHA256SUMS                 包内文件校验清单
VERSION.txt                资源版本与验证范围
licenses/                  第三方许可说明
```

恢复出厂设置、厂商 OTA 或清理 /data、/res 可能使自启动或账户失效；普通重启已验证可保留。后续不要只替换 sshd，sshd、sshd-session 与 sshd-auth 应保持同一版本。
