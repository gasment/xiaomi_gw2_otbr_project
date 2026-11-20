> GitHub 源码版：大型构建依赖和预构建包不随仓库提供。构建前按 [BUILD-RESOURCES.md](../BUILD-RESOURCES.md) 补齐资源并恢复链接；安装包从 Release 获取。

## post_init 模块

本组件只增删 `tun` 模块。模块在后台准备驱动；失败不会阻止最终原厂锚点。


# 2 — TUN 驱动（项目版本 0.3.0）

## 部件说明

为已验证的原厂 Linux 4.9.84 提供 tun.ko、`/dev/net/tun`（10:200）和启动包装。模块来自 SigmaStar Pioneer3 BSP 候选内核，已做 vermagic、基础模块 ABI、网络结构锚点、导入符号核对，并经本机 IPv6 TUN 双向 smoke 测试及重启验证。

`src/tun_lab` 保留模块、ABI probe、smoke 程序及构建/校验源码；`tested-kernel.config` 是已验证配置；`src/origin_ko` 是当前网关原厂 ABI 参考模块；完整内核源码和两个工具链需按资源文档补齐；执行权限已独立保存，不再需要保留 ZIP

## 打包版本部署方法

先完成 OpenSSH。上传 `deploy/mi_gateway_2_tun_deploy-0.3.0.tar.gz` 到 `/tmp`：

```sh
cd /tmp
tar -xzf mi_gateway_2_tun_deploy-0.3.0.tar.gz
sh /tmp/mi_gateway_2_tun_deploy/install.sh
reboot
```

安装器读取 `/etc/os-release` 中的 `LUMI_VERSION`，接受 `1.0.8_0015` 及更高版本；不再比较完整 `/proc/version` 构建串。更高版本的长期兼容性尚未逐版验收。已有后续 RCP/OTBR 包装时不要重装本层。

## 验证方法

```sh
grep '^tun ' /proc/modules
cat /sys/class/misc/tun/dev
ls -l /dev/net/tun
```

预期模块存在，设备号 10:200。仅在 OTBR 尚未运行或已由用户停止时运行独立测试：

```sh
/data/tun/tun-smoke
```

要求 `TUN_IPV6_ROUNDTRIP_PASS`；测试结束临时 mgtun0 应消失。此程序不替代真实 BR 路由验收。
## 手动构建步骤简易说明

1. Linux编译需 make/gcc/flex/bison/bc/python3。
3. 执行命令：

    ```sh
    cd ./2-tun-driver/src
    sh build.sh
    ```

    入口创建独立 kernel-work、修补 BSP Python3 调用、应用冻结配置，准备内核、构建 probe 和 tun.ko，执行 ABI/符号检查，再构建静态 smoke 程序。重建包写入 `src/build-output/`。发布包按 `LUMI_VERSION >= 1.0.8_0015` 放行；更高 Xiaomi 固件若日后出现模块加载或符号不兼容，再单独适配。
