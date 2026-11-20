# 小米多模网关 2：TUN 部署

## post_init 模块

本组件只增删 `tun` 模块。模块在后台准备驱动；失败不会阻止最终原厂锚点。


本包用于本项目已验证的原厂内核，提供 tun.ko、自启动、设备节点创建和手动 IPv6 收发测试。本文只介绍部署，不包含编译步骤。

## 适用设备

适用于 lumi.gateway.mcn001、硬件 1.0。安装器和启动器读取 `/etc/os-release` 的 `LUMI_VERSION`，接受 `1.0.8_0015` 及更高版本，不再比较完整 `/proc/version`。更高版本的兼容性保留为后续实测项。

已通过模块加载、临时接口创建、IPv6 双向收发和自动清理测试，详见 validation/runtime-results.md。长期稳定性和完整 OTBR 尚未验证。

## 最简单的安装方法

将项目目录 ./ 下的 `mi_gateway_2_tun_deploy.tar.gz` 通过 FTP/SFTP 上传到网关 /tmp。在网关的 SSH 或 Telnet 中逐行执行：

```sh
cd /tmp
tar -xzf mi_gateway_2_tun_deploy.tar.gz
sh mi_gateway_2_tun_deploy/install.sh
```

看到 `TUN deployment complete` 表示安装器完成。脚本不会自动重启、刷写内核或无线芯片，也不修改 root 密码。

## 与现有 SSH 启动的关系

安装器识别本项目的 OpenSSH 启动钩子，原样保存为 /data/tun/original-post_init.sh。新钩子先准备 TUN，再执行保存的原钩子，原钩子继续启动 SSH 和原厂业务。

```text
rcS
  -> /data/scripts/post_init.sh
      -> /data/tun/start-tun.sh
      -> 原 OpenSSH 钩子
          -> SSH 与原厂 fw_manager.sh -r
```

没有原有钩子时直接回退原厂启动器。TUN 启动失败返回后仍会继续后面的业务启动。发现不相关的自定义启动脚本时，安装器会停止，避免覆盖其他业务。

此后若要重新安装旧 OpenSSH 部署包，应先执行本包的撤销自启动步骤，恢复 SSH 钩子；安装 OpenSSH 后再安装本包。旧 OpenSSH 安装器不会识别 TUN 包装钩子，不能直接覆盖。

## 重启验证

准备好后执行：

```sh
reboot
```

重新连接 SSH/Telnet 后执行：

```sh
grep '^tun ' /proc/modules
cat /sys/class/misc/tun/dev
ls -l /dev/net/tun
```

应看到 tun 已加载、设备号为 10:200、/dev/net/tun 为 root 拥有且权限 crw------- 的字符设备。/dev 是临时文件系统，因此每次开机都需要重新创建节点。

需要手动准备驱动时执行：

```sh
sh /data/tun/start-tun.sh
```

驱动已经加载时不重复加载，只核实注册及节点。程序无法从内核中恢复已加载模块的原始文件哈希；安装前若已加载别的 tun.ko，需先停用相关接口并卸载，或在安装后重启，才能确保运行本包的模块。

## 可选的收发测试

该测试只在手动执行时运行，不加入开机启动：

```sh
/data/tun/tun-smoke
```

成功标志为 TUN_IPV6_ROUNDTRIP_PASS。测试使用临时 mgtun0 和专用 ULA 地址，模拟 IPv6 echo 对端。关闭文件描述符后接口、测试地址及附属路由应自动消失，不修改现有默认路由。

```sh
ip link show mgtun0
dmesg | tail -n 30
```

第一条应提示找不到设备；内核日志中不应有本次测试新增的 Oops/BUG。

## 日志与撤销

```sh
cat /var/log/tun-start.log
```

若要撤销 TUN 自启动并恢复之前的 SSH/原厂启动钩子：

```sh
sh /data/tun/uninstall-autostart.sh
```

脚本保留模块及测试程序，不停止当前 SSH 或原厂业务，不立即卸载正在使用的驱动。下一次重启不再通过本包加载 TUN。原钩子的权限也会恢复；无原钩子则恢复 rcS 的默认分支。若包装钩子被其他程序修改，脚本会停止而不会覆盖。

仅在确认没有程序使用 TUN 接口时，可手动卸载：

```sh
rmmod tun
```

不要删除原有 SSH 钩子备份。若后续安装了 OTBR，应先停止 OTBR，再考虑卸载驱动。

## 包内资源

- payload/tun.ko：已实机测试的原始模块，SHA-256 见 SHA256SUMS。
- payload/tun-smoke：已实机测试的静态 IPv6 收发测试程序。
- scripts/：启动、启动链包装及撤销脚本。
- validation/：静态布局、导入符号和用户实机验证记录。
- provenance/kernel.config：本次构建配置。
- source/、licenses/：对应源文件与许可。

安装路径为 /data/tun，空间检查要求 /data 至少有 2 MiB 可用；安装包建议解压到 /tmp。不会备份或包含设备私钥、米家 token 等凭据。厂商 OTA 或恢复出厂可能改变兼容性或清除部署；`LUMI_VERSION` 低于 1.0.8_0015 时启动器拒绝加载。
