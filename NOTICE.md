# 来源与合规声明

本仓库的插件代码**来自他人项目**，不是原创。以下是明确说明。

## 主体代码：astrbot_plugin_sts2_player

| 项 | 值 |
|---|---|
| 原作者 | **yuanzhe-xing102** |
| 上游仓库 | https://github.com/yuanzhe-xing102/astrbot_plugin_sts2_player |
| 版本 | v0.4.8（上游最后一版，2026-11-08） |
| 声明许可 | MIT（见 `PLUGIN-README.md` 的「许可」一节） |
| 上游 LICENSE 文件 | **不存在**（仓库根目录没有 LICENSE，源文件也没有版权行） |

### 本仓库对其做了什么

**只修改了 `main.py`**，加入多人联机适配补丁。改动清单见 [SYNC.md](SYNC.md)，
完整 diff 见 [_project/patches/sts2-player-v0.4.8-multiplayer.patch](_project/patches/sts2-player-v0.4.8-multiplayer.patch)。

以下文件与上游 v0.4.8 **完全一致，未作任何修改**：

- `metadata.yaml`（`author` / `repo` 字段保持原作者信息）
- `_conf_schema.json`
- `PLUGIN-README.md`（原 `README.md`，为避免与本仓库 README 冲突而改名）
- `docs/DEV.md`
- `tools/` 下全部 16 个脚本
- `logo.png`

### 上游未提供 LICENSE 文件的情况

上游声称 MIT，但仓库根目录没有 LICENSE 文件，源文件里也没有版权声明行。
按 MIT 的要求本应保留版权声明，本仓库因此：

- 保留完整原作者与来源信息（本文件）
- 保留 `metadata.yaml` 里的 `author` / `repo` / `social_link` 原样
- 保留上游 README 原文
- 在 `main.py` 里新增的代码处标注了修改原因

若原作者认为本仓库的收录方式不妥，请提 issue，会立即移除相关代码。

## 游戏侧依赖（本仓库不含其代码）

| 项目 | 用途 |
|---|---|
| [STS2-Agent](https://github.com/CharTyr/STS2-Agent) | 游戏 mod，提供本地 HTTP 接口 |
| [AstrBot](https://github.com/AstrBotDevs/AstrBot) | 机器人框架 |

## 原创部分

以下内容为本仓库原创，采用与 [LICENSE](LICENSE) 相同的 MIT 条款：

- `README.md`、`NOTICE.md`、`SYNC.md`
- `_project/` 下的实测报告与 `harness/` 验证脚本
- `main.py` 中的多人适配补丁

## 游戏资产

本仓库**不含**任何《杀戮尖塔 2》的游戏资产（贴图、音频、DLL、PCK 等）。
通过 mod 读取的是运行时状态数据，不涉及资产分发。

Slay the Spire 2 版权归 Mega Crit 所有，本项目与其无关联。
