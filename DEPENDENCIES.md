# 构建依赖

共享依赖集中在 `0-build-src`，各部件使用项目内部相对软链接，不依赖项目外的旧开发目录。保留目录结构即可分别进入各部件 `src` 运行 `build.sh`。

| 共享位置 | 内容 | 使用者 |
| --- | --- | --- |
| `0-build-src/toolchains/armv7-musl` | ARMv7 musl GCC 13.3.0 | OpenSSH、TUN smoke、RCP 工具、OTBR |
| `0-build-src/toolchains/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf` | 内核 GCC 9.2 | TUN 模块 |
| `0-build-src/openssl/arm` | 静态 OpenSSL 库及头文件 | OpenSSH、OTBR |
| `0-build-src/openssl/source` | OpenSSL 源码 | 可选重建依赖 |
| `0-build-src/linux/linux-chenxing-vendor-slop-ikayaki_dlm00v014` | 候选 Linux BSP 源码 | TUN |
| `0-build-src/linux/kernel-archive` | 原始 BSP ZIP，恢复源码执行权限时仍需使用 | TUN |
| `0-build-src/vendor/ot-br-posix` | OTBR 与递归子模块 | OTBR |
| `0-build-src/vendor/noise-c` | Noise-C | Native API、Thread Proxy |
| `0-build-src/vendor/yaml-cpp` | YAML 解析器 | OTBR |
| `0-build-src/firmware` | RCP / Zigbee 应用 GBL | RCP 工具打包及回归 |

关键文件指纹和修订位于 `0-build-src/DEPENDENCY-MANIFEST.json`，相对链接清单位于 `0-build-src/DEPENDENCY-LINKS.json`。OTBR 依赖准备程序会调用 Git 检查子模块修订，因此保留上游 `.git` 信息；不要删除后再使用现有构建入口。

`0-build-src/optional` 中的 openmiio_agent、silabs-firmware-builder、simplicity-sdk 只有缺失说明，完整上游源码需自行提供。它们不是重建本项目 Shell 管理脚本、原生刷写工具和 OTBR Host 的必需输入；重新编译上游 openmiio 或无线固件时才需要补齐。

主机需要 Linux x86_64、C/C++ 构建工具、CMake、make、Git、Python3；TUN 内核准备还需 flex、bison、bc。Python 互操作测试按对应脚本需要安装 aioesphomeapi、PyYAML 等依赖，不要求 ESPHome 虚拟环境，也不要求安装完整 ESPHome。

构建缓存、下载缓存和构建生成的重复部署目录不随源码保留，首次构建会重新生成。冻结发布件保存在各部件 `deploy` 中，构建不会自动覆盖这些文件。部署版本以根 `VERSION`、发布包文件名及包内 `VERSION` 为准；`deploy` 目录无需额外 VERSION 文件。

从项目根目录执行 `python3 verify-release.py` 可离线检查发布文件、依赖指纹、相对链接和脚本语法，不会编译或操作网关。手动构建仍由用户选择。归档项目时保留软链接，不要使用 `tar --dereference` 重复展开共享依赖。各上游源码和发布包内许可证应一并保留。
