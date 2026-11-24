# 从 v0.2.x 迁移到 v0.3.0 或以上

## 前期准备
1. 确保你的网关正常运行，并能够连接到其telnet服务
2. 使用telnet连接工具登录到网关，备份你的/data/otbr/config.yaml文件到本地

## 卸载旧版组件
1. 使用v0.3.0或以上版本的GUI程序，连接到网关
2. 勾选所有组件后，点击 **卸载并清理**，注意，⚠️⚠️⚠️**执行完成后，弹窗提示重启，千万不要点确定**⚠️⚠️
3. 再次使用telnet连接工具登录到网关，删除此文件：
    ```
    rm /data/scripts/post_init.sh
    ```

    或重命名以备份：
    ```
    mv /data/scripts/post_init.sh /data/scripts/post_init.sh.bak
    ```  
4. 再次检查`/data/scripts`目录下没有`post_init.sh`
    ```
    ls /data/scripts/post_init.sh
    ```    
    应提示：`No such file or directory`
5. 执行`reboot`重启网关，等待1分钟，如正常重新连接到telent，则为成功

## 安装 v0.3.0 或以上组件
按上面流程完成卸载旧版后，安装 v0.3.0 或以上组件时，正常再UI操作即可

## 启动故障
如你在卸载旧版后无法再连接到telnet，或其他原因导致无法联网（网关灯常亮），参考：[故障恢复](../faultsave/readme.md)