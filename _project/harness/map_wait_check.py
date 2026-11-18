# -*- coding: utf-8 -*-
"""验证「多人地图等别人投票」不会被误判成「状态卡住」。

真机现场（2026-11-18 11:35）：
  /sts2 自动 10
  → STS2 后端识别为：agent
  → 7.5 秒后「状态卡住没变化，先停下」

原因：队友已投票 → 规则层返回 wait（这是修好重复投票后的正确行为）→
状态确实不变 → 触发 same_count>=8 的「卡住」判定 → 停机。

修复后：地图上「已投票」归入 waiting（不消耗步数、不判卡住），
并且等太久（>90 次）会给出「对面可能没在操作」的明确提示。

    python map_wait_check.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"   # 仓库根的插件本体

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  {'✓' if ok else '✗'} {label}" + (f"  — {detail}" if detail and not ok else ""))


class MapWaitClient:
    """永远返回「已投票、等别人」的地图状态，记录动作调用。"""

    def __init__(self, repeat: int = 20):
        self.repeat = repeat
        self.i = 0
        self.act_calls: list[tuple] = []

    async def detect(self):
        return "agent"

    async def health(self):
        return True

    async def close(self):
        return None

    async def state(self, fmt: str = "json"):
        self.i += 1
        return {
            "state_type": "map",
            "screen": "MAP",
            "available_actions": ["choose_map_node"],
            "run": {"act": 1, "floor": 0, "character": "铁甲战士", "gold": 99},
            "player": {"hp": 80, "max_hp": 80, "gold": 99},
            "map": {
                "current_position": {},
                # 已投票后 available_nodes 通常为空，这里留一个模拟「还能改票」
                "next_options": [{"index": 0, "row": 0, "col": 3, "type": "Monster"}],
                "boss": {},
                "can_vote": True,
                "local_vote": {"row": 0, "col": 3},
                "voted_player_ids": ["8"],
            },
        }

    async def act(self, action, **params):
        self.act_calls.append((action, params))
        return {"status": "ok", "message": "ok"}


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    print("== 1. 地图等待时不应重复投票 ==")
    client = MapWaitClient()
    plugin = mod.Sts2PlayerPlugin(
        sts2stub.StubContext(sts2stub.ScriptedProvider()),
        {"max_steps": 10, "step_interval_sec": 0.01, "report_every": 100},
    )
    plugin.client = client
    event = sts2stub.AstrMessageEvent()

    msgs = []
    async for m in plugin._auto(event, 10):
        msgs.append(str(m))

    votes = [a for a in client.act_calls if a[0] == "choose_map_node"]
    check(len(votes) == 0, f"没有重复投票（调用了 {len(votes)} 次）")
    check(
        not any("状态卡住" in m for m in msgs),
        "没有被误判成「状态卡住」",
        " | ".join(m.splitlines()[0] for m in msgs)[:150],
    )
    joined = " ".join(msgs)
    print(f"     插件输出首行：{msgs[0].splitlines()[0] if msgs else '(无)'}")

    print("\n== 2. 等太久要给出「对面没在操作」的提示 ==")
    # 用 limit=90 的等待上限，interval 极小以便快速跑到
    client2 = MapWaitClient()
    plugin2 = mod.Sts2PlayerPlugin(
        sts2stub.StubContext(sts2stub.ScriptedProvider()),
        {"max_steps": 10, "step_interval_sec": 0.001, "report_every": 100},
    )
    plugin2.client = client2
    # 把 sleep 缩短，避免真的等 90 秒
    orig_sleep = asyncio.sleep

    async def fast_sleep(_t):
        await orig_sleep(0)

    asyncio.sleep = fast_sleep  # type: ignore[assignment]
    try:
        msgs2 = []
        async for m in plugin2._auto(sts2stub.AstrMessageEvent(), 10):
            msgs2.append(str(m))
            if "等太久" in str(m):
                break
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]

    hit = any("等太久" in m for m in msgs2)
    check(hit, "超时后提示「在地图上等别人投票等太久了」",
          " | ".join(m.splitlines()[0] for m in msgs2)[:150])

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
