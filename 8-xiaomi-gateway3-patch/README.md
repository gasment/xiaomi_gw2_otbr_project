# XiaomiGateway3 密码补丁（UI 版，0.2.5）

本目录提供 HA 运行时密码补丁、网关交互密码脚本与 BLE Spec Cache。密码补丁单独部署，BLE Spec Cache 可在 Windows 自动部署工具中选装。用于解决`xiaomi_gateway3`集成的无密码telent登录和阻止其root密码删除行为

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

当前 HA 密码保护修订为 3（不是 BLE 缓存补丁修订号）：引导在 Gateway3 模块导入时，直接去掉其官方 Telnet 开启命令中的 `passwd -d`；AsyncMiIO 发送层和 SyncMiIO/AsyncMiIO 共用的报文打包层还会再次处理该命令。共享打包层可覆盖绕过异步发送包装、或提前保存原发送方法的调用。这条保护不依赖 UI 配置、IP 匹配或条目加载先后。无法安全拆分的 `enable_telnet_service` 一律阻止，未审查的特权报文也会拒绝。

配置未就绪时，受保护网关的密码登录继续等待或拒绝，不回退空密码。禁用条目不会从运行中的 Python 进程移除全局导入钩子。

### 已安装用户：修复 Docker 冷启动后密码被清空

1. 覆盖 HA `/config/custom_components/xiaomi_gateway3_telnet_patch/` 整个组件目录，保留现有 UI 条目及 `/config/custom_components/__init__.py` 启动引导。
2. 在 HA 容器终端运行下面的只读检查。它只输出是否存在引导、两边网关地址是否匹配，不输出密码或 Token：

    ```sh
    python /config/custom_components/xiaomi_gateway3_telnet_patch/check_config.py
    ```

   两台网关都应为 `password_login_config=matched`，且 `BOOTSTRAP_ON_DISK=present`。该检查只验证磁盘配置，不能替代运行中钩子的确认。
3. 用你原来的 `docker restart` 方式冷启动 HA。启动日志应有 `GW2_PASSWORD_PATCH_EARLY_GUARD_ACTIVE`（revision 3）、`GW2_PASSWORD_PATCH_PACKET_GUARD_ACTIVE`、`GW2_PASSWORD_PATCH_COMMAND_GUARD_ACTIVE` 和 `GW2_PASSWORD_PATCH_CONFIG_READY`。各模块按需加载，日志先后不作为判定依据。缺少早期保护标记时，先检查启动引导及 HA 实际挂载的 `/config`，不要声称密码已受保护。
4. 对已被清空密码的网关，通过现有空密码 Telnet 登录，运行下面的密码脚本，设置与该网关 HA 补丁条目相同的密码。SSH 无需重装，也无需允许空密码。
5. 使用实际故障触发方式验收：如果原自动化同时重启网关和 HA 容器，应运行这套并发流程；仅单独重启 HA 不足以覆盖它。确认密码仍为 `ROOT_AUTH=sha512`、新密码 SSH 可登录，以及 BLE 有新的状态更新。

Gateway3 command 实体的 reboot 动作本身只发送 `reboot`。网关启动期间端口不可达，可能触发额外的 Telnet 开启流程；两者必须区分。新打包层会记录 `GW2_PASSWORD_PATCH_TELNET_ENABLE_PACKED`，只含目标 IP、方法、同步/异步路径及 `command=safe`，不记录口令或 miIO 认证参数。该日志代表安全命令已打包，不代表网关已经收到。若网关仍记录收到含 `passwd -d` 的原始 `system_command`，应按时间关联发送路径，不能仅凭已有启动标记认定本次发送已经受保护。

早期保护仍依赖 `/config/custom_components/__init__.py` 引导实际执行。其他 HA 实例或其他客户端发出的删密码命令不在本补丁控制范围内。单凭一台网关丢失密码，无法直接认定具体执行者或启动时序；应结合上述检查和启动日志确认。

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
   ssh -p 2223 -o PubkeyAuthentication=no -o PreferredAuthentications=password root@192.0.2.10
   ```
   输入新密码，应能登录。
  重启 HA 后新蓝牙状态正常、root 密码仍保留、新密码 SSH 登录成功，就完成了正常重连测试

    确认新 SSH 登录能成功，并且在HA重启后XiaomiGateway3蓝牙状态更新正常后，再关闭原终端。

## 作用范围

- 受保护 MGW2 的 Telnet 登录使用所配密码，不接受空密码回退。
- 未列入密码配置的网关仍用原登录方式；但 Gateway3 官方 Telnet 开启命令中的删密码部分同样会被剔除，内置 `enable_telnet_service` 会被阻止。依赖这两个清密码行为的旧网关需要另行确认兼容性。
- 修改地址或删除条目时，旧地址在当前 HA 进程中不会立即恢复为可删密码的旧逻辑。
- 本补丁只约束安装它的 HA 实例。其他未打补丁的实例或掌握 miIO 凭据的客户端，仍可能执行原厂接口。
- Telnet 仍是明文传输。
- 设密码后，之前仅支持空密码的 Windows 自动部署/OTA 客户端不能直接继续使用。

卸载时，删除 UI 条目，并从 `custom_components/__init__.py` 移除带标记的引导块（以及旧版手工两行，如有），随后重启 HA。保留该文件中的其他原始代码。补丁不会自动删除网关 root 密码；原版 XiaomiGateway3 仍不支持此密码登录。

## 其他
本项目openssh基于0.2.5编译期最新的`10.6p2`，不受"sshole"密码认证绕过漏洞风险（CVE-2026-123158）影响
