# -*- coding: utf-8 -*-
"""端到端验收：用**打了补丁的插件真实代码路径**驱动队友，主机侧模拟真人。

模拟的是交付场景：
  · 主机由「真人」操作（这里脚本用朴素策略点，只为把对局推进下去）；
  · 队友由插件 `_auto` 驱动 —— 和 QQ 里发 `/sts2 自动 N` 走的是同一条代码路径。

验收点：
  1. 多人地图：主机投票后队友也能投票，对局能继续推进（不再卡在地图）
  2. 多人战斗：队友出牌不被 invalid_action 卡死（补丁的退避重试生效）
  3. 队友结束回合后能正确「等队友」，不把步数预算耗光
  4. 奖励 / 营火 / 商店这些非战斗界面同样能推进

    python e2e.py --steps 80
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"   # 仓库根的插件本体


class SilentEvent(sts2stub.AstrMessageEvent):
    """主机的「真人」不需要看到长报告，只统计。"""


async def human(host, mod) -> None:
    """主机侧：朴素规则，能点就点，目的是让对局往前走。"""
    try:
        st = await host.state()
    except Exception:  # noqa: BLE001
        return
    bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6, card_min=18.0)
    act = bot.next_action(st)
    if not act or act.get("action") in (None, "wait", "sleep"):
        return
    params = {k: v for k, v in act.items() if k not in ("action", "tool", "think", "reason")}
    try:
        await host.act(act["action"], **params)
    except Exception:  # noqa: BLE001
        pass


async def main(args) -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    host = mod.Sts2Client(args.host, timeout=25.0)
    await host.detect()

    provider = sts2stub.ScriptedProvider()
    plugin = mod.Sts2PlayerPlugin(
        sts2stub.StubContext(provider),
        {
            "sts2_url": args.comp,
            "sts2_timeout_sec": 25,
            "operator_ids": [],
            "max_steps": args.steps,
            "step_interval_sec": 0.45,
            "report_every": 10,
            "use_llm": False,
            "potion_hp_ratio": 0.32,
            "block_priority": 0.6,
            "card_min": 18,
            "auto_restart": False,
        },
    )
    event = SilentEvent()
    screens: Counter[str] = Counter()
    turns = set()
    retry_hits = 0

    async def feed_companion():
        nonlocal retry_hits
        async for msg in plugin._auto(event, args.steps):
            text = str(msg)
            if "重试" in text or "↻" in text:
                retry_hits += 1
            if args.verbose:
                print("  [队友]", text.splitlines()[0][:110], flush=True)

    comp_task = asyncio.create_task(feed_companion())
    while not comp_task.done():
        await human(host, mod)
        try:
            st = await plugin.client.state()
            screens[str(st.get("state_type"))] += 1
            b = st.get("battle") or {}
            if b.get("round"):
                turns.add(b["round"])
        except Exception:  # noqa: BLE001
            pass
        if not args.verbose:
            print(".", end="", flush=True)
        await asyncio.sleep(args.interval)

    try:
        await comp_task
    except Exception as e:  # noqa: BLE001
        print(f"\n队友循环异常：{e}")

    print("\n\n=== 验收结果 ===")
    print(f"队友经过的界面：{dict(screens)}")
    print(f"经历的战斗轮次：{sorted(turns)}")
    print(f"触发重试提示次数：{retry_hits}")

    for base, label in ((args.host, "HOST"), (args.comp, "COMP")):
        c = mod.Sts2Client(base, timeout=25.0)
        try:
            st = await c.state()
            print(f"\n=== {label} 最终 ===\n" + mod.render_state(st))
        finally:
            await c.close()
    await host.close()
    await plugin.client.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://127.0.0.1:8081")
    p.add_argument("--comp", default="http://127.0.0.1:8082")
    p.add_argument("--steps", type=int, default=60)
    p.add_argument("--interval", type=float, default=0.5)
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a)))
