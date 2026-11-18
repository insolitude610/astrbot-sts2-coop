# -*- coding: utf-8 -*-
"""验证「机器人不说话」的修复。

真机现场（2026-11-18 12:03）：
  /sts2 自动 10 → 插件执行了、出牌了，但一条回复都没发。
  原因：播报条件 `i % report_every == 0 or i == steps`，
  默认 report_every=15、max_steps=20，而 steps=10 →
  10 % 15 != 0 且 10 != 20 → 一次都不播。

修复后应有行为：
  1. 一开始就回一条「开始自动打 N 步」（不等 report_every）
  2. 每一步至少有一行极简进度 [i/N]
  3. 进入等待（地图/战斗）时第一时间就说一声
  4. 正常跑完有收尾消息
  5. 步数为 1 也要有输出

    python reply_check.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  {'✓' if ok else '✗'} {label}" + (f"  — {detail}" if detail and not ok else ""))


def map_state(voted: bool) -> dict:
    return {
        "state_type": "map",
        "screen": "MAP",
        "available_actions": ["choose_map_node"],
        "run": {"act": 1, "floor": 0, "character": "铁甲战士", "gold": 99},
        "player": {"hp": 80, "max_hp": 80, "gold": 99},
        "map": {
            "current_position": {},
            "next_options": [{"index": 0, "row": 0, "col": 3, "type": "Monster"}],
            "boss": {},
            "can_vote": True,
            "local_vote": {"row": 0, "col": 3} if voted else None,
            "voted_player_ids": ["8"] if voted else [],
        },
    }


def combat_state() -> dict:
    return {
        "state_type": "monster",
        "screen": "COMBAT",
        "available_actions": ["end_turn", "play_card"],
        "run": {"act": 1, "floor": 1, "character": "铁甲战士", "gold": 99},
        "player": {
            "hp": 70, "max_hp": 80, "block": 0, "energy": 3, "max_energy": 3, "gold": 99,
            "hand": [{
                "index": 0, "id": "STRIKE", "name": "打击", "type": "Attack", "cost": 1,
                "description": "造成6点伤害。", "target_type": "AnyEnemy",
                "requires_target": True, "valid_target_indices": [0],
                "can_play": True, "resolved_damage": 6, "resolved_block": 0,
            }],
            "potions": [], "relics": [], "deck": [],
        },
        "battle": {
            "round": 1, "turn": "player", "is_play_phase": True,
            "waiting_for_players": False, "players": [], "lethal": False,
            "enemies": [{
                "entity_id": "0", "name": "小啃兽", "hp": 99, "max_hp": 99, "block": 0,
                "intents": [{"type": "Attack", "label": "12", "title": "Attack"}],
            }],
        },
    }


class FixedClient:
    """返回状态；每次都让 state 有一点点变化，模拟真游戏（否则会触发「卡住」判定）。"""

    def __init__(self, st: dict, vary: bool = True):
        self.st = st
        self.acts: list[tuple] = []
        self.vary = vary
        self.n = 0

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def close(self):
        return None

    async def state(self, fmt: str = "json"):
        self.n += 1
        if not self.vary:
            return self.st
        # 深拷贝后改一个无副作用的字段，让签名变化但不影响规则层判断
        import copy

        st = copy.deepcopy(self.st)
        st["_tick"] = self.n
        return st

    async def act(self, action, **params):
        self.acts.append((action, params))
        return {"status": "ok", "message": "ok"}


async def run_case(
    mod, st: dict, steps: int, cfg_extra=None, vary: bool = True
) -> tuple[list[str], FixedClient]:
    cfg = {
        "max_steps": 40,
        "step_interval_sec": 0.001,
        "report_every": 15,     # 关键：保持默认值，复现原 bug 条件
        "auto_restart": False,
    }
    if cfg_extra:
        cfg.update(cfg_extra)
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(sts2stub.ScriptedProvider()), cfg)
    client = FixedClient(st, vary=vary)
    plugin.client = client
    msgs = []
    async for m in plugin._auto(sts2stub.AstrMessageEvent(), steps):
        msgs.append(str(m))
    return msgs, client


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    print("== 1. steps=10, report_every=15（原来一句话都没有）==")
    msgs, _ = await run_case(mod, combat_state(), 10)
    check(len(msgs) >= 2, f"至少 2 条消息（实际 {len(msgs)} 条）")
    check(any("开始自动打" in m for m in msgs), "有「开始自动打」开场消息")
    progress = [m for m in msgs if m.startswith("[") and "/" in m.split("]")[0] + "]"]
    check(len(progress) >= 1, f"有进度消息（{len(progress)} 条）")
    check(any("跑满" in m for m in msgs), "有收尾消息")
    print("     实际输出：")
    for m in msgs[:4]:
        print("       · " + m.splitlines()[0][:80])

    print("\n== 2. steps=1 也要说话 ==")
    msgs, _ = await run_case(mod, combat_state(), 1)
    check(len(msgs) >= 2, f"steps=1 有 {len(msgs)} 条消息")

    print("\n== 3. 地图已投票 → 进等待要立刻提示 ==")
    msgs, client = await run_case(mod, map_state(voted=True), 3)
    votes = [a for a in client.acts if a[0] == "choose_map_node"]
    check(len(votes) == 0, f"没有重复投票（{len(votes)} 次）")
    wait_msg = [m for m in msgs if "等你投票" in m or "等别人投票" in m]
    check(len(wait_msg) >= 1, f"有等待提示（{len(wait_msg)} 条）")
    if wait_msg:
        print("     提示内容：" + wait_msg[0].splitlines()[0][:80])

    print("\n== 4. report_every=1 时仍然正常 ==")
    msgs, _ = await run_case(mod, combat_state(), 3, {"report_every": 1})
    check(len(msgs) >= 4, f"每步都播报（{len(msgs)} 条）")

    print("\n== 5. _running 状态不泄漏 ==")
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(sts2stub.ScriptedProvider()),
                                  {"max_steps": 10, "step_interval_sec": 0.001})
    plugin.client = FixedClient(combat_state())
    ev = sts2stub.AstrMessageEvent()
    async for _ in plugin._auto(ev, 2):
        pass
    check(ev.unified_msg_origin not in plugin._running,
          f"跑完后不在 _running 里（{plugin._running}）")

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
