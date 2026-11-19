# -*- coding: utf-8 -*-
"""验证 sts2_autopilot 工具（让主 LLM 自己决定接手托管）。

用户需求原话：
  「我希望的效果是，这个 bot 和我在对话的时候，我提到了我们要去打牌了，
   她能自己调用工具看到情况，然后接着继续开打」

也就是：不靠固定触发词，由模型判断意图后自己调 sts2_autopilot 接手。

    python llm_autopilot_check.py
"""

from __future__ import annotations

import asyncio
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


class FakeClient:
    """假的 STS2 客户端：state 直接返回给定局面，不碰网络。"""

    def __init__(self, st: dict | None = None):
        self._st = st or {
            "screen": "MAP",
            "state_type": "map",
            "available_actions": ["choose_map_node"],
            "run": {"floor": 6, "character_id": "IRONCLAD"},
        }
        self.closed = False

    async def state(self, fmt: str = "json") -> dict:
        return self._st

    async def act(self, action: str, **params):
        return {"status": "ok", "message": "Action completed."}

    async def detect(self) -> str:
        return "agent"

    async def health(self) -> bool:
        return True

    async def close(self) -> None:
        self.closed = True


def build(cfg_extra: dict | None = None, st: dict | None = None):
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    provider = sts2stub.ScriptedProvider()
    cfg = {
        "sts2_url": "http://127.0.0.1:8082",
        "operator_ids": [],
        "autopilot_from_chat": True,
        "autopilot_interval_sec": 0.3,
        "use_llm": False,
        "llm_combat_plan": False,
    }
    if cfg_extra:
        cfg.update(cfg_extra)
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(provider), cfg)
    plugin.client = FakeClient(st)
    return mod, plugin, provider


async def main() -> int:
    print("== 1. 私聊里调用 → 启动托管 ==")
    mod, p, _ = build()
    ev = sts2stub.AstrMessageEvent(is_private=True)
    out = await p.tool_sts2_autopilot(ev, reason="玩家说继续和我一起打")
    check("托管" in out or "✅" in out, f"返回启动提示：{out[:60]!r}")
    check(p._autopilot is True, "_autopilot 已置 True")
    check(p._autopilot_task is not None, "后台 task 已创建")
    await p._stop_autopilot(quiet=True)
    check(p._autopilot is False, "停止后 _autopilot 为 False")

    print("\n== 2. 群里调用 → 拒绝 ==")
    _, p2, _ = build()
    ev2 = sts2stub.AstrMessageEvent(is_private=False)
    out2 = await p2.tool_sts2_autopilot(ev2)
    check(p2._autopilot is False, "群聊不启动托管")
    check("私聊" in out2, f"提示只在私聊：{out2[:50]!r}")

    print("\n== 3. 没权限的用户 → 拒绝 ==")
    _, p3, _ = build({"operator_ids": ["99999"]})
    ev3 = sts2stub.AstrMessageEvent(sender_id="12345", is_private=True)
    out3 = await p3.tool_sts2_autopilot(ev3)
    check(p3._autopilot is False, "非 operator 不启动")
    check("权限" in out3, f"提示无权限：{out3[:50]!r}")

    print("\n== 4. 配置关掉 autopilot_from_chat → 拒绝 ==")
    _, p4, _ = build({"autopilot_from_chat": False})
    ev4 = sts2stub.AstrMessageEvent(is_private=True)
    out4 = await p4.tool_sts2_autopilot(ev4)
    check(p4._autopilot is False, "开关关闭时不启动")
    check("关掉" in out4 or "无法" in out4, f"提示已关闭：{out4[:60]!r}")

    print("\n== 5. 重复调用不重复启动 ==")
    _, p5, _ = build()
    ev5 = sts2stub.AstrMessageEvent(is_private=True)
    await p5.tool_sts2_autopilot(ev5)
    task1 = p5._autopilot_task
    out5 = await p5.tool_sts2_autopilot(ev5)
    check(p5._autopilot_task is task1, "task 未被替换")
    check("已经在跑" in out5, f"提示已在跑：{out5[:50]!r}")
    await p5._stop_autopilot(quiet=True)

    print("\n== 6. 注入的上下文里带 sts2_hint（模型才知道有这个工具） ==")
    mod6, p6, _ = build()
    captured: list[str] = []

    class Req:
        def __init__(self):
            self.extra_user_content_parts: list = []

    req = Req()

    async def fake_state():
        return {"screen": "MAP", "state_type": "map", "run": {"floor": 6}}

    p6.client.state = fake_state
    await p6.inject_game_context(sts2stub.AstrMessageEvent(is_private=True), req)
    joined = " ".join(str(getattr(x, "text", x)) for x in req.extra_user_content_parts)
    check("sts2_game_context" in joined, "注入了对局上下文")
    check("sts2_autopilot" in joined, "提示里提到了 sts2_autopilot")
    check("继续和我一起打" in joined, "提示里给了自然语言例子")

    print("\n== 7. 托管已在跑时不再注入 hint（省 token） ==")
    _, p7, _ = build()
    p7._autopilot = True
    req7 = Req()

    async def fake_state7():
        return {"screen": "MAP", "state_type": "map", "run": {"floor": 6}}

    p7.client.state = fake_state7
    p7._paused_for_chat = True
    await p7.inject_game_context(sts2stub.AstrMessageEvent(is_private=True), req7)
    joined7 = " ".join(str(getattr(x, "text", x)) for x in req7.extra_user_content_parts)
    check("sts2_hint" not in joined7, "托管中不注入 hint")
    check("sts2_game_context" in joined7, "但仍注入战况")

    print("\n== 8. 游戏连不上时工具给出人话提示 ==")

    class BadClient(FakeClient):
        async def state(self, fmt: str = "json") -> dict:
            raise RuntimeError("connection refused")

    _, p8, _ = build()
    p8.client = BadClient()
    out8 = await p8.tool_sts2_autopilot(sts2stub.AstrMessageEvent(is_private=True))
    check(isinstance(out8, str) and len(out8) > 0, f"没崩，返回：{out8[:70]!r}")

    print()
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"=== {passed}/{total} 通过 ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
