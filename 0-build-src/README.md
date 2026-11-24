# 共享构建依赖

各部件通过内部相对软链接复用本目录中的工具链、SDK、静态库和上游源码。内容与可选缺失源码见根 DEPENDENCIES.md。

DEPENDENCY-MANIFEST.json 记录关键文件指纹与上游修订；DEPENDENCY-LINKS.json 记录部件的相对链接。保留原有许可证、上游 Git 元数据、工具链执行权限和软链接，不要展开所有链接重复复制 SDK。
