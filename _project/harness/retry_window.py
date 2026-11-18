# -*- coding: utf-8 -*-
"""量化「队友读到的状态已经过期」这个窗口：出牌失败后隔多久重试能成功。

结论用途：AstrBot 插件在多人局里必须对 invalid_action / action_in_flight 做
带退避的**重试**，而不是当成硬错误累计（现有实现累计 3 次就整局停下）。

    python retry_window.py --comp http://127.0.0.1:8082 --host http://127.0.0.1:8081
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"   # 仓库根的插件本体

RETRYABLE = ("invalid_action", "action_in_flight")


async def sync_round(host, comp, mod) -> bool:
    """把两边推到「同一次战斗、双方都可行动」的状态。

    多人语义：一方 end_turn 之后自己就不能再动了，直到所有人都结束回合。
    所以一方已经结束回合时，让另一方也结束，等下一轮重新开始。
    """
    for _ in range(80):
        try:
            hs, cs = await host.state(), await comp.state()
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.6)
            continue
        if hs.get("screen") != "COMBAT" or cs.get("screen") != "COMBAT":
            # 不在战斗就往前推（奖励/地图/宝箱…）
            for c, s in ((host, hs), (comp, cs)):
                bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6)
                a = bot.next_action(s)
                if a and a.get("action") not in (None, "wait", "sleep"):
                    p = {k: v for k, v in a.items() if k != "action"}
                    try:
                        await c.act(a["action"], **p)
                    except Exception:  # noqa: BLE001
                        pass
            await asyncio.sleep(0.7)
            continue

        hp_ = (hs.get("battle") or {}).get("is_play_phase")
        cp_ready = (cs.get("battle") or {}).get("is_play_phase")
        if hp_ and cp_ready:
            return True

        # 有一方已经结束回合：让另一方也结束，推进到下一轮
        for c, s, ready in ((host, hs, hp_), (comp, cs, cp_ready)):
            if ready:
                try:
                    await c.act("end_turn")
                except Exception:  # noqa: BLE001
                    pass
        await asyncio.sleep(1.0)
    return False


async def main(args) -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    host = mod.Sts2Client(args.host, timeout=25.0)
    comp = mod.Sts2Client(args.comp, timeout=25.0)
    await host.detect()
    await comp.detect()

    # 先把两边推到同一场战斗里（旧的粗推进保留作兜底，sync_round 负责精确对齐）
    await sync_round(host, comp, mod)

    delays = [0.0, 0.15, 0.3, 0.5, 0.8, 1.2]
    results: dict[float, list[str]] = {d: [] for d in delays}

    for trial in range(args.trials):
        if not await sync_round(host, comp, mod):
            print("推不到「双方都可行动」的战斗，收工")
            break
        hs, cs = await host.state(), await comp.state()
        hb, cb = hs.get("battle") or {}, cs.get("battle") or {}
        if hs.get("screen") != "COMBAT" or not (hb.get("is_play_phase") and cb.get("is_play_phase")):
            print("不在双方可行动的战斗里，结束")
            break

        # 人类先出一张牌，制造「队友手里的快照已过期」
        hbot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6)
        ha = hbot.next_action(hs)
        if not ha or ha.get("action") in (None, "wait", "sleep"):
            await asyncio.sleep(0.5)
            continue
        hp_ = {k: v for k, v in ha.items() if k != "action"}
        await host.act(ha["action"], **hp_)

        # 队友用**刚才读到的旧快照**立刻出牌，然后按不同延迟重试
        cbot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6)
        ca = cbot.next_action(cs)
        if not ca or ca.get("action") not in ("play_card",):
            await asyncio.sleep(0.5)
            continue
        cp = {k: v for k, v in ca.items() if k != "action"}

        delay = delays[trial % len(delays)]
        if delay:
            await asyncio.sleep(delay)
        res = await comp.act(ca["action"], **cp)
        status = str(res.get("status"))
        err = str(res.get("error") or "")
        kind = "ok" if status == "ok" else ("retryable" if any(k in err for k in RETRYABLE) else "other")
        results[delay].append(kind)
        print(f"[{trial}] delay={delay}s -> {status} {kind} {err[:70]}", flush=True)
        await asyncio.sleep(0.7)

    print("\n延迟 → 成功/可重试/其它")
    for d in delays:
        r = results[d]
        if not r:
            continue
        ok = sum(1 for x in r if x == "ok")
        rt = sum(1 for x in r if x == "retryable")
        ot = sum(1 for x in r if x == "other")
        print(f"  {d:>4}s : ok={ok} retryable={rt} other={ot}  (n={len(r)})")

    await host.close()
    await comp.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://127.0.0.1:8081")
    p.add_argument("--comp", default="http://127.0.0.1:8082")
    p.add_argument("--trials", type=int, default=18)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a)))
