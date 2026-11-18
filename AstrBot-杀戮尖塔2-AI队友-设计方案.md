# AstrBot × 杀戮尖塔 2：AI 队友「陪玩」设计方案

> 状态：设计稿 v0.1，**未开始编码**
> 日期：2026-11-17
> 环境前提：Windows 本机、Steam 版游戏 `v0.113.1`、AstrBot 4.x 原生部署（非 Docker）、AiTeammate Mod
> 目标读者：后续实现者（我）/ 想评估可行性的你

---

## 0. 一句话方案

在 AstrBot 里写一个 **Star 插件**，用 TCP 行 JSON 直连游戏内 **AiTeammate Mod** 的本地桥（`127.0.0.1:26333`），让 AstrBot 的模型成为**游戏内 AI 队友的大脑**：

- 群聊 / 私聊里随时能和它说话，它也会在游戏聊天面板里回话；
- 没人说话时，它自己按 `sts2_wait → 决策 → sts2_decide` 的循环把整局打完；
- 决策与聊天共用 AstrBot 的人格、记忆与模型配置。

不改游戏代码、不需要 DSH、不需要 MCP、不需要另开模型后端。

---

## 1. 需求拆解

| 编号 | 需求 | 本方案的满足方式 |
|---|---|---|
| R1 | AstrBot 跑在本机 Windows，游戏也在本机 | 桥只监听 `127.0.0.1`，天然同机 |
| R2 | 群聊或私聊里大家能和 AI 队友对话 | AstrBot 原生消息管线 + 插件注入局面 + 回写游戏聊天面板 |
| R3 | 不对话时 AI 队友也能自己玩 | 插件内常驻 `PlayLoop`，与消息事件解耦 |
| R4 | 不抢玩家操作、可随时收回控制权 | 只走 `ai_decision`（AI 自己的决策），不碰玩家 UI；`/sts2 stop` + 游戏内开关双保险 |
| R5 | 可控成本与风险 | 单局请求上限、决策超时、只读模式、断开重连 |

---

## 2. 可行性结论（为什么这条路成立）

### 2.1 游戏侧：AiTeammate 已经把「大脑接口」留好了

- 它是**多版本 bundle**（加载器 + `lib/<游戏版本>/AiTeammate.Content.dll`），仓库 2026-11-13 已提交 `0.113.0` 适配；
- 设置页有「外部 Agent（dsh）」分区：`EnableAgentBridge`、`AgentBridgePort`（默认 `26333`）、`AgentBridgeToken`、`AgentBridgeAllowActions`、`AgentChatToDsh`、`AgentChatReplyTimeoutSeconds`（默认 120s）、`AgentChatFallbackToBackend`；
- 桥协议是**极简 TCP + UTF-8 行分隔 JSON**，与具体客户端无关（dsh-sts2 只是其中一个客户端）；
- 外部大脑模式下，AI 队友的决策会挂起为 `phase=ai_decision`，把 `decision.prompt` / `decision.options` 交出来，客户端回 `sts2_decide` 即可，**执行、同步、校验、兜底全部由 Mod 负责**——插件不需要自己出牌。

### 2.2 AstrBot 侧：需要的能力都是公开 API

| 能力 | AstrBot API | 用途 |
|---|---|---|
| 插件生命周期 | `Star` 子类、`__init__`、`terminate()` | 启动/关闭 TCP 与后台任务 |
| 后台常驻任务 | `asyncio.create_task()`（官方示例） | `PlayLoop`、心跳、重连 |
| 调模型（不经过消息管线） | `provider.text_chat(prompt=..., system_prompt=..., context=...)` | 每次决策单发请求 |
| 获取模型 | `context.get_using_provider_async(umo=...)` / `get_provider_by_id()` | 决策与聊天用同一模型 |
| 主动发消息 | `context.send_message(umo, MessageChain)` | 播报、开场白、私聊/群聊推送 |
| 注入局面到聊天 | `@filter.on_llm_request` + `req.extra_user_content_parts`（可 `.mark_as_temp()`） | 让聊天回复知道当前对局 |
| 镜像回复到游戏 | `@filter.on_llm_response` | 把 bot 的话写进游戏聊天面板 |
| 配置界面 | `_conf_schema.json`（`_special: select_provider / select_persona`） | WebUI 里选模型、人格、端口、token |
| 打包 | `metadata.yaml`（`astrbot_version`、`support_platforms`）、`requirements.txt` | 发布/加载 |

### 2.3 结论

**可行，且不需要改 Mod。** 唯一硬约束是：AstrBot 必须和游戏在同一台机器上（桥只绑回环地址）。

---

## 3. 总体架构

```
┌───────────────────────────── Windows 本机 ─────────────────────────────┐
│                                                                        │
│  QQ 群 / 私聊                                                          │
│      │  消息                                   ▲ 主动播报 / 回复        │
│      ▼                                        │                        │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ AstrBot Core（消息管线 / 人格 / 记忆 / 模型提供商 / TTS）      │      │
│  └───────────────▲──────────────────────────────┬───────────────┘      │
│                  │ on_llm_request 注入局面       │ on_llm_response 镜像  │
│                  │ （临时上下文，不进历史）       │ 到游戏聊天面板        │
│  ┌───────────────┴──────────────────────────────▼───────────────┐      │
│  │ astrbot_plugin_sts2_teammate（Star 插件）                     │      │
│  │  ├─ BridgeClient：asyncio TCP，行 JSON，26333，token          │      │
│  │  ├─ PlayLoop：sts2_wait → 决策 → sts2_decide（无人说话也跑）  │      │
│  │  ├─ Takeover：sts2_takeover 轮询，认领“AI 队友入局”邀请       │      │
│  │  ├─ ChatBridge：群/私聊 ↔ 游戏聊天面板（chat_poll/chat_send）│      │
│  │  ├─ Heartbeat：决策期间定时 sts2_state，防“静默回退”          │      │
│  │  └─ Notes：本局构筑方向 / Boss 对策，注入决策提示词            │      │
│  └───────────────────────┬──────────────────────────────────────┘      │
│                          │ 127.0.0.1:26333                             │
│  ┌───────────────────────▼──────────────────────────────────────┐      │
│  │ 杀戮尖塔 2 + AiTeammate Mod                                   │      │
│  │  ├─ AI 队友（独立角色 / 投票 / 出牌 / 聊天）                   │      │
│  │  ├─ AgentDecisionBroker：挂起 ai_decision，等 sts2_decide      │      │
│  │  ├─ AgentChatRelay：chat.pending / seq，等 sts2_chat_send      │      │
│  │  └─ 执行器 / 联机同步 / 超时兜底（自带回退到内置后端）          │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

**职责边界**

- 插件只负责「读局面、要决策、回决策、收发聊天、播报」；
- 所有游戏动作、合法性校验、联机同步、失败兜底都在 Mod 内；
- AstrBot 只负责「模型、人格、记忆、消息平台」。

---

## 4. 关键设计决策

### D1：决策不走 AstrBot 的消息管线，直接 `provider.text_chat` 单发 JSON

**为什么**：`@filter.command` / `tool_loop_agent` 都绑定一条用户消息事件；AI 队友每回合都要决策，不可能靠玩家每次发话触发。而决策所需信息（`decision.prompt`、`decision.options`、实时 `combat` 段）Mod 已经整理好了，单发一次 chat 请求、让它返回 JSON 即可。

- 输入：`decision.prompt`（Mod 自带，含输出格式要求）+ 紧凑局面 + 最近队友发言 + 本局笔记；
- 输出：`sts2_decide {decision: <JSON>}`；
- 不进 AstrBot 对话历史，不污染聊天上下文，token 可控；
- 解析失败重试 1 次；连续失败则停止心跳、让 Mod 按 60–300s 预算回退到内置后端，并在会话里说明「我这回合卡住了」。

> 备选升级（非 v1）：需要查牌堆/百科时，用 `func_tool=ToolSet([...])` 走 `text_chat` 的工具调用，或对单次决策用 `tool_loop_agent`。

### D2：聊天走 AstrBot 原生管线，插件只做「注入 + 镜像」

**为什么**：群聊/私聊的多轮对话、人格、记忆、图片/语音、@、引用，AstrBot 已经做得很好，重写没有意义。

- `on_llm_request`：把「当前对局摘要 + 你是 AI 队友 + 游戏内聊天待回复」作为 **临时** 用户内容块注入（`.mark_as_temp()`），不写进历史；
- `on_llm_response`：如果本局在进行且开启了镜像，把回复用 `sts2_chat_send` 写进游戏聊天面板；
- 游戏内玩家发言：`sts2_chat_poll` 长轮询拿到 `{seq, from, text}`，作为 `[游戏内聊天]` 注入下一轮聊天/决策上下文，并用 `reply_to` 回复；
- **回声抑制**：自己写到游戏面板的文本记入 `sent_hashes`，`chat_poll` 读到同文时不再反向注入，避免「游戏→QQ→游戏」循环。

### D3：自主游玩是独立循环，不依赖消息

`PlayLoop` 在认领对局后启动：

```
while run_active and autoplay:
    snap = sts2_wait(after_token=last_token, timeout_seconds=25)
    if snap.phase == "ai_decision":
        answer = decide(snap)          # text_chat + JSON
        sts2_decide(answer)
    elif snap.phase == "ai_busy":
        continue
    elif snap.phase == "game_over":
        break
    last_token = snap.token
```

- 没人在群里说话时照常跑；
- 有人说话时，消息进入 `directives` 队列（最近 5 条），拼进下一次决策提示词——「先打左边」「留着药水」这类话会实际生效；
- 玩家随时可以 `/sts2 pause` 或关游戏内开关。

### D4：只接 `ai_decision`，不做 UI 代打

`controlled.kind=ai` 时，Mod 会拒绝 `sts2_play_card` 等 UI 动作（避免和内置执行器抢同一个玩家），只接受 `sts2_decide`。这正好：

- 插件不需要理解手牌索引、目标选择、动画时序；
- 不会和玩家自己的操作打架；
- 单人「AI 独自爬塔」与多人「AI 队友」共用一套决策路径。

> 未来若想做「AstrBot 代打玩家本人」，那是另一套（`controlled.kind=local` + UI 动作），本方案不做。

### D5：心跳防「静默回退」

Mod 的判定是：桥连着但 `ClientIdleSeconds` 超过 `AgentFallbackSeconds`（默认 30s）就把决策交回内置后端。一次 LLM 决策可能 5–20s，长思考模型可能更久。

- 决策期间每 `heartbeat_seconds`（默认 10s）发一次 `sts2_state` 续命；
- `sts2_chat_poll` / `sts2_chat_send` / `sts2_takeover` **不计入**活动，别拿它们当心跳；
- 若模型持续超时，就主动放弃（停止心跳），让 Mod 用自己的兜底，别把整局卡死。

### D6：单驱动锁 + 只读开关 + token

- 插件内全局 `asyncio.Lock`：同一时刻只有一个决策在跑；
- `allow_actions` 默认 `false`：只读局面、只聊天，不回答决策（想先围观的人可以用）；
- 桥 token 与 Mod 设置一致；只连 `127.0.0.1`；
- 游戏断开/重开：指数退避重连，`terminate()` 取消所有任务。

### D7：会话绑定（群聊 + 私聊）

- 配置项 `home_session`：填一个 `unified_msg_origin`（群或私聊），插件把开场白、播报、游戏内聊天镜像都发到那里；
- 没填时，谁先发 `/sts2 play` 就绑定谁，后续可用 `/sts2 bind` 改绑；
- 其他会话仍可正常和 bot 聊天（AstrBot 原生），但不接收播报；
- 播报节流：战斗开始/结束、精英/Boss、死亡/通关，每类每次对局最多一条，避免刷屏。

---

## 5. 协议映射（插件会用到的调用）

| 调用 | 参数 | 用途 | 备注 |
|---|---|---|---|
| `sts2_hello` | `{}` | 连接自检 | 返回 `name/bridge_version/game_version/allow_actions/port` |
| `sts2_state` | `{detail?}` | 读快照 | `detail=delta` 只回变化字段；也当心跳 |
| `sts2_wait` | `{after_token?, timeout_seconds?}` | 等可行动 | 主循环；默认 25s，最大 50s |
| `sts2_read` | `{subject, ...}` | 深读牌堆/遗物/地图/单卡 | 可选，决策需要时用 |
| `sts2_decide` | `{decision: <JSON>}` | 回答 `ai_decision` | 形状由 `decision.answer_with` / `prompt` 指定 |
| `sts2_chat_poll` | `{after_seq?, wait_seconds?}` | 长轮询玩家发言 | 不计入活动打点 |
| `sts2_chat_send` | `{text, reply_to?, directives?, nickname?}` | 在游戏聊天面板说话 | `reply_to` 必须是仍待回复的 seq |
| `sts2_takeover` | `{}` | 认领「AI 队友入局」邀请 | 返回 `{take, run_token, prompt, workspace, host, port, character}` 或 `{take:false, reason}` |
| `sts2_note` | `{text}` | 记录本局笔记 | 按种子保存，后续决策提示词会带上 |
| `sts2_pause` / `sts2_resume` | `{}` | 暂停/继续 | 可选 |
| `sts2_autoplay` | `{enabled}` | dsh 插件专用 | AstrBot 版不需要，用自己的 PlayLoop |

**快照关键字段**（用于决策提示词与状态判断）：

```json
{
  "schema": 1,
  "token": "9f2c1a7b",
  "phase": "ai_decision",
  "actionable": true,
  "blocked_by": "",
  "mode": "Multiplayer",
  "run": {"act":1,"floor":6,"character":"Ironclad","hp":61,"max_hp":80,"gold":142,"deck_size":16,"relics":[],"potions":[]},
  "combat": {"round":3,"player":{"hp":61,"block":5,"energy":3,"stars":0,"powers":[]},"hand":[],"enemies":[],"piles":{"draw":12,"discard":3,"exhaust":0}},
  "decision": {"id":"...","kind":"combat","prompt":"...","system_prompt":"...","answer_with":"..."},
  "options": [],
  "notes": ["..."],
  "last_action": {"tool":"sts2_decide","ok":true,"detail":"..."}
}
```

> `phase` 还可能出现：`menu / char_select / daily_lobby / custom_lobby / combat / map / rewards / card_reward / card_select / card_choice / bundle_select / crystal_sphere / relic_select / shop / rest / target_select / event / treasure / room_proceed / game_over / paused / ai_busy / idle / unsupported`。v1 只处理 `ai_decision / ai_busy / game_over`，其余交给 Mod 的内置 AI（因为 AI 队友模式下这些流程本来就由 Mod 决策）。

---

## 6. 运行流程

### 6.1 启动与连接

1. AstrBot 启动 → 插件 `__init__` 创建 `BridgeClient`（懒连接 + 1.5s 首探）；
2. `sts2_hello` 成功 → 状态 `READY`，`/sts2 status` 返回版本、端口、是否允许动作；
3. 游戏没开/桥没开 → 保持 `DISCONNECTED`，指数退避，不影响 AstrBot 其他功能。

### 6.2 入局与认领

1. 你在游戏里：主菜单 → 多人 → 邀请 AI 队友（或单人「AI 独自爬塔」）；
2. 入局约 30s 后，Mod 开启 `sts2_takeover` 邀请窗口（每局最多 3 次、每次 60s）；
3. 插件每 4s 轮询 `sts2_takeover`：
   - `take:true` → 记录 `run_token`、向 `home_session` 发开场白（人格化一句），启动 `PlayLoop`；
   - `take:false` 且 reason=`already_driving` → 说明已有别的客户端在驱动，不打扰；
   - `warmup` / `disabled` / `read_only` / `no_ai_teammate` → 记日志，不重试轰炸。

### 6.3 决策循环（无人说话时）

```
sts2_wait → phase=ai_decision
   → 组 prompt：decision.prompt + 最近 5 条队友发言 + 本局笔记 + 局面摘要
   → provider.text_chat(单发, JSON)
   → 解析/校验 → sts2_decide
   → 心跳继续 → sts2_wait …
```

- 失败：重试 1 次；仍失败 → 停心跳，交给 Mod 回退，会话里发「这回合我卡住了，先让内置 AI 顶一下」；
- `game_over` → 发本局总结（层数、死因、构筑），停止循环，释放 `run_token`；
- 离开对局（回主菜单）→ 立即停循环，避免在主菜单空转。

### 6.4 聊天（群聊/私聊）

1. 群友发消息 → AstrBot 正常管线（人格、记忆、工具）；
2. `on_llm_request` 注入：`<sts2_context> 当前第X层，HP…，你的角色…，最近游戏内聊天… </sts2_context>`（临时块）；
3. 模型回复 → `on_llm_response` → 若本局进行中且开启镜像 → `sts2_chat_send`；
4. 游戏内玩家在面板发言 → `chat_poll` → 作为 `[游戏内] 玩家名: ...` 注入下一轮，必要时 `reply_to` 回复；
5. 有人 @ 或私聊时，回复照常走 QQ；游戏内面板同步显示一份。

### 6.5 收回控制权

- `/sts2 stop`：停 `PlayLoop`、停心跳；
- 游戏内关闭「外部 Agent 桥接」：Mod 立即回退内置后端，插件检测到断连后停止；
- `/sts2 pause` / `/sts2 resume`：只暂停插件循环，不暂停游戏（避免和 Mod 的暂停语义打架）。

---

## 7. 插件结构

```
astrbot_plugin_sts2_teammate/
├── metadata.yaml            # 名称/作者/版本/astrbot_version
├── _conf_schema.json        # WebUI 配置
├── main.py                  # Star 子类：指令、钩子、生命周期
├── bridge.py                # asyncio TCP 行 JSON 客户端（无第三方依赖）
├── protocol.py              # 请求/响应数据类 + 校验
├── play_loop.py             # 自主循环、决策提示词、重试/回退
├── chat_bridge.py           # chat_poll / chat_send / 回声抑制 / seq 管理
├── takeover.py              # 邀请轮询与认领
├── prompts.py               # 决策 system/user 模板、人格化播报模板
├── state.py                 # 运行态：token、run_token、directives、notes
├── README.md                # 安装、配置、故障排查
└── requirements.txt         # 空（仅标准库 + AstrBot API）
```

**主要指令**（`/sts2` 指令组）：

| 指令 | 作用 |
|---|---|
| `/sts2 status` | 连接、游戏版本、当前阶段、是否在驱动 |
| `/sts2 play` | 手动开始接管（也用于绑定当前会话） |
| `/sts2 pause` / `/sts2 resume` | 暂停/恢复自主循环 |
| `/sts2 stop` | 停止并释放 |
| `/sts2 bind` | 把当前会话设为播报/镜像目标 |
| `/sts2 say <text>` | 让 AI 队友在游戏聊天面板说一句 |
| `/sts2 note <text>` | 记录本局笔记 |
| `/sts2 config` | 显示当前关键配置（不显示 token） |

---

## 8. 配置 Schema 草案

```json
{
  "host": {"description": "游戏桥地址", "type": "string", "default": "127.0.0.1"},
  "port": {"description": "游戏桥端口（与 Mod 设置一致）", "type": "int", "default": 26333},
  "token": {"description": "访问 token（与 Mod 设置一致，可留空）", "type": "string", "default": "", "secret": true},
  "provider_id": {"description": "决策与聊天使用的模型", "type": "string", "default": "", "_special": "select_provider"},
  "persona_id": {"description": "聊天人格", "type": "string", "default": "", "_special": "select_persona"},
  "home_session": {"description": "播报目标会话 umo（留空则绑定首个 /sts2 play 的会话）", "type": "string", "default": ""},
  "auto_takeover": {"description": "AI 队友入局时自动认领", "type": "bool", "default": true},
  "auto_play": {"description": "认领后自动开始决策循环", "type": "bool", "default": true},
  "allow_actions": {"description": "允许回答决策（关闭=只读围观）", "type": "bool", "default": false},
  "mirror_chat": {"description": "把 QQ 回复镜像到游戏聊天面板", "type": "bool", "default": true},
  "relay_game_chat": {"description": "把游戏内聊天转进 QQ 上下文", "type": "bool", "default": true},
  "broadcast": {"description": "关键节点播报到目标会话", "type": "bool", "default": true},
  "heartbeat_seconds": {"description": "决策期间心跳间隔", "type": "int", "default": 10},
  "decision_timeout_seconds": {"description": "单次模型请求超时", "type": "int", "default": 45},
  "max_requests_per_run": {"description": "单局模型请求上限（预算护栏）", "type": "int", "default": 1500},
  "play_style": {"description": "决策风格提示", "type": "string", "default": "balanced", "options": ["safe", "balanced", "greedy"]},
  "debug_log": {"description": "输出桥协议与决策日志", "type": "bool", "default": false}
}
```

> `provider_id` / `persona_id` 用 `_special` 让 WebUI 直接出模型/人格下拉框。

---

## 9. 状态机与并发

```
DISCONNECTED ──connect ok──> READY ──takeover ok──> RUNNING
     ▲                         │                      │
     └──── 断线/重连 ───────────┘                      │
                                                      ├─ ai_decision → DECIDING → RUNNING
                                                      ├─ pause → PAUSED → resume → RUNNING
                                                      └─ game_over/stop → ENDED
```

- 一个 `BridgeClient`（单连接，请求 id 自增，按 id 匹配响应）；
- 一个 `PlayLoop`（全局唯一）；
- 一个 `Heartbeat`（仅 `DECIDING` 期间运行）；
- 一个 `ChatPump`（`chat_poll` 长轮询，可与决策并行）；
- 一个 `TakeoverPoller`（未认领时每 4s，认领后停止）；
- 所有任务在 `terminate()` 中 cancel + await，socket 关闭。

**并发注意**：

- 决策与聊天回复可能同时发生 → 决策锁只锁 `sts2_decide`，聊天 `chat_send` 走独立队列；
- 心跳与 `sts2_wait` 不能同时打满桥 → 心跳只在「模型请求进行中」发，`sts2_wait` 返回后停；
- 动作串行由 Mod 保证（`SemaphoreSlim(1)`），插件无需再串行，但不要并发发两个 `sts2_decide`。

---

## 10. 成本与延迟（粗估）

| 项 | 估算 | 说明 |
|---|---|---|
| 单局决策次数 | 200–600 次 | 战斗每回合可能多次决策（Mod 单回合最多 6 次） |
| 单次输入 | 1.5–4k tokens | `decision.prompt` + 紧凑局面 + 最近发言 |
| 单次输出 | 100–400 tokens | JSON 决策 |
| 单局总量 | **约 1–3M tokens** | 比 dsh-sts2 的 7–8M 低一个量级（没有工具循环历史） |
| 单次延迟 | 2–8s | 取决于模型；超过 30s 会触发 Mod 静默回退，心跳可缓解 |
| 聊天 | 每次一条普通对话 | 与对局分开计费 |

> 实测为准；`max_requests_per_run` 是硬护栏，达到上限自动停并播报。

---

## 11. 风险与未验证点

| # | 风险 | 影响 | 应对 |
|---|---|---|---|
| 1 | 游戏 `0.113.1` 与 AiTeammate 的兼容性（README 支持表停在 0.107/0.111，仓库 11-13 才适配 0.113.0） | 桥可能起不来或行为异常 | 先做 M0 连通性验证；不行就等 Release 或回退游戏分支 |
| 2 | Mod 的「静默回退」30s 与模型慢响应冲突 | 决策被内置后端抢走 | 心跳 + 把 `AgentFallbackSeconds` 调大（Mod 设置） |
| 3 | 多人局中 AI 决策的执行一致性（`externalBrain` 全房一致） | 掉线 / 状态分叉 | 只在一台机器（房主）驱动；先单人验证再联机 |
| 4 | AstrBot 4.x API 漂移（`on_llm_request`、`text_chat`、`send_message`） | 插件加载失败 | `metadata.yaml` 声明 `astrbot_version`；M0 先跑通最小调用 |
| 5 | 聊天回声/循环（游戏面板 ↔ QQ） | 刷屏、重复回复 | `sent_hashes` + 只镜像目标会话 + 冷却 |
| 6 | 群聊限流 / 长消息 | 播报丢失 | 合并摘要、每条 ≤ 200 字、失败重试一次 |
| 7 | 模型 JSON 不合格 | 决策失败 | 重试 1 次；再失败停心跳让 Mod 兜底，并如实播报 |
| 8 | 人格与决策冲突（聊天人格太话痨，决策输出跑偏） | 决策质量差 | 决策用独立 system prompt，只借用人格的「战斗风格」字段 |
| 9 | AstrBot 在 Docker 里（虽然本机是原生） | localhost 不通 | 文档写明必须同机原生；Docker 需 `host.docker.internal` |
| 10 | 只读模式误开动作 | 抢玩家操作 | `allow_actions` 默认 false；首次开启需二次确认 |

---

## 12. 里程碑与验收

| 里程碑 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| **M0 连通** | BridgeClient + `hello`/`state` + `/sts2 status` | 0.5 天 | 游戏内状态页显示「已连接 1 个客户端」；`/sts2 status` 返回版本与局面摘要 |
| **M1 决策闭环** | `ai_decision → text_chat → sts2_decide`，单场战斗 | 1 天 | 带 AI 队友的一局里，AI 队友的战斗由 AstrBot 模型决策并打完 |
| **M2 聊天双向** | `on_llm_request` 注入、`on_llm_response` 镜像、`chat_poll` 回传 | 1 天 | 群里说「先打左边」影响下一手；游戏面板出现 AstrBot 的回复；回复 `seq` 正确 |
| **M3 自主与播报** | 完整一局无人干预、关键节点播报、预算/暂停 | 1 天 | 一局从开局到结束无需人工说话；超预算自动停并播报 |
| **M4 打包容错** | `metadata.yaml`/schema/README/重连/日志脱敏 | 0.5–1 天 | 卸载重装不丢配置；断游戏 30s 内自动重连；日志不含 token |

**总工作量：约 4–5 个工作日**（不含调优与兼容性排障）。

---

## 13. 本方案不做什么

- ❌ 不做「AstrBot 代打玩家本人」（`controlled.kind=local` 的 UI 动作）——那是另一套工具集；
- ❌ 不做多局并行、多开游戏实例；
- ❌ 不做游戏内 overlay / 截图理解（Mod 自己有截图工具，AstrBot 模型不支持图像时会退化）；
- ❌ 不替代 Mod 的内置 AI：内置 AI 始终是兜底，桥断了游戏也能继续；
- ❌ 不做语音（可作为 M5：AstrBot TTS + 游戏内 MiniMax 二选一，避免两个声音）。

---

## 14. 参考

- AiTeammate Mod：https://github.com/YuWan886/STS2-AiTeammate
- 桥协议设计文档（本方案主要依据）：https://github.com/YuWan886/STS2-AiTeammate/blob/main/docs/dsh-agent-bridge.md
- dsh-sts2 插件（可借鉴的客户端实现，MIT）：https://github.com/YuWan886/dsh-sts2
- AstrBot 插件开发（Star / 工具 / LLM）：https://docs.astrbot.app/dev/star/plugin.html
- AstrBot AI 指南（`text_chat` / `tool_loop_agent` / 人格）：https://docs.astrbot.app/dev/star/guides/ai.html
- AstrBot MCP（本方案不需要，但可作备选）：https://docs.astrbot.app/use/mcp.html

---

*本文件是设计稿，尚未创建任何代码；实现前建议先做 M0 连通性验证，确认游戏 `0.113.1` + AiTeammate 的桥能正常握手。*
