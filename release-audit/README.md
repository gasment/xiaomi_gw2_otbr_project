# GitHub 源码版校验

当前预构建发布件位于各部件的 deploy 目录。当前校验入口为根 verify-release.py；外部发布件及构建资源校验方式见 ../BUILD-RESOURCES.md。下列文件保留已验证版本的文件映射和出处，不表示本地 SDK 已补齐。

# 当前发布校验

项目版本以根 VERSION 为准。ARCHIVE-DEVICE-MATCH.json 保留此前实机验收的文件映射；extra-public-dependencies.json 与 BOOT-CHAIN.json 记录单一 stock anchor、API 1 模块边界和旧链迁移规则。verify-installed.py 只读核对这些公开文件，不读取网关运行配置或密钥。

SOURCE-PAYLOAD-MAP.json 用于离线核对发布脚本和对应源码模板，SOURCE-FINGERPRINTS.json 记录自有源码指纹。RELEASE-COMPONENTS-0.3.2.json 记录当前组件包、GUI 和 RCP 哈希，其余版本归档记录用于追溯。PUBLIC-EXAMPLE-KEY.json 仅登记上游公开示例常量。

README 可独立修订；deploy 下不要求额外 VERSION。发布包内仍带 VERSION 及自身 SHA256SUMS。根 SHA256SUMS 覆盖自有发布文件，deploy/SHA256SUMS 覆盖该部件发布文件；共享依赖由 0-build-src 的关键指纹与相对链接清单单独核对。

哈希一致性不替代实机业务验收；RCP Flash 未做免拆完整字节回读。0.3.2 的部署包已通过离线验证。
