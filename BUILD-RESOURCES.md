# 构建补充资源清单

## 必需资源

| 放置路径 | 资源及版本 | 使用部件 |
| --- | --- | --- |
| `0-build-src/toolchains/armv7-musl` | [Bootlin](https://toolchains.bootlin.com/) armv7-eabihf musl **stable-2024.05-1**，GCC 13.3.0；入口 `bin/arm-buildroot-linux-musleabihf-gcc` | 1、2 的 smoke、3、5 |
| `0-build-src/toolchains/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf` | Arm GNU **9.2-2019.12**，GCC 9.2.1；交叉前缀 `arm-none-linux-gnueabihf-`；归档地址见 `2-tun-driver/src/tun_lab/fetch-toolchain.sh` | 2 |
| `0-build-src/openssl/arm` | ARMv7 musl 静态 OpenSSL 库及头文件：`include/openssl`、`lib/libssl.a`、`lib/libcrypto.a`；指纹见 `dependencies/lock.json` | 1、5 |
| `0-build-src/linux/linux-chenxing-vendor-slop-ikayaki_dlm00v014` | [linux-chenxing 候选 BSP](https://github.com/linux-chenxing/linux-chenxing-vendor-slop/tree/ikayaki_dlm00v014)，分支 **ikayaki_dlm00v014** | 2 |
| `0-build-src/vendor/ot-br-posix` | [OTBR](https://github.com/openthread/ot-br-posix) 提交 **285bcb549edcfe6823269b4df2f0982298bc1e56**，包含递归子模块和 Git 元数据 | 5 |
| `0-build-src/vendor/noise-c` | Noise-C 0.1.31，esphome-libs 提交 **62c2fdca7a874ea898761147bb062ca1cde9f36d**；下载地址及 SHA256 见 `5-otbr/src/otbr_host/deps.lock.json` | 5 |
| `0-build-src/vendor/yaml-cpp` | **yaml-cpp-0.9.0**；下载地址及 SHA256 见 `5-otbr/src/otbr_host/deps.lock.json` | 5 |
| `0-build-src/firmware/lumi-gateway-mgl001_opentread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_460800.gbl` | [silabs-firmware-builder](https://github.com/darkxst/silabs-firmware-builder) 的 **20250627** 发行，SDK 2024.6.3，UART 460800、硬件流控 | 3 |
| `0-build-src/firmware/xiaomi_stock_ncp_6.6.6.0_build218.gbl` | 原厂 Zigbee **6.6.6.0 build 218** 应用固件，可从已验证的 `rcp-native-0.2.0.tar.gz` 获取；SHA256 见 `dependencies/lock.json` | 3 |

## OTBR 子模块

| 资源 | 固定修订 |
| --- | --- |
| OpenThread | `3de409682fa2a28452d91ec00c2614b70f986b75` |
| mbedTLS | `e185d7fd85499c8ce5ca2a54f5cf8fe7dbe3f8df` |
| mbedTLS framework | `457996474728cb8e968ed21953b72f74d2f536b2` |
| cJSON | `cf97c6f066d81fdbba4ef722cfd327bbbba2365c` |
| cpp-httplib | `03cf43ebaa55f27a2778bed870ea3549f7e84e2c` |

## 可选资源

| 放置路径 | 资源及版本 | 用途 |
| --- | --- | --- |
| `0-build-src/openssl/source` | [OpenSSL](https://github.com/openssl/openssl)，提交 `84dda7853c130429210b37bee9e5b62366ca8bce` | 重建静态 OpenSSL |
| `0-build-src/optional/openmiio_agent` | [openmiio_agent](https://github.com/AlexxIT/openmiio_agent) 源码及 Go 环境；部署二进制为 1.2.1，精确构建提交未确认 | 重编 openmiio |
| `0-build-src/optional/silabs-firmware-builder` | Silicon Labs 无线固件构建工程 | 重编无线固件 |
| `0-build-src/optional/simplicity-sdk` | Silicon Labs SDK **2024.6.3** 及对应构建环境 | 重编无线固件 |

## Windows Release 打包资源

| 放置目录 | 文件 |
| --- | --- |
| 仓库同级 `release/` | `mi_gateway_2_openssh_deploy-0.2.0.tar.gz` |
| 同上 | `mi_gateway_2_tun_deploy-0.2.0.tar.gz` |
| 同上 | `rcp-native-0.2.0.tar.gz` |
| 同上 | `rcp-mode-0.2.0.tar.gz` |
| 同上 | `rcp-openmiio-0.2.0.tar.gz` |
| 同上 | `mi-gw2-otbr-0.2.0.tar.gz` |
| 同上 | `rcp-recovery-update-0.2.0.tar.gz` |
| 同上 | `spinel-probe-0.2.0` |
| 同上 | `openmiio_agent-1.2.1-arm` |

## 主机构建工具

| 使用范围 | 所需工具 |
| --- | --- |
| 源码构建 | Linux x86_64／WSL、make、C/C++ 编译工具、CMake、Git、Python3 |
| TUN 内核准备 | flex、bison、bc |
| Python 互操作测试 | 按测试需要提供 aioesphomeapi、PyYAML 等依赖 |
