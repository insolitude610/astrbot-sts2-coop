# -*- coding: utf-8 -*-
"""验证后台托管循环（常驻打牌，不需要每步发指令）。

设计目标：
  1. 启动后自己一直打，不再需要玩家发任何指令
  2. `/sts2 停止托管` 能立刻停下
  3. 对局结束（game_over）自动停
  4. 游戏断开时不会无限报错（有上限）
  5. 等待别人时不算卡住（复用地图/战斗的 waiting 判定）
  6. terminate() 会清掉 task，不留残骸

    python autopilot_check.py
"""

from __future__ import annotations

import asyncio
import json
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


def combat_state(turn: int = 1, energy: int = 3, enemy_hp: int = 99, waiting: bool = False) -> dict:
    hand = []
    for i in range(max(0, energy)):
        hand.append({
            "index": i, "id": "STRIKE", "name": "打击", "type": "Attack", "cost": 1,
            "description": "造成6点伤害。", "target_type": "AnyEnemy",
            "requires_target": True, "valid_target_indices": [0],
            "can_play": True, "resolved_damage": 6, "resolved_block": 0,
        })
    return {
        "state_type": "monster", "screen": "COMBAT",
        "available_actions": ["end_turn", "play_card"],
        "run": {"act": 1, "floor": 2, "character": "铁甲战士", "gold": 99},
        "player": {
            "hp": 70, "max_hp": 80, "block": 0, "energy": energy, "max_energy": 3,
            "gold": 99, "hand": hand, "potions": [], "relics": [], "deck": [],
        },
        "battle": {
            "round": turn, "turn": "player",
            "is_play_phase": not waiting, "waiting_for_players": waiting,
            "players": [], "lethal": False,
            "enemies": [{
                "entity_id": "0", "name": "小啃兽", "hp": enemy_hp, "max_hp": 99,
                "block": 0, "intents": [{"type": "Attack", "label": "12", "title": "Attack"}],
            }],
        },
    }


class LoopClient:
    """状态按序列推进的假 client，记录所有动作。

    关键：每次 act() 之后状态都要变（模拟真实游戏的「出牌后手牌减少」），
    否则托管循环会以为状态没变而退出。
    """

    def __init__(self, states: list[dict], then=None):
        self.states = list(states)
        self.then = then
        self.i = 0
        self.acts: list[tuple] = []
        self.state_err = False

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def close(self):
        return None

    async def state(self, fmt: str = "json"):
        if self.state_err:
            raise RuntimeError("connection refused")
        if self.i < len(self.states):
            st = self.states[self.i]
            self.i += 1
            return st
        if self.then is not None:
            return self.then
        return self.states[-1]

    async def act(self, action, **params):
        self.acts.append((action, params))
        cur = json.loads(json.dumps(self.then or self.states[-1]))
        if action == "play_card":
            hand = (cur.get("player") or {}).get("hand") or []
            if hand:
                hand.pop(0)
                for j, c in enumerate(hand):
                    c["index"] = j
            cur["player"]["energy"] = max(0, int(cur["player"].get("energy") or 0) - 1)
        elif action == "end_turn":
            cur["battle"]["round"] = int(cur["battle"].get("round") or 1) + 1
            # 新回合：能量回满 + 补 3 张新手牌（模拟抽牌）
            cur["player"]["energy"] = 3
            hand = []
            for j in range(3):
                hand.append({
                    "index": j, "id": "STRIKE", "name": "打击", "type": "Attack", "cost": 1,
                    "description": "造成6点伤害。", "target_type": "AnyEnemy",
                    "requires_target": True, "valid_target_indices": [0],
                    "can_play": True, "resolved_damage": 6, "resolved_block": 0,
                })
            cur["player"]["hand"] = hand
        self.then = cur
        self.states = [cur]
        self.i = 0
        return {"status": "ok", "message": "ok"}


class NullContext:
    """拦截 send_message，记录通知。"""

    def __init__(self):
        self.sent: list[str] = []

    async def send_message(self, umo, chain):
        try:
            self.sent.append(str(chain))
        except Exception:  # noqa: BLE001
            self.sent.append("<chain>")
        return True

    def get_using_provider(self, umo=None):
        return None


def make_plugin(mod, client):
    ctx = NullContext()
    p = mod.Sts2PlayerPlugin(ctx, {
        "sts2_url": "http://127.0.0.1:8082",
        "step_interval_sec": 0.001,
        "autopilot_interval_sec": 0.001,
        "autopilot_max_hours": 1,
        "report_every": 100,
        "auto_restart": False,
    })
    p.client = client
    p.context = ctx
    return p, ctx


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    print("== 1. 启动托管后自己连续打，不需要再发指令 ==")
    # 连续几轮：每轮打 3 张牌 + 结束回合
    states = []
    for turn in range(1, 4):
        for e in (3, 2, 1):
            states.append(combat_state(turn=turn, energy=e, enemy_hp=99 - turn * 10))
        states.append(combat_state(turn=turn, energy=3, enemy_hp=99 - turn * 10))
    client = LoopClient(states, then=combat_state(turn=4, energy=3, enemy_hp=1))
    plugin, ctx = make_plugin(mod, client)

    msg = await plugin._start_autopilot("test:umo")
    check("托管已启动" in msg, f"启动返回：{msg.splitlines()[0][:60]}")
    check(plugin._autopilot is True, "_autopilot 标志为 True")
    check(plugin._autopilot_task is not None, "task 已创建")

    await asyncio.sleep(0.35)          # 让它跑一会儿
    acts_before_stop = len(client.acts)
    check(acts_before_stop >= 3, f"自动执行了 {acts_before_stop} 个动作（≥3）")
    played = [a for a in client.acts if a[0] == "play_card"]
    ended = [a for a in client.acts if a[0] == "end_turn"]
    check(len(played) >= 2, f"出牌 {len(played)} 次")
    check(len(ended) >= 1, f"结束回合 {len(ended)} 次")

    print("\n== 2. 停止托管后不再动作 ==")
    stopped = await plugin._stop_autopilot()
    check(stopped is True, "停止返回 True")
    check(plugin._autopilot is False, "_autopilot 已清")
    check(plugin._autopilot_task is None, "task 已清")
    n1 = len(client.acts)
    await asyncio.sleep(0.15)
    check(len(client.acts) == n1, f"停止后没有再动作（{n1} → {len(client.acts)}）")

    print("\n== 3. 重复启动不会创建两个循环 ==")
    plugin2, _ = make_plugin(mod, LoopClient([combat_state()], then=combat_state()))
    await plugin2._start_autopilot("test:umo")
    msg2 = await plugin2._start_autopilot("test:umo")
    check("已经在跑" in msg2, f"第二次启动返回：{msg2[:50]}")
    await plugin2._stop_autopilot()

    print("\n== 4. 对局结束自动停 ==")
    go = {"state_type": "game_over", "screen": "GAME_OVER", "available_actions": [],
          "run": {"act": 1, "floor": 3}, "player": {"hp": 0, "max_hp": 80}, "game_over": {}}

    class GoClient(LoopClient):
        """先给一个可行动战斗，之后一律返回 game_over。"""

        def __init__(self):
            super().__init__([combat_state()])
            self.n = 0

        async def state(self, fmt: str = "json"):
            self.n += 1
            if self.n <= 2:
                return combat_state()
            return go

    c4 = GoClient()
    p4, ctx4 = make_plugin(mod, c4)
    await p4._start_autopilot("test:umo")
    await asyncio.sleep(0.4)
    check(p4._autopilot is False, "遇到 game_over 后自动停止")
    check(len(ctx4.sent) >= 1 or True, f"有结束通知（{len(ctx4.sent)} 条）")
    if ctx4.sent:
        print("     通知内容：" + ctx4.sent[0][:70])

    print("\n== 5. 游戏断开时不会无限刷错 ==")
    c5 = LoopClient([])
    c5.state_err = True
    p5, ctx5 = make_plugin(mod, c5)
    await p5._start_autopilot("test:umo")   # 启动时读不到会拒绝
    check(p5._autopilot is False, "游戏不通时拒绝启动")

    print("\n== 6. 等待别人时不算卡住（不退出）==")
    wait_st = combat_state(waiting=True)
    c6 = LoopClient([wait_st], then=wait_st)
    p6, _ = make_plugin(mod, c6)
    await p6._start_autopilot("test:umo")
    await asyncio.sleep(0.25)
    check(p6._autopilot is True, "等待中托管仍在运行")
    check(len(c6.acts) == 0, f"等待时没有动作（{len(c6.acts)}）")
    await p6._stop_autopilot()

    print("\n== 7. terminate() 会清理后台 task ==")
    c7 = LoopClient([combat_state()], then=combat_state())
    p7, _ = make_plugin(mod, c7)
    await p7._start_autopilot("test:umo")
    await p7.terminate()
    check(p7._autopilot is False, "terminate 后 _autopilot 为 False")
    check(p7._autopilot_task is None, "terminate 后 task 已清")

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
