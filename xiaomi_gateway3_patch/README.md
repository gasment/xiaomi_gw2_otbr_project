# XiaomiGateway3 密码补丁（UI 版，0.2.5）

这是独立工具补充，不属于 OTBR 自动部署流程。目录名为 `xiaomi_gateway3_patch`。包含 HA 运行时补丁和网关交互密码脚本；不修改 XiaomiGateway3 的源文件。用于解决`xiaomi_gateway3`集成的无密码telent登录和阻止其root密码删除行为

适配的`xiaomi_gateway3`集成版本为`4.3.0`，不保证后续更新可用
## HA：全部通过 UI 配置

1. 把 `ha/custom_components/xiaomi_gateway3_telnet_patch` 整个目录复制到 HA 的 `/config/custom_components/`。
2. 需要先重启 HA，使其识别新组件。
3. 打开 **设置 → 设备与服务 → 添加集成**，搜索 **Xiaomi Gateway 3 Telnet Password Patch / 小米网关 Telnet 密码补丁**。
4. 输入网关 IP、准备使用的 root 密码，勾选 **自动安装早期启动引导**。
5. 提交后重启 HA，激活启动引导，再给网关设置相同密码。首次显示待重启/重试属于预期；重启后条目应正常加载。

每台网关添加一个条目；以后在条目的 **配置** 页面修改 IP 或密码。修改密码时留空保留原值，已有密码不会回显。修改 UI 值不会替你修改网关密码。

密码由 HA 私有配置条目存储，不写入项目文件，也不由补丁输出到日志。HA 的配置存储和备份应按含凭据的数据管理。

### 自动启动引导做了什么

用户勾选并提交 UI 后，组件向 `/config/custom_components/__init__.py` 添加带 BEGIN/END 标记的小段引导。已有代码保留；首次修改已有文件时备份为 `__init__.py.before-gw2-password-patch`。不会修改 XiaomiGateway3 目录。

引导保证在 XiaomiGateway3 模块导入结束前挂钩，防止普通集成加载顺序造成删密码窗口。新安装的引导必须重启 HA 后才生效，UI 会给出修复提示；不自动重启 HA。已有引导块被手工改动、初始化文件语法错误、符号链接或目录不可写时会拒绝自动写入。

引导存在而补丁配置未就绪时，相关 MGW2 登录和特权开启命令等待或拒绝，不回退到空密码/删密码行为。禁用条目不会从运行中的 Python 进程移除全局导入钩子。

## 网关：设置 root 密码

将 `gateway/set-root-password.sh` 放到网关 `/data/openssh/set-root-password.sh`，保留现有交互终端，执行：

```sh
chmod 755 /data/openssh/set-root-password.sh
sh /data/openssh/set-root-password.sh
```

按提示输入两次与 HA UI 一致的密码。脚本使用网关 `passwd` 交互输入，不接收命令行、环境变量或文件中的密码。

脚本会先验证 SHA-512 支持、持久化账户布局和新 SSH 配置，再修改 root 密码。账户文件位于 `/res/passwd`；Telnet 和 SSH 共用该账户。SSH 设置为允许 root 密码登录、禁止空密码登录，并仅 HUP 重载监听进程，保留现有会话。

只读检查：

```sh
sh /data/openssh/set-root-password.sh --check
```

预期为 `ROOT_AUTH=sha512`、`PasswordAuthentication yes`、`PermitRootLogin yes`、`PermitEmptyPasswords no`。

在新终端强制密码认证验证，替换示例地址：

```sh
ssh -p 2223 -o PubkeyAuthentication=no -o PreferredAuthentications=password root@192.0.2.10
```
## 验证
1. 网关终端执行：

    ```bash
    sh /data/openssh/set-root-password.sh --check
    ```
   应显示 ROOT_AUTH=sha512，以及 PermitEmptyPasswords no。
2. 在 HA 中确认密码补丁条目的网关 IP、密码正确，然后重启 HA。这会让 XiaomiGateway3 重新建立连接，避免沿用设置密码前的连接。
3. HA 启动后，实际触发一个蓝牙设备，例如开关门磁，确认 XiaomiGateway3 对应实体收到本次操作的新状态。只看实体“可用”不够。
4. 网关再次执行：
    ```bash
   sh /data/openssh/set-root-password.sh --check
   ```
   仍应为 ROOT_AUTH=sha512。再打开一个新 SSH 窗口，强制使用密码登录：
    ```cmd
   ssh -p 2223 -o PubkeyAuthentication=no -o PreferredAuthentications=password root@192.168.32.128
   ```
   输入新密码，应能登录。
  重启 HA 后新蓝牙状态正常、root 密码仍保留、新密码 SSH 登录成功，就完成了正常重连测试

    确认新 SSH 登录能成功，并且在HA重启后XiaomiGateway3蓝牙状态更新正常后，再关闭原终端。

## 作用范围

- 受保护 MGW2 的 Telnet 登录使用所配密码，不接受空密码回退。
- 配置加载完成后，未列入保护的网关保持原行为。
- 修改地址或删除条目时，旧地址在当前 HA 进程中不会立即恢复为可删密码的旧逻辑。
- 本补丁只约束安装它的 HA 实例。其他未打补丁的实例或掌握 miIO 凭据的客户端，仍可能执行原厂接口。
- Telnet 仍是明文传输。
- 设密码后，之前仅支持空密码的 Windows 自动部署/OTA 客户端不能直接继续使用。

卸载时，删除 UI 条目，并从 `custom_components/__init__.py` 移除带标记的引导块（以及旧版手工两行，如有），随后重启 HA。保留该文件中的其他原始代码。补丁不会自动删除网关 root 密码；原版 XiaomiGateway3 仍不支持此密码登录。

## 其他
本项目openssh基于0.2.5编译期最新的`10.6p2`，不受"sshole"密码认证绕过漏洞风险（CVE-2026-123158）影响