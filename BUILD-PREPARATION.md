# 构建准备

本文按全新 GitHub clone 整理完整的环境准备与文件准备。普通用户使用 Windows 一键部署包时，不需要执行这些步骤。所有命令由构建者自行执行；本文不会自动编译或连接网关。

## 1. 工作目录与主机环境

使用 Linux x86_64／WSL。建议在 WSL 的 Linux 文件系统 clone 仓库，进入仓库根目录；不要在 Windows 资源管理器中复制 Linux 软链接。

下面各节以仓库根目录为起点。首次进入根目录后设置：

```sh
PROJECT_ROOT=$(pwd)
```

Ubuntu／WSL 环境安装主机工具：

```sh
sudo apt update
sudo apt install build-essential cmake git perl pkg-config flex bison bc python3 python3-venv libssl-dev ca-certificates curl file unzip xz-utils
```

`libssl-dev` 只用于 x86_64 原生测试，不代替 ARM 静态 OpenSSL。OpenSSH 已保留 configure；只有自行重新生成时才需要 autoconf／automake。

准备 Python 测试环境，已使用的测试依赖版本如下，现有验证环境使用 Python 3.12：

```sh
python3 -m venv .venv-build
. .venv-build/bin/activate
python -m pip install aioesphomeapi==46.12.0 PyYAML==6.0.3 cryptography==50.0.2
```

不需要安装完整 ESPHome，也不需要使用原作者的 ESPHome 虚拟环境。后续重新打开终端时，先进入仓库并激活 `.venv-build`。

## 2. 文件目录总览

补齐后需要形成以下目录。`BUILD-RESOURCES.md` 是精确资源清单，`dependencies/lock.json` 保存关键文件指纹。

```text
0-build-src/
├── downloads/                         # 本地下载缓存
├── toolchains/
│   ├── armv7-musl/
│   └── gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/
├── openssl/
│   ├── source/                        # 重建 OpenSSL 时需要
│   └── arm/                           # 静态 ARM 库及头文件
├── linux/
│   └── linux-chenxing-vendor-slop-ikayaki_dlm00v014/
├── vendor/
│   ├── ot-br-posix/
│   ├── noise-c/
│   └── yaml-cpp/
└── firmware/
    ├── lumi-gateway-mgl001_openthread_rcp_2.5.3.0_115200.gbl
    └── xiaomi_stock_ncp_6.6.6.0_build218.gbl
```

如果已有完整开发环境，可以直接复制这些目录，保留执行权限与上游 Git 元数据，然后跳到第 7 节。不要复制编译缓存、重复 ZIP 或 Windows 中的零字节链接文件。已有匹配的静态 OpenSSL 时，不必重新构建它。

下列在线获取步骤仅用于缺失目录；已有目录时不要重复 clone 或解压覆盖。

## 3. 两套交叉工具链

### ARM musl 工具链

Bootlin 的下载目录提供该版本 tar.xz 和校验文件：
[armv7-eabihf 工具链目录](https://toolchains.bootlin.com/downloads/releases/toolchains/armv7-eabihf/tarballs/)。

```sh
mkdir -p 0-build-src/downloads
cd 0-build-src/downloads
BOOTLIN_BASE=https://toolchains.bootlin.com/downloads/releases/toolchains/armv7-eabihf/tarballs
curl -fLO "$BOOTLIN_BASE/armv7-eabihf--musl--stable-2024.05-1.tar.xz"
curl -fLO "$BOOTLIN_BASE/armv7-eabihf--musl--stable-2024.05-1.sha256"
sha256sum -c armv7-eabihf--musl--stable-2024.05-1.sha256
cd "$PROJECT_ROOT"
mkdir -p 0-build-src/toolchains/armv7-musl
tar -xJf 0-build-src/downloads/armv7-eabihf--musl--stable-2024.05-1.tar.xz --strip-components=1 -C 0-build-src/toolchains/armv7-musl
sh 0-build-src/toolchains/armv7-musl/relocate-sdk.sh
0-build-src/toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-gcc --version
```

### 内核专用 GNU 9.2 工具链

仅 TUN 内核模块使用此工具链；不要用它替换其他部件的 musl 工具链。

```sh
sh 2-tun-driver/src/tun_lab/fetch-toolchain.sh
```

入口会下载到共享缓存、解压到共享 toolchains 目录，不会编译内核。已有完整工具链时直接复用。后续资源检查会核对编译器指纹。

## 4. 上游源码文件

### Linux BSP

```sh
mkdir -p 0-build-src/linux
git clone --branch ikayaki_dlm00v014 --single-branch https://github.com/linux-chenxing/linux-chenxing-vendor-slop.git 0-build-src/linux/linux-chenxing-vendor-slop-ikayaki_dlm00v014
```

资源恢复入口会在源码缺少 `.config` 时补入仓库保存的初始配置；TUN 构建随后使用已验证的 `tested-kernel.config`。原 ZIP 中的执行权限已独立保存在仓库，不需要再保留大 ZIP。

### OTBR 与递归子模块

```sh
mkdir -p 0-build-src/vendor
git clone https://github.com/openthread/ot-br-posix.git 0-build-src/vendor/ot-br-posix
git -C 0-build-src/vendor/ot-br-posix checkout 285bcb549edcfe6823269b4df2f0982298bc1e56
git -C 0-build-src/vendor/ot-br-posix submodule update --init --recursive
```

保留 `.git` 和全部子模块 Git 元数据。Web 依赖准备程序会检查固定的 cJSON、cpp-httplib 修订，因此仅提供不带 Git 信息的源码 ZIP 不满足现有入口要求。

### Noise-C 与 yaml-cpp

```sh
curl -fL https://codeload.github.com/esphome-libs/noise-c/tar.gz/62c2fdca7a874ea898761147bb062ca1cde9f36d -o 0-build-src/downloads/noise-c-0.1.31.tar.gz
curl -fL https://codeload.github.com/jbeder/yaml-cpp/tar.gz/refs/tags/yaml-cpp-0.9.0 -o 0-build-src/downloads/yaml-cpp-0.9.0.tar.gz
sha256sum -c dependencies/source-archives.sha256
mkdir -p 0-build-src/vendor/noise-c
mkdir -p 0-build-src/vendor/yaml-cpp
tar -xzf 0-build-src/downloads/noise-c-0.1.31.tar.gz --strip-components=1 -C 0-build-src/vendor/noise-c
tar -xzf 0-build-src/downloads/yaml-cpp-0.9.0.tar.gz --strip-components=1 -C 0-build-src/vendor/yaml-cpp
```

恢复入口会按需要补入 Noise-C 的构建适配文件和 yaml-cpp 的本地源码清单。下载归档先按锁定 SHA256 检查，不使用未锁定的最新版替换。

## 5. 两份无线 GBL 与可选发布资源

直接把资源清单中的两份精确 GBL 放到 `0-build-src/firmware`。仓库不再提供包含旧版整包安装器的 Windows 部署 ZIP，也不应从自动部署 EXE 中提取或替换构建资源。

RCP 工具构建会校验两份 GBL，不重新编译无线固件，也不会执行刷写。普通 Host 构建不需要 Silicon Labs SDK。仅重编无线固件或外部 openmiio 时才需要清单中的可选 SDK／Go 环境。

Windows 管理端从各部件 `deploy` 目录直接汇集资源，构建入口为 `7-auto-deploy/gui-python/build.ps1`。自行编译的新产物仍需重新验收并更新发布指纹，不能直接当作原已验证发布件。

## 6. ARM 静态 OpenSSL

如果已有与资源锁定指纹匹配的 `0-build-src/openssl/arm`，可以跳过本节。

先准备固定源码：

```sh
mkdir -p 0-build-src/openssl
git clone https://github.com/openssl/openssl.git 0-build-src/openssl/source
git -C 0-build-src/openssl/source checkout 84dda7853c130429210b37bee9e5b62366ca8bce
```

执行仓库内的构建入口：

```sh
sh tools/build-openssl.sh
```

入口使用原配置记录：`linux-armv4`、Cortex-A7、NEON-VFPv4、hard-float、`-Os -fPIC` 和 `no-shared no-tests no-module no-dso`。构建目录为 `0-build-src/openssl/build-arm`，安装目录为 `0-build-src/openssl/arm`。已有构建或安装目录时停止，不会覆盖已有库。默认并行度为 2，可通过 `JOBS` 调整。

生成后会检查静态归档中的 ARM32 对象并记录本地构建信息，不在 x86_64 主机运行 ARM 程序。新构建的哈希可能与原发布库不同；验证结果后显式登记本地依赖：

```sh
python3 tools/record-openssl-build.py --accept
```

这一步核对记录与当前库一致，再更新两个 OpenSSL 依赖锁及其源码校验值。它不修改已发布程序和实机验收指纹。复用原匹配库时无需登记。

## 7. 恢复链接与准备完成检查

```sh
python3 tools/restore-dependencies.py --create-links
python3 verify-release.py --dependencies
```

只有出现 `BUILD_RESOURCES_READY`，且依赖／源码检查通过后，才进入构建。缺失项会列出具体路径和指纹问题，不会自动跳过。

只构建某个部件时可限定编号，例如：

```sh
python3 tools/restore-dependencies.py --create-links --component 5
```

这一步才创建指向当前仓库 `0-build-src` 的相对软链接，不依赖原作者目录。资源缓存、虚拟环境和生成链接不提交 Git。

## 8. 构建入口

以下各组命令均从仓库根目录开始，构建顺序与网关实际安装顺序不是同一概念。构建不会自动连接网关、刷写无线模块或启动 Thread。

### OpenSSH

```sh
cd 1-openssh/src
sh build.sh
```

输出：`1-openssh/src/build-output/mi_gateway_2_openssh_deploy-rebuilt.tar.gz`。

### TUN

```sh
cd 2-tun-driver/src
sh build.sh
```

入口会准备独立内核树、应用固定配置、构建 ABI probe 与 tun.ko，并执行静态兼容检查和 smoke 程序的交叉编译。构建时不在主机加载 ARM 模块，也不运行网关侧 IPv6 smoke。

输出：`2-tun-driver/src/build-output/mi_gateway_2_tun_deploy-rebuilt.tar.gz`。不同内核不得因文件编译成功就直接加载。

### RCP 原生工具与启动隔离

```sh
cd 3-rcp-mode/src
sh build.sh
```

两份 GBL 直接从 `0-build-src/firmware` 读取并校验，不依赖先下载已发布的 rcp-native tar。入口包含本机刷写器回归测试、ARM 工具构建及隔离脚本打包，不会重新编译无线 GBL，也不会访问网关 UART。

输出位置：`3-rcp-mode/src/build-output/`；原生工具和探测器另见 `3-rcp-mode/src/rcp_lab/native-tools/`。生成的包名以构建输出为准。

### BLE/openmiio 管理部件

```sh
cd 4-rcp-openmiio/src
sh build.sh
```

输出：`4-rcp-openmiio/src/build-output/rcp-openmiio-rebuilt.tar.gz`。这一步只打包本项目管理脚本，不生成外部 openmiio 程序。

### OTBR Host

保持前述测试 Python 环境可用，从仓库根目录开始：

```sh
cd 5-otbr/src
sh build.sh
```

入口运行本机配置／API／Web／代理回归、固定依赖检查，再交叉构建启用用户态 BBR 后端的 ARM Host 并打包。输出：`5-otbr/src/otbr_host/otbr-deploy-bbr.tar.gz`。

如果没有激活测试环境，可用 `OTBR_API_TEST_PYTHON` 指向包含 aioesphomeapi 和 PyYAML 的 Python 可执行文件。构建入口不读取网关实际 YAML；运行配置仍由用户在网关编辑。

## 9. 输出与验证范围

构建不会自动上传网关、刷写无线模块或导入 Thread 配置。生成的包不自动覆盖已有 Release；发布前仍需对新产物进行实机验证并更新发布指纹。

本次补充了准备文档、OpenSSL 构建入口和静态检查；没有执行编译。完整“全新 clone → 在线获取所有资源 → 五个部件全部构建”的最终验收仍待实际运行。
