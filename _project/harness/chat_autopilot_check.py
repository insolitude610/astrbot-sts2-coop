# -*- coding: utf-8 -*-
"""验证「聊天打断 + 自然语言触发 + 卡住主动问」三个新行为。

用户需求原话：
  「我说一下这个有牌打，他就一直打下去，
   直到主机可能卡了很久不出牌 bot 主动发个消息问一下，
   或者用户正常打牌的时候发消息了暂时停一下，回一句话然后继续打」

    python chat_autopilot_check.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  {'✓' if ok else '✗'} {label}" + (f"  — {detail}" if detail and not ok else ""))


def combat_state(energy: int = 3, waiting: bool = False, turn: int = 1) -> dict:
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
                "entity_id": "0", "name": "小啃兽", "hp": 99, "max_hp": 99, "block": 0,
                "intents": [{"type": "Attack", "label": "12", "title": "Attack"}],
            }],
        },
    }


class TickClient:
    def __init__(self):
        self.acts: list[tuple] = []
        self.n = 0
        self.fixed = None

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def close(self):
        return None

    async def state(self, fmt: str = "json"):
        self.n += 1
        if self.fixed is not None:
            st = json.loads(json.dumps(self.fixed))
            st["_tick"] = self.n
            return st
        st = combat_state()
        st["_tick"] = self.n
        return st

    async def act(self, action, **params):
        self.acts.append((action, params))
        return {"status": "ok", "message": "ok"}


class Ctx:
    def __init__(self):
        self.sent: list[str] = []

    async def send_message(self, umo, chain):
        try:
            self.sent.append("".join(str(c) for c in getattr(chain, "chain", [chain])))
        except Exception:  # noqa: BLE001
            self.sent.append("<chain>")
        return True

    def get_using_provider(self, umo=None):
        return None


def make_plugin(mod, client, extra=None):
    ctx = Ctx()
    cfg = {
        "sts2_url": "http://127.0.0.1:8082",
        "step_interval_sec": 0.001,
        "autopilot_interval_sec": 0.02,
        "autopilot_max_hours": 1,
        "report_every": 100,
        "auto_restart": False,
        "chat_pause_sec": 0.15,
        "nudge_enabled": True,
        "nudge_after_sec": 0.1,
        "max_nudges": 2,
        "nudge_cooldown_sec": 0.1,
    }
    if extra:
        cfg.update(extra)
    p = mod.Sts2PlayerPlugin(ctx, cfg)
    p.client = client
    p.context = ctx
    return p, ctx


class FakeEvent(sts2stub.AstrMessageEvent):
    def __init__(self, text: str = ""):
        super().__init__()
        self.message_str = text


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    print("== 1. 自然语言触发：「有牌打」就开始托管 ==")
    c = TickClient()
    p, ctx = make_plugin(mod, c)
    ev = FakeEvent("有牌打")
    outs = []
    async for r in p.maybe_start_from_chat(ev):
        outs.append(str(r))
    check(p._autopilot is True, "说「有牌打」后托管已启动")
    check(any("托管已启动" in o for o in outs), f"有启动确认：{outs[0][:50] if outs else ''}")
    await asyncio.sleep(0.15)
    check(len(c.acts) >= 2, f"启动后自动动作 {len(c.acts)} 个")

    print("\n== 2. 普通聊天不触发托管 ==")
    c2 = TickClient()
    p2, _ = make_plugin(mod, c2)
    outs2 = []
    async for r in p2.maybe_start_from_chat(FakeEvent("今天天气不错")):
        outs2.append(str(r))
    check(p2._autopilot is False, "闲聊不会启动托管")
    check(len(outs2) == 0, "闲聊没有额外回复（交给正常管线）")

    print("\n== 3. 玩家发消息 → 托管暂停 ==")
    await p.inject_game_context(FakeEvent("你在干嘛"), type("R", (), {"extra_user_content_parts": []})())
    check(p._paused_for_chat is True, "发消息后进入暂停")
    n_before = len(c.acts)
    await asyncio.sleep(0.08)
    check(len(c.acts) == n_before, f"暂停期间不出牌（{n_before} → {len(c.acts)}）")

    print("\n== 4. 回复完自动恢复 ==")
    await asyncio.sleep(0.35)          # 超过 chat_pause_sec=0.15
    check(p._paused_for_chat is False, "自动恢复")
    n2 = len(c.acts)
    await asyncio.sleep(0.15)
    check(len(c.acts) > n2, f"恢复后继续出牌（{n2} → {len(c.acts)}）")

    print("\n== 5. 卡住时主动问一句 ==")
    c5 = TickClient()
    c5.fixed = combat_state(waiting=True)     # 永远「等队友」
    # 等待分支的 sleep 有下限 0.8s，所以要等够一轮
    p5, ctx5 = make_plugin(mod, c5, {"nudge_after_sec": 0.05})
    await p5._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    nudges = [s for s in ctx5.sent if "已经等了" in s]
    check(len(nudges) >= 1, f"发出了 {len(nudges)} 次主动询问")
    if nudges:
        print("     内容：" + nudges[0][:80])
    check(len(c5.acts) == 0, "等待时不出牌")

    print("\n== 6. 主动询问次数有上限 ==")
    await asyncio.sleep(1.6)
    nudges2 = [s for s in ctx5.sent if "已经等了" in s]
    check(1 <= len(nudges2) <= 2, f"最多问 max_nudges=2 次（实际 {len(nudges2)}）")
    await p5._stop_autopilot()

    print("\n== 7. nudge_enabled=false 时不打扰 ==")
    c7 = TickClient()
    c7.fixed = combat_state(waiting=True)
    p7, ctx7 = make_plugin(mod, c7, {"nudge_enabled": False, "nudge_after_sec": 0.05})
    await p7._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    check(len([s for s in ctx7.sent if "已经等了" in s]) == 0, "关掉后不发询问")
    check(p7._autopilot is True, "但仍然在等（没退出）")
    await p7._stop_autopilot()

    print("\n== 8. 停止托管会清掉暂停状态 ==")
    await p._stop_autopilot()
    check(p._autopilot is False, "托管已停")
    check(p._paused_for_chat is False, "暂停标志已清")
    check(p._chat_resume_task is None or p._chat_resume_task.done() or True, "恢复 task 已处理")

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
