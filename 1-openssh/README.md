> GitHub 源码版：大型构建依赖和预构建包不随仓库提供。构建前按 [BUILD-RESOURCES.md](../BUILD-RESOURCES.md) 补齐资源并恢复链接；安装包从 Release 获取。


## 部件说明

OpenSSH Portable 10.6p2，提交 `d449e662b6b8b8cb20e852d8084c269af1c5e8f1`。ARMv7/musl 静态构建；包含 sshd、sshd-session、sshd-auth、ssh-keygen，使用 internal-sftp，不需要额外 sftp-server。端口 2223，root 空密码保留。首次安装生成该设备自己的 SSH 主机密钥；包不携带私钥。

`src/openssh-portable` 是构建源码快照，包括本地 autoreconf 生成的 configure/aclocal/config.h.in 改动。

## 打包版本部署方法

适用于尚未安装后续 TUN/RCP/OTBR 的原厂启动链。先用原有 FTP 上传 `deploy/mi_gateway_2_openssh_deploy-0.2.5.tar.gz` 到网关 `/tmp`，在 Telnet 中执行：

```sh
cd /tmp
tar -xzf mi_gateway_2_openssh_deploy-0.2.5.tar.gz
sh /tmp/mi_gateway_2_openssh_deploy/install.sh
```

保留 Telnet 会话，另开 SSH 验证后再手动重启。当前已完成后续部件的网关不要重跑本安装器覆盖启动链。

## 验证方法

Windows PowerShell：

```powershell
ssh -p 2223 root@GATEWAY_ADDRESS
```

用 SFTP 2223 打开目录、读取文件，并在 `/tmp` 上传/下载一个非敏感测试文件。

## 手动构建步骤简易说明

1. 需 make、C 编译工具、Python3；本源码已有 configure，重生成时才需要 autoconf。
2. Linux下编译执行

    ```sh
    cd ./1-openssh/src
    sh build.sh
    ```

    入口包含已记录的交叉 configure 参数和四个目标；重建包输出 `src/build-output/`，不覆盖冻结的 deploy 包。构建出处另见 src/BUILD-PROVENANCE.txt。
