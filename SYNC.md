# 与上游的差异

上游：https://github.com/yuanzhe-xing102/astrbot_plugin_sts2_player
版本：**v0.4.8**（上游最后一版，2026-11-08）

## 改了什么

**只有 `main.py` 改过。** 其余文件与上游 v0.4.8 完全一致：

`metadata.yaml` · `_conf_schema.json` · `PLUGIN-README.md` · `docs/DEV.md` ·
`tools/` 全部 16 个脚本 · `logo.png`

完整 diff：[_project/patches/sts2-player-v0.4.8-multiplayer.patch](_project/patches/sts2-player-v0.4.8-multiplayer.patch)

全部改动都是**多人联机适配**，单人局行为不受影响：

| # | 缺陷 | 原版表现 | 严重度 |
|---|---|---|---|
| D1 | 多人地图投票后 `RuleBot._map()` 返回 `None` | 整局停下 | 致命 |
| D2 | 瞬时过期快照（409 `invalid_action`）被当硬错误 | 累计 3 次停机 | 高 |
| D3 | 结束回合后被误判为「敌方回合」 | 空转到超时 | 中 |
| D4 | `status=pending` 转场未完成就当成已完成 | 读到旧界面 | 中 |
| D5 | 事件选项未使用引擎的 `will_kill_player` | 一路扣到 1/1 HP | 中 |
| D6 | 已投票仍重复投票（动作不会从 available_actions 消失） | 3.2 秒投 9 次 | 高 |
| D7 | 地图等待被误判为「状态卡住」 | 7.5 秒即停机 | 高 |
| D8 | 播报条件 `i % report_every == 0 or i == steps` 永远不成立 | 全程零回复 | 中 |

附带：消费 `discard_potion`（药水槽满时防死循环）、渲染队友 HP / 倒地状态、
后端识别失败不再永久缓存（原来「先开 AstrBot 后开游戏」会永久锁在 MCP 分支 → 404）。

实测数据与复现方法见 [_project/2026-11-18-多人适配.md](_project/2026-11-18-多人适配.md)。

## 为什么上游没修

上游仓库截至 2026-11-18：**0 issue / 0 PR / 0 fork / 0 star**，v0.4.8 下载量 4 次。
作者最后提交 2026-11-08，全部针对单人局（提交信息提到「真机第14层」「营火选项容错」
「商店跳过买不起的货」），从没涉及多人联机。

这些缺陷**不是已知问题，是首次暴露**。

## 同步与回滚

本仓库根目录就是插件本体。部署：

```powershell
$dst = "<ASTRBOT_ROOT>\data\plugins\astrbot_plugin_sts2_player"

# 部署前备份
Copy-Item "$dst\main.py" "$dst\main.py.bak-$(Get-Date -Format yyyyMMdd)"

# 同步（/MIR 会删除目标多余文件，注意别带上 _project、.git）
robocopy . $dst /MIR /XD .git _project /XF *.bak-*
```

**AstrBot 不会自动重载插件**（需 `ASTRBOT_RELOAD=1` 或重启 AstrBot）。

回滚到上游原版：见 [NOTICE.md](NOTICE.md) 里的上游地址，重新下载 v0.4.8 覆盖即可。

## 上游更新怎么办

1. 先对比新版是否已修这些多人问题（大概率没有）
2. 有冲突就手工合并，**别直接打补丁**（行号会漂）
3. 重新跑 `_project/harness/` 下的全部测试确认没退化
