# -*- coding: utf-8 -*-
"""专门验证多人战斗里的「动作串行」窗口。

问题：一方刚出完牌，另一方立刻出牌会不会被
      invalid_action: Action is not available in the current state 拒掉？

顺序很重要：
  --order comp-first  队友先出（模拟 AstrBot 驱动队友的那一天）
  --order host-first  人类先出（模拟真人玩家先手，队友后手）

每组都试两种间隔，看拒绝率。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"


async def one(client, mod, st, label: str):
    bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6, card_min=18.0)
    act = bot.next_action(st)
    if not act or act.get("action") in (None, "wait", "sleep"):
        return "none", act
    name = act["action"]
    params = {k: v for k, v in act.items() if k not in ("action", "tool", "think", "reason")}
    res = await client.act(name, **params)
    return str(res.get("status")), (name, params, res.get("error") or res.get("message"))


async def main(args) -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    host = mod.Sts2Client(args.host, timeout=25.0)
    comp = mod.Sts2Client(args.comp, timeout=25.0)
    await host.detect()
    await comp.detect()

    first, second = (comp, host) if args.order == "comp-first" else (host, comp)
    fl, sl = ("COMP", "HOST") if args.order == "comp-first" else ("HOST", "COMP")

    stats = {"ok": 0, "err": 0, "other": 0}
    for i in range(args.rounds):
        hs = await host.state()
        cs = await comp.state()
        if hs.get("screen") != "COMBAT" or cs.get("screen") != "COMBAT":
            print(f"[{i}] 不在战斗（host={hs.get('screen')} comp={cs.get('screen')}），停")
            break
        hb, cb = hs.get("battle") or {}, cs.get("battle") or {}
        if not (hb.get("is_play_phase") and cb.get("is_play_phase")):
            await asyncio.sleep(1.0)
            continue

        st1 = cs if fl == "COMP" else hs
        st2 = hs if sl == "HOST" else cs
        s1, r1 = await one(first, mod, st1, fl)
        if args.gap:
            await asyncio.sleep(args.gap)
        s2, r2 = await one(second, mod, st2, sl)

        print(f"[{i}] {fl} -> {s1} {r1}\n     {sl} -> {s2} {r2}", flush=True)
        for s in (s1, s2):
            if s in ("ok",):
                stats["ok"] += 1
            elif s == "error":
                stats["err"] += 1
            else:
                stats["other"] += 1
        await asyncio.sleep(args.interval)

    print(f"\n统计：{stats}（顺序 {args.order}，间隔 {args.gap}s）")
    await host.close()
    await comp.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://127.0.0.1:8081")
    p.add_argument("--comp", default="http://127.0.0.1:8082")
    p.add_argument("--order", choices=["comp-first", "host-first"], default="host-first")
    p.add_argument("--gap", type=float, default=0.0, help="第一方动作后到第二方动作之间的等待")
    p.add_argument("--rounds", type=int, default=12)
    p.add_argument("--interval", type=float, default=0.6)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a)))
