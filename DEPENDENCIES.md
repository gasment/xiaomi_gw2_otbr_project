# 构建依赖

GitHub 源码版不携带大型依赖，完整的资源位置、版本、校验和补齐步骤见 [BUILD-RESOURCES.md](BUILD-RESOURCES.md)。锁定清单位于 [dependencies/lock.json](dependencies/lock.json)，相对链接清单位于 [dependencies/links.json](dependencies/links.json)。

补齐资源后，在 WSL 内执行 `python3 tools/restore-dependencies.py --create-links`；默认源码校验不要求外部 SDK 存在。预构建包保存在仓库之外的 Release 资产目录，不纳入 Git。

完整的环境准备、文件获取与重建步骤见 [构建准备](BUILD-PREPARATION.md)。
