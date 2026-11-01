# iOS 9 keybagd 自动匹配与实机验证

原项目的 mount 脚本仅接受列出的主板/构建号，补丁器内部再按源文件摘要匹配。
本 fork 已取消脚本中的逐个主板/构建白名单，改为核对 ramdisk 标记和已安装系统
构建一致，再由签名补丁器根据实际 keybagd 的完整 SHA-256 自动选择已审核记录。
仅因文件大小相同或 iOS 版本号相近，不会套用另一套偏移。

## 本次 9.3.2 / n66map / 13F69

实机只读挂载 System 并取得匹配样本，经静态控制流、导入符号和字符串交叉引用
核对后，按照原项目 9.3.1 的方法适配，保持 release kernel，未增加内核补丁。

- 源文件：308240 字节，22 处 `/private/var` 路径
- 源 SHA-256：`06a5777ac137435a05103e9fc36ceab7f9e2364bd09451db353c0cfa007302c9`
- 输出 SHA-256：`bd4724c8d1b3cf34771749269ea3602c13f0511ab77da8b9c4974558093e50af`
- 5 处指令修改：关闭 fatal handler 的 NVRAM 写入与 reboot；强制加载 Data
  systembag；在原成功退出点结束 init，避开 earlyboot / 用户会话设置。

2026-11-01 的实机会话已验证：输出 `System Keybag loaded`，launchd 出现服务 PID，
`./qwqramdisk mount` 的 systembag 读取和 Data 写入/读回/删除通过。
新打包镜像的整套冷启动仍待回归；本次不是一次新的 AMFI 绕过。

```sh
./qwqramdisk create 9.3.2 --profile n66m-13F69 --offline
python3 -m tools.verify_ios9 --profile n66m-13F69
./qwqramdisk boot 9.3.2 --profile n66m-13F69
./qwqramdisk mount
```

首次 create 会下载所需组件；缓存完整后可加 --no-download。boot 需要连接对应设备并进入 DFU。

## 自动匹配的范围

记录在 `ramdisk/keybagd-profiles.json`，当前包括 13A405（也匹配 13A452）、13B143、13D15、13E238、13F69
的精确样本。构建号是说明标签，运行时按完整文件摘要匹配，因此同一二进制可供
不同主板或构建复用。9.2.1、9.3.1 的指令表和输出摘要保持不变。
13A405 / 13A452 共享样本已增加 2 处成功日志修正，保留原来的 4 处装载/退出补丁。

`patch-keybagd-ios9 --check SOURCE` 只在内存中验证源摘要、每处原指令、路径数量
和结果摘要，不写文件。mount 在加载 SEP、挂载 Data 前执行它；未知样本明确报错。
所有 iOS 9 新建镜像都会安装同一组签名且兼容 iOS 9 的常用工具和传输组件。

## 遇到新的二进制

对 iOS 9.3 系列形态，宿主机可自动发现候选位置：

```sh
python3 -m tools.keybagd_patterns keybagd --build 13F69 --report keybagd.analysis.json
```

分析器核对 Mach-O 导入符号、fatal NVRAM 两次调用的同一目标、reboot/exit，
以及 systembag 分支与 earlyboot/成功退出的关系。零个或多个匹配、控制流改变、
导入符号缺失都会拒绝分析。该分析器不覆盖所有 iOS 9 布局，不自动把未知哈希
加入信任清单，也不修改设备文件。

候选经审核后才能加入注册表；实机验证状态单独记录。修改记录或 C 源码后运行：

```sh
python3 -m tools.prepare_ios9_helpers
```

这会校验注册表、生成 C 头文件、编译并预签名。create 继续只打包预制资源，
Linux 离线构建无需签名工具。旧入口 `tools.verify_ios921` 仍可使用。

## MobileGestalt 缓存修改命令

在 Mac 的项目目录执行 `./qwqramdisk patch-activation`，通过已启动的 ramdisk
读取 `/mnt2/mobile/Library/Caches/com.apple.MobileGestalt.plist`，将
`CacheExtra` 字典里的 `a6vjpkzcrjrsxmnifsm0dg` 设为真正的布尔值 true。
保留其他字段及原 XML/二进制格式；先验证上传的临时文件，再备份原文件、写回，
最后重新读取验证内容与权限/属主。命令输出原文件的设备端备份路径。

此命令已通过离线内容与模拟写回流程测试，尚未在真实 MobileGestalt 缓存上执行。
该修改在 Mac 端生效，无需重建 ramdisk。

## 9.0.2 / 9.1，iPhone 6s n71map

9.0.2 / 13A452 已确认从 DFU 启动到 SSH，keybagd 与 13A405 的完整摘要相同。
初版成功日志输出异常；增加与 13D15 同类的两处日志修正后，返回的诊断日志确认
`System Keybag loaded`、launchd 服务 PID、systembag 读取及 Data 写入/读回/删除通过。
两处修正只作用于 kb_set 成功分支，保留反序列化及 kb_set 的失败检查。
最后六处补丁打包镜像的完整冷启动仍待单独回归。

9.1 / 13B143 的诊断包确认 n71map 启动到 SSH、只读 System 挂载成功。
其 keybagd 的代码、字符串、导入和数据段与已审核的早期样本相同，
但完整文件摘要不同，因此独立登记 13B143，仍使用相同六处指令修改和九处路径重定位。
用户确认后续完整挂载测试包正常；原始挂载日志尚未另行归档，状态标为
`device-reported-ssh-rw`，与已审阅日志的实测记录分开。

```sh
./qwqramdisk create 9.0.2 --profile n71m-13A452 --offline
./qwqramdisk boot 9.0.2 --profile n71m-13A452
# 或使用已安装 9.1 的同主板设备：
./qwqramdisk create 9.1 --profile n71m-13B143 --offline
./qwqramdisk boot 9.1 --profile n71m-13B143
./qwqramdisk mount
```

更新项目后需要重新 create 才能把新补丁器装入 ramdisk；旧输出镜像不会自动更新。
旧 Apple 固件的 HTTP 下载地址改为同一站点的 HTTPS，组件校验保持不变。

## 9.3.5 反馈与其他版本

用户报告当前桌面版本在 9.3.5 也成功，未新增专用补丁。
该反馈尚未提供主板和对应日志，不据此将所有 9.3.5 profile 标为已验证。
9.3.3、9.3.4 仍待实测；其他型号需使用对应主板镜像，运行时继续精确核对 keybagd。
