# -*- coding: utf-8 -*-
"""验证聊天上下文注入：有游戏就注入、没游戏就静默跳过。

设计目标（用户明确要求）：
  1. 游戏开着 → 聊天时模型能看到当前战况
  2. **游戏关了 → 一行都不注入，也不拖慢闲聊**
  3. 连发多条消息不重复打接口（缓存）
  4. 注入用临时块，不写进对话历史

    python inject_check.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  {'✓' if ok else '✗'} {label}" + (f"  — {detail}" if detail and not ok else ""))


class FakePart:
    def __init__(self, text: str):
        self.text = text
        self.is_temp = False

    def mark_as_temp(self):
        self.is_temp = True
        return self


class FakeReq:
    def __init__(self):
        self.extra_user_content_parts: list = []


class FakeClient:
    """可切换「游戏开着/关掉」的假 client。"""

    def __init__(self, alive: bool = True):
        self.alive = alive
        self.calls = 0

    async def state(self, fmt: str = "json"):
        self.calls += 1
        if not self.alive:
            raise RuntimeError("connection refused")
        return {
            "state_type": "monster",
            "screen": "COMBAT",
            "available_actions": ["end_turn", "play_card"],
            "run": {"act": 1, "floor": 3, "character": "铁甲战士", "gold": 120},
            "player": {
                "hp": 70, "max_hp": 80, "block": 0, "energy": 3, "max_energy": 3,
                "gold": 120, "hand": [], "potions": [], "relics": [], "deck": [],
            },
            "battle": {
                "round": 2, "turn": "player", "is_play_phase": True,
                "waiting_for_players": False, "players": [], "lethal": False,
                "enemies": [{
                    "entity_id": "0", "name": "缩小甲虫", "hp": 8, "max_hp": 85,
                    "block": 0, "intents": [{"type": "Attack", "label": "12", "title": "Attack"}],
                }],
            },
        }

    async def close(self):
        return None


def make_plugin(mod, client, cfg_extra=None):
    cfg = {"sts2_url": "http://127.0.0.1:8082", "inject_game_context": True, "context_cache_sec": 8.0}
    if cfg_extra:
        cfg.update(cfg_extra)
    p = mod.Sts2PlayerPlugin(sts2stub.StubContext(sts2stub.ScriptedProvider()), cfg)
    p.client = client
    return p


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    # 让插件能 import 到 TextPart（真实 AstrBot 里由 astrbot.core.agent.message 提供）
    fake_msg = types.ModuleType("astrbot.core.agent.message")
    fake_msg.TextPart = FakePart
    fake_core = types.ModuleType("astrbot.core")
    fake_agent = types.ModuleType("astrbot.core.agent")
    fake_core.agent = fake_agent
    fake_agent.message = fake_msg
    sys.modules["astrbot.core"] = fake_core
    sys.modules["astrbot.core.agent"] = fake_agent
    sys.modules["astrbot.core.agent.message"] = fake_msg

    event = sts2stub.AstrMessageEvent()

    print("== 1. 游戏开着 → 注入战况 ==")
    c = FakeClient(alive=True)
    p = make_plugin(mod, c)
    req = FakeReq()
    await p.inject_game_context(event, req)
    check(len(req.extra_user_content_parts) == 1, f"注入了 {len(req.extra_user_content_parts)} 个内容块")
    if req.extra_user_content_parts:
        part = req.extra_user_content_parts[0]
        check("sts2_game_context" in part.text, "含 <sts2_game_context> 标记")
        check("缩小甲虫" in part.text, "含敌人信息")
        check("第1幕 第3层" in part.text or "第3层" in part.text, "含层数")
        check(getattr(part, "is_temp", False), "标记为临时块（不进历史）")
        print("     注入片段（前 3 行）：")
        for line in part.text.splitlines()[:3]:
            print("       " + line[:80])

    print("\n== 2. **游戏关了 → 一行都不注入** ==")
    dead = FakeClient(alive=False)
    p2 = make_plugin(mod, dead)
    req2 = FakeReq()
    await p2.inject_game_context(event, req2)
    check(len(req2.extra_user_content_parts) == 0, "没有注入任何内容块")

    print("\n== 3. 游戏关着时，连发多条消息不重复探测 ==")
    # 用全新的 client + plugin，避免受上一项已建立的冷却影响
    dead2 = FakeClient(alive=False)
    p2b = make_plugin(mod, dead2)
    dead2.calls = 0
    for _ in range(5):
        await p2b.inject_game_context(event, FakeReq())
    check(dead2.calls == 1, f"5 条消息只探测了 {dead2.calls} 次接口（应为 1）")
    check(len(p2b.__dict__) > 0 and p2b._ctx_cache is None, "缓存为空（不会注入旧数据）")

    print("\n== 4. 游戏开着时，多条消息共用缓存 ==")
    live = FakeClient(alive=True)
    p3 = make_plugin(mod, live, {"context_cache_sec": 60.0})
    live.calls = 0
    for _ in range(5):
        r = FakeReq()
        await p3.inject_game_context(event, r)
        assert len(r.extra_user_content_parts) == 1
    check(live.calls == 1, f"5 条消息只请求 {live.calls} 次接口（缓存 60s）")

    print("\n== 5. 配置关掉后完全不注入 ==")
    p4 = make_plugin(mod, FakeClient(alive=True), {"inject_game_context": False})
    req4 = FakeReq()
    await p4.inject_game_context(event, req4)
    check(len(req4.extra_user_content_parts) == 0, "开关关闭时不注入")

    print("\n== 6. 游戏从「关」到「开」能自动恢复 ==")
    flip = FakeClient(alive=False)
    p5 = make_plugin(mod, flip)
    r1 = FakeReq()
    await p5.inject_game_context(event, r1)
    check(len(r1.extra_user_content_parts) == 0, "关着时不注入")
    flip.alive = True
    p5._ctx_next_probe = 0.0     # 模拟过了冷却期
    r2 = FakeReq()
    await p5.inject_game_context(event, r2)
    check(len(r2.extra_user_content_parts) == 1, "游戏起来后能恢复注入")

    ok = sum(1 for r in results if r[0])
    print(f"\n=== {ok}/{len(results)} 通过 ===")
    if ok != len(results):
        for good, label in results:
            if not good:
                print(f"  ✗ {label}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
