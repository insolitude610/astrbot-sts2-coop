# 插件源码（本地修改版）

上游：https://github.com/yuanzhe-xing102/astrbot_plugin_sts2_player
版本：**v0.4.8**（上游最后一版，2026-11-08）

## 与上游的差异

**只有 `main.py` 改过**，其余文件（`metadata.yaml`、`_conf_schema.json`、`README.md`、
`docs/`、`tools/`、`logo.png`）与上游 v0.4.8 完全一致。

改动内容 = [../patches/sts2-player-v0.4.8-multiplayer.patch](../patches/sts2-player-v0.4.8-multiplayer.patch)
（+217/−14），全部是**多人联机适配**，单人局行为不受影响：

| # | 缺陷 | 严重度 |
|---|---|---|
| D1 | 多人地图投票后 `RuleBot._map()` 返回 `None` → 整局停下 | 致命 |
| D2 | 瞬时过期快照（409 `invalid_action`）被当硬错误，累计 3 次停机 | 高 |
| D3 | 结束回合后被误判为「敌方回合」，空转到超时 | 中 |
| D4 | `status=pending` 转场未完成就当成已完成 | 中 |
| D5 | 事件选项未使用引擎的 `will_kill_player`，一路扣到 1/1 HP | 中 |

附带：消费 `discard_potion`（药水槽满时防死循环）、渲染队友 HP/倒地状态。

详见 [../2026-11-18-多人适配.md](../2026-11-18-多人适配.md)。

## 为什么上游没修

上游仓库截至 2026-11-18：**0 issue / 0 PR / 0 fork / 0 star**，v0.4.8 下载量 4 次。
作者最后提交是 2026-11-08，全部提交都针对单人局（提交信息提到「真机第14层」
「营火选项容错」「商店跳过买不起的货」），从没涉及多人联机。

也就是说这些缺陷**不是已知问题，是首次暴露**。

## 同步与回滚

从线上同步（改完线上后）：

```powershell
$src = "<ASTRBOT_ROOT>\data\plugins\astrbot_plugin_sts2_player"
robocopy $src plugin /MIR /XD __pycache__ /XF *.bak-*
```

部署到线上前，建议先备份：

```powershell
$dst = "<ASTRBOT_ROOT>\data\plugins\astrbot_plugin_sts2_player"
Copy-Item "$dst\main.py" "$dst\main.py.bak-$(Get-Date -Format yyyyMMdd)"
Copy-Item "plugin\main.py" "$dst\main.py" -Force
```

**注意**：AstrBot 不会自动重载插件（需 `ASTRBOT_RELOAD=1` 或重启）。

## 上游更新怎么办

如果上游发了新版：

1. 先对比新版是否已修这些多人问题（大概率没有）
2. 有冲突就用手工合并，别直接打补丁
3. 重新跑 `../harness/selfcheck.py` 确认没退化
