# 第三方代码与来源声明

本仓库包含**他人项目**的副本，不是本仓库原创。以下是逐一说明。

## plugin/ —— astrbot_plugin_sts2_player

| 项 | 值 |
|---|---|
| 原作者 | **yuanzhe-xing102** |
| 上游仓库 | https://github.com/yuanzhe-xing102/astrbot_plugin_sts2_player |
| 版本 | v0.4.8 |
| 声明许可 | MIT（见上游 README「许可」一节；上游仓库根目录**未提供** LICENSE 文件） |

### 本仓库对其做了什么

`plugin/main.py` 打了多人联机适配补丁，具体改动见
[patches/sts2-player-v0.4.8-multiplayer.patch](../patches/sts2-player-v0.4.8-multiplayer.patch)
和 [plugin/SYNC.md](../plugin/SYNC.md)。

`plugin/` 下的其余文件（`metadata.yaml`、`_conf_schema.json`、`README.md`、
`docs/`、`tools/`、`logo.png`）与上游 v0.4.8 **完全一致，未作修改**。

### 上游许可的注意事项

上游声称 MIT 但根目录没有 LICENSE 文件，也没有在源文件里标注版权行。
按 MIT 要求应保留版权声明，本仓库因此：

- 保留完整的原作者与来源信息（本文件）
- 保留上游 `metadata.yaml` 里的 `author` / `repo` 字段原样
- 保留上游 `README.md` 原文（含「许可」一节）

若原作者认为本仓库的收录方式不妥，请提 issue，会立即移除。

## 游戏侧依赖（本仓库不含其代码）

| 项目 | 用途 |
|---|---|
| [STS2-Agent](https://github.com/CharTyr/STS2-Agent) | 游戏 mod，提供本地 HTTP 接口 |
| [AstrBot](https://github.com/AstrBotDevs/AstrBot) | 机器人框架 |

## 文档与 harness/

`README.md`、`*.md` 实测文档、`harness/` 下的验证脚本均为本仓库原创，
采用与 [LICENSE](../LICENSE) 相同的 MIT 条款。

## 游戏资产

本仓库**不含**任何《杀戮尖塔 2》的游戏资产（贴图、音频、DLL、PCK 等）。
通过 mod 读取的是运行时状态数据，不涉及资产分发。

Slay the Spire 2 版权归 Mega Crit 所有，本项目与其无关联。
