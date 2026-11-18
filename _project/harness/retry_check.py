# -*- coding: utf-8 -*-
"""验证「多人动作被拒 → 重读状态 → 重试」补丁。

做法：用假的 client 包住真实 Sts2Client，第一次对 play_card / choose_map_node
返回引擎真实的 409 错误体，之后放行，然后跑插件真实的 `_auto` 循环。
只要补丁生效，整局就不会因为一次瞬时拒绝而停下。

不连游戏也能跑（用 mock 状态序列），连上游戏时更真实。

    python retry_check.py            # 离线（mock 状态序列）
    python retry_check.py --live     # 连真游戏
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"   # 仓库根的插件本体


def combat_state(turn: int, energy: int, hp: int = 70) -> dict:
    """造一个「玩家可行动、手上有打击」的战斗状态（插件内部形状）。"""
    hand = []
    for i in range(min(3, energy)):
        hand.append(
            {
                "index": i,
                "id": "STRIKE_IRONCLAD",
                "name": "打击",
                "type": "Attack",
                "cost": 1,
                "description": "造成6点伤害。",
                "target_type": "AnyEnemy",
                "requires_target": True,
                "valid_target_indices": [0],
                "can_play": True,
                "resolved_damage": 6,
                "resolved_block": 0,
            }
        )
    return {
        "state_type": "monster",
        "screen": "COMBAT",
        "available_actions": ["end_turn", "play_card"],
        "run": {"act": 1, "floor": 1, "character": "铁甲战士", "gold": 99},
        "player": {
            "hp": hp,
            "max_hp": 80,
            "block": 0,
            "energy": energy,
            "max_energy": 3,
            "gold": 99,
            "hand": hand,
            "potions": [],
            "relics": [],
            "deck": [],
        },
        "battle": {
            "round": turn,
            "turn": "player",
            "is_play_phase": True,
            "waiting_for_players": False,
            "players": [],
            "lethal": False,
            "enemies": [
                {
                    "entity_id": "0",
                    "name": "小啃兽",
                    "hp": 99,
                    "max_hp": 99,
                    "block": 0,
                    "intents": [{"type": "Attack", "label": "12", "title": "Attack"}],
                }
            ],
        },
    }


class FlakyClient:
    """第一次动作返回多人局真实会遇到的 409，之后正常。"""

    def __init__(self, inner, fail_kinds):
        self.inner = inner
        self.fail_kinds = list(fail_kinds)
        self.act_calls = 0
        self.failed = 0

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def state(self, fmt: str = "json"):
        return await self.inner.state(fmt)

    async def close(self):
        await self.inner.close()

    async def act(self, action, **params):
        self.act_calls += 1
        if self.fail_kinds:
            kind = self.fail_kinds.pop(0)
            self.failed += 1
            return {"status": "error", "error": f"409: {kind}"}
        return await self.inner.act(action, **params)


class SequenceClient:
    """离线：状态序列由脚本给定，动作只记账。"""

    def __init__(self, states):
        self.states = list(states)
        self.i = 0
        self.acted: list[tuple] = []
        self.fail_plan = {0: "invalid_action"}  # 第 1 次动作被拒

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def state(self, fmt: str = "json"):
        st = self.states[min(self.i, len(self.states) - 1)]
        self.i += 1
        return st

    async def close(self):
        return None

    async def act(self, action, **params):
        n = len(self.acted)
        if n in self.fail_plan:
            self.fail_plan.pop(n)
            return {"status": "error", "error": "409: invalid_action: Action is not available in the current state."}
        self.acted.append((action, params))
        return {"status": "ok", "message": "Action completed."}


async def run_offline(mod) -> int:
    # 足够长的可行动回合：补丁应当「被拒一次 → 重试成功 → 继续打完」
    states = [combat_state(1, 3, hp=80 - i) for i in range(6)]
    states += [combat_state(2, 3, hp=60) for _ in range(4)]
    client = SequenceClient(states)
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(sts2stub.ScriptedProvider()), {"max_steps": 6})
    plugin.client = client
    event = sts2stub.AstrMessageEvent()

    messages = []
    async for msg in plugin._auto(event, 6):
        messages.append(str(msg))

    print(f"动作次数：{len(client.acted)}")
    for a in client.acted:
        print(f"  · {a[0]} {a[1]}")
    print("\n--- 插件输出 ---")
    for m in messages:
        print("  " + m.splitlines()[0][:110])

    got = [a for a in client.acted if a[0] == "play_card"]
    stuck = any("连续失败" in m for m in messages)
    if stuck:
        print("\n✗ 仍然因为瞬时拒绝而整局停下")
        return 1
    if len(got) < 2:
        print(f"\n✗ 重试后没有继续出牌（只出了 {len(got)} 张）")
        return 1
    print(f"\n✓ 被拒一次后自动重试并继续（共出牌 {len(got)} 次），没有整局停下")
    return 0


async def run_live(mod, args) -> int:
    client = FlakyClient(mod.Sts2Client(args.base, timeout=25.0), ["invalid_action"])
    await client.detect()
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(sts2stub.ScriptedProvider()), {"max_steps": 8})
    plugin.client = client
    event = sts2stub.AstrMessageEvent()
    msgs = []
    async for msg in plugin._auto(event, 8):
        msgs.append(str(msg))
    print(f"动作调用 {client.act_calls} 次，注入失败 {client.failed} 次")
    for m in msgs[:6]:
        print("  " + m.splitlines()[0][:110])
    stuck = any("连续失败" in m for m in msgs)
    if client.failed and stuck:
        print("\n✗ 注入的瞬时拒绝把整局停下了")
        return 1
    print("\n✓ 真游戏上被注入一次拒绝后仍继续")
    await client.close()
    return 0


async def amain(args) -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    if args.live:
        return await run_live(mod, args)
    return await run_offline(mod)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--base", default="http://127.0.0.1:8082")
    a = p.parse_args()
    raise SystemExit(asyncio.run(amain(a)))
