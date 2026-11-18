# -*- coding: utf-8 -*-
"""验证「卡住时的主动询问」由模型结合上下文生成。

需求：询问不要是固定模板，要能接上刚才聊的内容。

    python nudge_llm_check.py
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


def combat_state(waiting: bool = True) -> dict:
    return {
        "state_type": "monster", "screen": "COMBAT",
        "available_actions": ["end_turn", "play_card"],
        "run": {"act": 1, "floor": 5, "character": "铁甲战士", "gold": 99},
        "player": {
            "hp": 42, "max_hp": 80, "block": 0, "energy": 0, "max_energy": 3,
            "gold": 99, "hand": [], "potions": [], "relics": [], "deck": [],
        },
        "battle": {
            "round": 3, "turn": "player",
            "is_play_phase": not waiting, "waiting_for_players": waiting,
            "players": [], "lethal": False,
            "enemies": [{
                "entity_id": "0", "name": "毛绒伏地虫", "hp": 47, "max_hp": 123, "block": 0,
                "intents": [{"type": "Attack", "label": "11", "title": "Attack"}],
            }],
        },
    }


class Ctx:
    """带 provider 和 conversation_manager 的上下文桩。"""

    def __init__(self, reply: str | None = "我们继续吧？", history=None, provider_none=False):
        self.sent: list[str] = []
        self.reply = reply
        self.history = history or ["用户: 这把稳吗", "bot: 有点悬，先稳一下"]
        self.calls: list[str] = []
        self._provider = None if provider_none else self
        self.conversation_manager = self

    # --- provider 接口 ---
    async def text_chat(self, prompt: str = "", system_prompt: str = "", **kw):
        self.calls.append(prompt)
        if self.reply is None:
            raise RuntimeError("provider down")
        return type("R", (), {"completion_text": self.reply})()

    # --- conversation_manager 接口 ---
    async def get_curr_conversation_id(self, umo):
        return "conv-1"

    async def get_human_readable_context(self, umo, conv_id, page=1, page_size=10):
        return self.history, len(self.history)

    # --- 消息发送 ---
    async def send_message(self, umo, chain):
        self.sent.append("".join(str(c) for c in getattr(chain, "chain", [chain])))
        return True

    def get_using_provider(self, umo=None):
        return self._provider


class TickClient:
    def __init__(self, waiting=True):
        self.fixed = combat_state(waiting=waiting)
        self.n = 0
        self.acts = []

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def close(self):
        return None

    async def state(self, fmt: str = "json"):
        self.n += 1
        st = json.loads(json.dumps(self.fixed))
        st["_tick"] = self.n
        return st

    async def act(self, action, **params):
        self.acts.append((action, params))
        return {"status": "ok", "message": "ok"}


def make_plugin(mod, client, ctx=None, extra=None):
    ctx = ctx or Ctx()
    cfg = {
        "sts2_url": "http://127.0.0.1:8082",
        "autopilot_interval_sec": 0.02,
        "autopilot_max_hours": 1,
        "nudge_enabled": True,
        "nudge_after_sec": 0.05,
        "max_nudges": 1,
        "nudge_cooldown_sec": 0.1,
        "nudge_use_llm": True,
    }
    if extra:
        cfg.update(extra)
    p = mod.Sts2PlayerPlugin(ctx, cfg)
    p.client = client
    p.context = ctx
    return p, ctx


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    print("== 1. 模型生成的询问被发出去（不是固定模板）==")
    ctx = Ctx(reply="卡在等你出牌呢，要不你先手？")
    p, _ = make_plugin(mod, TickClient(), ctx)
    await p._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    await p._stop_autopilot()
    check(len(ctx.calls) >= 1, f"调用了模型 {len(ctx.calls)} 次")
    sent = [s for s in ctx.sent if s]
    check(len(sent) >= 1, f"发出了 {len(sent)} 条通知")
    if sent:
        check("卡在等你出牌" in sent[0], f"发的是模型生成的内容：{sent[0][:60]}")
    if ctx.calls:
        prompt = ctx.calls[0]
        check("最近的聊天记录" in prompt, "prompt 里带了聊天记录")
        check("这把稳吗" in prompt, "聊天记录内容确实传进去了")
        check("当前局面" in prompt, "prompt 里带了当前局面")
        check("毛绒伏地虫" in prompt, "局面细节传进去了")

    print("\n== 2. 模型返回空 → 回退固定文案 ==")
    ctx2 = Ctx(reply="")
    p2, _ = make_plugin(mod, TickClient(), ctx2)
    await p2._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    await p2._stop_autopilot()
    sent2 = [s for s in ctx2.sent if s]
    check(len(sent2) >= 1, f"仍有通知（{len(sent2)} 条）")
    if sent2:
        check("已经等了" in sent2[0], f"回退文案：{sent2[0][:60]}")

    print("\n== 3. 模型抛异常 → 回退固定文案，不影响托管 ==")
    ctx3 = Ctx(reply=None)     # text_chat 抛异常
    p3, _ = make_plugin(mod, TickClient(), ctx3)
    await p3._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    running = p3._autopilot
    await p3._stop_autopilot()
    sent3 = [s for s in ctx3.sent if s]
    check(len(sent3) >= 1, f"仍有通知（{len(sent3)} 条）")
    if sent3:
        check("已经等了" in sent3[0], "回退到固定文案")
    check(running is True, "托管循环没被模型异常搞挂")

    print("\n== 4. nudge_use_llm=false → 完全不调模型 ==")
    ctx4 = Ctx(reply="不该用到")
    p4, _ = make_plugin(mod, TickClient(), ctx4, {"nudge_use_llm": False})
    await p4._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    await p4._stop_autopilot()
    check(len(ctx4.calls) == 0, f"没有调用模型（{len(ctx4.calls)} 次）")
    sent4 = [s for s in ctx4.sent if s]
    check(len(sent4) >= 1 and "已经等了" in sent4[0], "发的是固定文案")

    print("\n== 5. 没有 provider 时也能工作 ==")
    ctx5 = Ctx(provider_none=True)
    p5, _ = make_plugin(mod, TickClient(), ctx5)
    await p5._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    await p5._stop_autopilot()
    sent5 = [s for s in ctx5.sent if s]
    check(len(sent5) >= 1, f"无 provider 仍发通知（{len(sent5)} 条）")
    if sent5:
        check("已经等了" in sent5[0], "回退固定文案")

    print("\n== 6. 模型给出带引号/前缀的输出会被清理 ==")
    ctx6 = Ctx(reply='回复：等了挺久了，要不要先歇会儿？')
    p6, _ = make_plugin(mod, TickClient(), ctx6)
    await p6._start_autopilot("test:umo")
    await asyncio.sleep(1.6)
    await p6._stop_autopilot()
    sent6 = [s for s in ctx6.sent if s]
    check(len(sent6) >= 1, f"有通知（{len(sent6)} 条）")
    if sent6:
        check(not sent6[0].startswith("回复："), f"前缀已清理：{sent6[0][:50]}")

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
