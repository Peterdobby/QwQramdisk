# iPhone 6s Plus / iOS 9.2.1

本 fork 增加 13D15 的 keybagd 补丁、签名兼容工具、文件传输及激活备份修复。
台积电 A9 的 n66map 已在运行中的 ramdisk 会话实测 SSH、systembag 读取、
Data 写入/读回/删除及文件传输；最终打包镜像的完整冷启动仍待回归。

| 主板 | 芯片 | profile | 验证范围 |
|---|---|---|---|
| n66map | 台积电 A9，0x8003 | n66m-13D15 | 真机会话与离线镜像 |
| n66ap | 三星 A9，0x8000 | n66-13D15 | 离线镜像 |

13D15 与 13D20 都叫 9.2.1，必须按实际安装的构建号选择。
13D20 没有在本次验证；DFU 查询能确认主板，不能确认已安装构建号。

## 构建与使用

在克隆的项目目录执行。首次构建会下载所需固件组件，不需要完整 IPSW：

```sh
./qwqramdisk doctor
./qwqramdisk create 9.2.1 --profile n66m-13D15 --offline
python3 -m tools.verify_ios9 --profile n66m-13D15
```

三星 A9 使用 n66-13D15。缓存准备完整后可给 create 加 `--no-download`。
离线检查覆盖固件身份/摘要、IMG4 载荷及镜像内注入文件，不等于真机启动通过。
设备连接并进入 DFU 后：

```sh
./qwqramdisk boot 9.2.1 --profile n66m-13D15
./qwqramdisk mount
./qwqramdisk ssh
```

SSH 地址为 root@localhost:2236，密码 alpine。mount 会写入 Data 中的临时探针，
只有读取 systembag 和写入/读回/删除都通过才报告可用。

## 补丁与工具

- System 只读挂载失败时，重试 `mount_hfs -j -o rdonly`，保留 Data 的日志模式。
- 参考上游 [018b3cacab01](https://github.com/j1ans/QwQramdisk/commit/018b3cacab01)
  恢复预先 ad-hoc 签名的补丁器；create 不在运行时编译或签名。
- 13D15 沿用 9.0.1 的 4 处 systembag/安全退出修改，另外修正 2 处成功日志输出。
  在 kb_set 成功路径将现有 C 字符串交给 puts，保持原来的错误检查。
- find、grep、chmod、cp、chown、sleep、scp 和 sftp-server 补签；ls 从 Apple/BSD
  旧版源码编译为 arm64 / iOS 9，避免原版本的 clock_gettime 依赖。
- `/bin/mount` 转到原生 `/sbin/mount`，兼容 Dropbear 的默认 PATH。

输入 SHA-256：`39b981a0641cb68771df8b3ef65e271c67cd27756720fb890831d3ee8d993a55`。
输出 SHA-256：`8f02a3166f920e383c3a68581aa59662aee31a56a48b46c446d9022853927425`。
按完整摘要匹配；未知文件不会因版本相近而套用偏移。

修改 C 源码或注册表后，在 macOS/Xcode 上运行：

```sh
python3 -m tools.prepare_ios9_helpers
shasum -a 256 -c ramdisk/SHA256SUMS
```

## 激活备份与恢复

```sh
./qwqramdisk dump-activation
./qwqramdisk restore-activation BACKUP.tar
```

9.2.1 优先读取 `/mnt2/mobile/Library/mad`，目录遍历失败会保留实际错误。
附加的 `com.apple.commcenter.device_specific_nobackup.plist` 在存在时收录到
`Extras/wireless/Library/Preferences/`，恢复时写回原无线配置路径，先备份现有文件，
再核对大小、权限与属主。旧归档没有该文件时不会改动它。

dump 已在真机验证。restore 的完整写回、备份、权限及属主验证使用隔离的
设备临时目录完成；没有用测试数据覆盖真实激活/无线配置。

[验证状态表](docs/validation/ios9.md) · [9.3.2 与自动匹配](README-IOS9-AUTO.md)
