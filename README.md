# 杀戮尖塔 2 自动打牌 · 多人联机适配版

基于 [yuanzhe-xing102/astrbot_plugin_sts2_player](https://github.com/yuanzhe-xing102/astrbot_plugin_sts2_player) **v0.4.8** 的改进版，
修掉了原版在**双人联机**下的 7 个缺陷。单人局行为与原版一致。

> 让 AstrBot 通过游戏 mod 的本地 HTTP 接口读取引擎真值，用**规则机器人**（零 token）打牌与构筑，
> 也可选让 LLM 在关键界面决策。

## 与原版的区别

原版是**单人局**打磨出来的，一进双人联机就会卡死或误判。本版修复：

| # | 问题 | 原版表现 |
|---|---|---|
| D1 | 地图投票后 `RuleBot._map()` 返回 `None` | **整局停下**，发 `/sts2 自动` 只回一句「不知道地图该做什么」 |
| D2 | 瞬时过期快照被当硬错误 | 别人刚出完牌你就被 `409 invalid_action` 拒，累计 3 次停机 |
| D3 | 结束回合后误判为「敌方回合」 | 空转到超时 |
| D4 | `status=pending` 时转场没结束就继续 | 读到旧界面，动作白做 |
| D5 | 已投票仍重复投票 | 真机实测 **3.2 秒投了 9 次**同一票 |
| D6 | 地图等待被判为「状态卡住」 | 真机实测 **7.5 秒即停机** |
| D7 | 播报条件永远不成立 | `/sts2 自动 10` **全程零回复**（`report_every=15` 且 `steps=10`） |

另外启用了引擎自带的 `will_kill_player` 字段、补了药水槽满时的 `discard_potion` 处理。

完整技术细节与复现数据见 [SYNC.md](SYNC.md) 与 [_project/2026-11-18-多人适配.md](_project/2026-11-18-多人适配.md)。

## 安装

**重要：AstrBot 要求插件目录名是 `astrbot_plugin_*`。** clone 后必须改名：

```bash
git clone https://github.com/insolitude610/astrbot-sts2-coop.git astrbot_plugin_sts2_player
mv astrbot_plugin_sts2_player <ASTRBOT_ROOT>/data/plugins/
```

或直接下载 zip，解压后把文件夹改名为 `astrbot_plugin_sts2_player` 放进 `<ASTRBOT_ROOT>/data/plugins/`。

装完**重启 AstrBot**（插件不会自动热重载，除非设了 `ASTRBOT_RELOAD=1`）。

## 配置

`<ASTRBOT_ROOT>/data/config/astrbot_plugin_sts2_player_config.json`：

```json
{
  "sts2_url": "http://127.0.0.1:8082",
  "operator_ids": ["<你的 QQ openid>"],
  "max_steps": 20,
  "step_interval_sec": 0.3,
  "report_every": 15,
  "use_llm": false,
  "block_priority": 0.6,
  "auto_restart": false
}
```

> `sts2_url` 指向**队友实例**的端口。指向主窗口（8081）会去操作你自己的角色。
>
> `operator_ids` 从 AstrBot 日志里取：`default_xxx:FriendMessage:<openid>` 那段。

## 游戏侧准备

需要一个**离线的第二实例**当队友。不需要第二个 Steam 账号。

```powershell
$g = "<GAME_DIR>"   # 含 SlayTheSpire2.exe 那一层

# 1. 主窗口（你自己玩）
Start-Process "$g\SlayTheSpire2.exe" -ArgumentList '-fastmp','host_standard' -WorkingDirectory $g

# 2. 队友实例（等主窗口稳定 35 秒以上再拉，否则握手超时）
$env:STS2_MULTIPLAYER_HOST_IP = '127.0.0.1'
$env:STS2_MULTIPLAYER_NET_ID  = '3'        # 必须等于 --clientId
$env:STS2_API_PORT            = '8082'
$env:STS2_API_ALLOW_FALLBACK  = '1'
$env:STS2_AGENT_ROLE          = 'companion'
$env:STS2_AGENT_AUTOPLAY      = '0'        # 0 = 外部接管
$env:STS2_AGENT_SETTINGS_PATH = "$env:APPDATA\STS2AIAgent\settings.companion.json"
Start-Process "$g\SlayTheSpire2.exe" `
  -ArgumentList '--windowed','--force-steam','off','--clientId','3','-fastmp','join' `
  -WorkingDirectory $g
```

**新 clientId 首次启动必须补存档**（否则 mod 不加载、队友没有 API）：

```powershell
$p = "$env:APPDATA\SlayTheSpire2\default\<clientId>\settings.save"
# 先启动一次让它生成目录，立刻关掉游戏进程，再改：
#   "mod_settings": null  →  开启 STS2AIAgent
#   "seen_ea_disclaimer": false → true
#   "skip_intro_logo": false → true
```

游戏运行中改会被覆盖。详细踩坑清单见 [_project/2026-11-18-多人适配.md](_project/2026-11-18-多人适配.md)。

## 使用

在 QQ 私聊机器人：

| 指令 | 说明 |
|---|---|
| `/sts2 状态` | 当前局面快照 |
| `/sts2 自动 10` | 自动打 10 步（会逐步播报进度） |
| `/sts2 执行 end_turn` | 手动下一个动作 |
| `/sts2 停` | 停止 |
| `/sts2 帮助` | 动作速查 |

## 多人局须知

- **必须双方都结束回合**才会推进。队友结束后会显示「（已结束回合，等队友）」
- **地图需要双方都投票**。队友投完会提示「地图上已经投过票了，等你投票中」
- 两边界面可能不同步，属正常现象
- 双人局敌人血量约为单人的 2 倍

## 已知限制

- 规则层打不过第 1 幕 Boss 很正常，真机最好成绩第 15~17 层
- LLM 决策实测**不如**规则层（作者数据：规则层第 15~17 层 / 0 token，全交模型第 5 层 / 49.9k token）
- 只测过 `v0.113.1` + STS2-Agent `v0.19.2`

## 目录说明

| 路径 | 内容 |
|---|---|
| `main.py` | 插件本体（已打多人适配补丁） |
| `PLUGIN-README.md` | 上游原版插件说明，保留原文 |
| `tools/` `docs/` | 上游自带的开发工具与文档，未修改 |
| `SYNC.md` | 与上游的差异、同步/回滚方法 |
| `_project/` | 实测报告、验证脚手架、补丁文件 |

## 许可

MIT，见 [LICENSE](LICENSE)。

`plugin` 代码版权归原作者 **yuanzhe-xing102**，本仓库仅做多人适配修改。
完整来源与合规说明见 [NOTICE.md](NOTICE.md)。

本仓库不含任何游戏资产；Slay the Spire 2 版权归 Mega Crit，本项目与其无关联。
