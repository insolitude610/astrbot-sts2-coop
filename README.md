# 杀戮尖塔 2 × AstrBot 陪玩

让 AstrBot 通过游戏 mod 的本地 HTTP 接口，驱动一个**离线第二实例**当 AI 队友，和你一起爬塔。

> 不需要第二个 Steam 账号。用游戏自带的 FastMP 本地联机起一个 `--force-steam off` 的实例，
> 它就能以独立玩家身份进你的大厅，外部程序通过它自己的本地 API 出牌。

> [!IMPORTANT]
> **`plugin/` 里的插件是 [yuanzhe-xing102/astrbot_plugin_sts2_player](https://github.com/yuanzhe-xing102/astrbot_plugin_sts2_player) v0.4.8 的副本，
> 版权归原作者，采用 MIT 许可。** 本仓库只对 `plugin/main.py` 打了多人联机适配补丁，
> 其余文件未修改。完整来源说明见 [NOTICE.md](NOTICE.md)。
>
> 本仓库不含任何《杀戮尖塔 2》游戏资产；Slay the Spire 2 版权归 Mega Crit，本项目与其无关联。

## 文档

> 下文命令里的占位符，按你自己的环境替换：
>
> | 占位符 | 含义 |
> |---|---|
> | `<ASTRBOT_ROOT>` | AstrBot 安装目录（含 `venv/`、`data/` 那一层） |
> | `<repo>` | 本仓库在你机器上的路径 |
> | `<GAME_DIR>` | 游戏安装目录（含 `SlayTheSpire2.exe` 那一层） |

| 文件 | 内容 |
|---|---|
| [AstrBot-杀戮尖塔2-AI队友-设计方案.md](AstrBot-杀戮尖塔2-AI队友-设计方案.md) | 早期设计方案（走 AiTeammate mod 的 TCP 桥，**这条路线没走**） |
| [2026-11-17-实测交接.md](2026-11-17-实测交接.md) | 第一轮实测：跑通「第二实例进大厅并开局」 |
| [2026-11-18-多人适配.md](2026-11-18-多人适配.md) | 第二轮实测：多人局适配缺陷与修复（本目录代码对应这轮） |

## 核心结论（截至 2026-11-18）

1. **不需要第二个 Steam 账号** —— `--force-steam off` 的离线实例能进大厅
2. **companion 角色的 `/action` 可用** —— `play_phase: paused` 只是 mod 自走循环的状态，
   不影响外部驱动（这点第一轮没确认）
3. 插件 `astrbot_plugin_sts2_player` v0.4.8 是**单人局打磨出来的**，多人局有 5 个真实缺陷，
   已在 [patches/](patches/) 里修复

## 目录

| 路径 | 内容 |
|---|---|
| `plugin/` | **插件源码（本地修改版）**，与上游的差异见 [plugin/SYNC.md](plugin/SYNC.md) |
| `patches/` | 补丁文件，可对上游 v0.4.8 原版应用 |
| `harness/` | 验证脚手架（见下） |
| `*.md` | 设计稿、两轮实测报告 |

## 打补丁

[patches/sts2-player-v0.4.8-multiplayer.patch](patches/sts2-player-v0.4.8-multiplayer.patch)
是插件 v0.4.8 的多人适配修复（+217/−14）。原文件是**纯 LF**，Windows 上应用时必须关掉换行转换，
否则会得到 CRLF 版本（内容一样但字节不同）：

```powershell
cd <插件目录>          # 里面要有 astrbot_plugin_sts2_player/main.py
git -c core.autocrlf=false apply <repo>\patches\sts2-player-v0.4.8-multiplayer.patch
```

已验证：对 `main.py.bak-20261118-multiplayer` 应用后 SHA256 与线上版本完全一致。

## harness/ 是什么

在 AstrBot 进程之外，用插件**真实代码路径**直连游戏接口做验证的脚手架。
好处是不用重启 AstrBot、不碰 QQ 会话；代价是没有验证 AstrBot 集成链路（鉴权、`plain_result`、事件循环）。

| 脚本 | 用途 |
|---|---|
| `sts2stub.py` | AstrBot 最小桩：让插件 `main.py` 能在 AstrBot 外被 import |
| `sts2ctl.py` | 通用探针：`probe` / `raw-state` / `actions` / `act` / `play` / `lobby` |
| `selfcheck.py` | 适配层 / 规则层 / 渲染 / 重试判定，**29 项** |
| `map_fix_check.py` | 多人地图 6 个场景（含已投票不重投、别人投票不误判） |
| `map_wait_check.py` | 地图等待不被误判为「状态卡住」 |
| `detect_fix_check.py` | 后端识别缓存、404 自愈，**12 项** |
| `reply_check.py` | 自动打牌必有回复（开场 / 进度 / 收尾 / 等待提示），**9 项** |
| `retry_check.py` | 动作被拒后的退避重试（`--live` 走真游戏） |
| `retry_window.py` | 量化「过期快照」窗口：0s 必败 / 0.15s+ 基本成功 |
| `rule_check.py` | 看规则层对当前状态会做什么（不实际发动作） |
| `duo.py` | 双实例协同驱动（**会替你操作主窗口**，只用于验证） |
| `e2e.py` | 端到端：主机模拟真人 + 队友走插件 `_auto` |

`sts2_plugin_main.py` 是 `main.py` 的副本，供 harness import 用。改动插件后需重新拷贝：

```powershell
Copy-Item "<ASTRBOT_ROOT>\data\plugins\astrbot_plugin_sts2_player\main.py" `
          "harness\sts2_plugin_main.py" -Force
```

### 跑测试

```powershell
$v = "<ASTRBOT_ROOT>\venv\Scripts\python.exe"
cd harness
& $v selfcheck.py          # 离线，不需要游戏开着
& $v map_fix_check.py      # 离线
& $v retry_check.py        # 离线
```

## 起一局（人工）

```powershell
$g = "<GAME_DIR>"

# 1. 主窗口（你自己玩）
Start-Process "$g\SlayTheSpire2.exe" -ArgumentList '-fastmp','host_standard' -WorkingDirectory $g

# 2. 队友实例（环境变量一个都不能少）
$env:STS2_MULTIPLAYER_HOST_IP = '127.0.0.1'
$env:STS2_MULTIPLAYER_NET_ID  = '3'          # 必须等于 --clientId
$env:STS2_API_PORT            = '8082'
$env:STS2_API_ALLOW_FALLBACK  = '1'
$env:STS2_AGENT_ROLE          = 'companion'
$env:STS2_AGENT_AUTOPLAY      = '0'          # 0 = 外部接管
$env:STS2_AGENT_SETTINGS_PATH = "$env:APPDATA\STS2AIAgent\settings.companion.json"
Start-Process "$g\SlayTheSpire2.exe" `
  -ArgumentList '--windowed','--force-steam','off','--clientId','3','-fastmp','join' `
  -WorkingDirectory $g
```

**新 clientId 首次启动必须补两个东西**（否则 mod 不加载、队友没有 API）：

```powershell
$p = "$env:APPDATA\SlayTheSpire2\default\<clientId>\settings.save"
# 把 "mod_settings": null 换成开启 STS2AIAgent，并把 seen_ea_disclaimer 设为 true
# 改之前务必先关掉游戏进程，否则会被覆盖
```

完整避坑清单见 [2026-11-18-多人适配.md](2026-11-18-多人适配.md)。

## 已知未验证

- **AstrBot 集成链路一次都没跑过**：QQ 里发 `/sts2 状态` / `/sts2 自动` 到插件的完整路径，
  包括 `operator_ids` 鉴权、`plain_result` 回消息、插件在 AstrBot 事件循环里的表现
- **没有完整打通一整局**：每次都在第 1 幕被反复重启打断
- **LLM 决策路径未测**：所有测试都是 `use_llm=false` 的零 token 规则层
