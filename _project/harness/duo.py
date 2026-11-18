# -*- coding: utf-8 -*-
"""双人协同驱动：主机（人类位）也交给规则层，专为「验证多人语义」用。

真实玩法里主机是你自己；这里让脚本替主机点，是因为多人战斗要双方都结束回合
才会推进，不点就永远验证不到第 2 轮以后。

    python duo.py --steps 40 --host http://127.0.0.1:8081 --comp http://127.0.0.1:8082

每条 battle 判定都会打印两边的 action_readiness，方便定位「卡在等谁」。
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


class Driver:
    """一个实例的规则层驱动（复用插件真实代码路径）。"""

    def __init__(self, mod, base: str, label: str):
        self.label = label
        self.client = mod.Sts2Client(base, timeout=25.0)
        self.bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6, card_min=18.0)
        self.last_sig = ""
        self.stuck = 0

    async def state(self):
        return await self.client.state()

    async def act(self, action: dict):
        name = str(action.get("action") or "")
        params = {k: v for k, v in action.items() if k not in ("action", "tool", "think", "reason")}
        if name in ("", "wait", "sleep"):
            return {"status": "wait"}
        return await self.client.act(name, **params)

    async def close(self):
        await self.client.close()


def signature(st: dict) -> str:
    b = st.get("battle") or {}
    p = st.get("player") or {}
    return "|".join(
        str(x)
        for x in (
            st.get("screen"),
            b.get("round"),
            p.get("hp"),
            p.get("energy"),
            len(p.get("hand") or []),
            sum(1 for e in (b.get("enemies") or []) if (e.get("hp") or 0) > 0),
        )
    )


async def readiness(d: Driver) -> dict:
    st = await d.client.state()
    return st


async def main(args) -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    hosts = Driver(mod, args.host, "HOST")
    comp = Driver(mod, args.comp, "COMP")
    await hosts.client.detect()
    await comp.client.detect()

    for i in range(args.steps):
        sts = {}
        for d, key in ((hosts, "host"), (comp, "comp")):
            try:
                sts[key] = await d.state()
            except Exception as e:  # noqa: BLE001
                print(f"[{i}] {d.label} 读状态失败：{e}")
                sts[key] = None

        hs, cs = sts.get("host"), sts.get("comp")
        if hs is None or cs is None:
            await asyncio.sleep(1.0)
            continue

        screen = hs.get("screen")
        hb = (hs.get("battle") or {})
        cb = (cs.get("battle") or {})
        print(
            f"[{i}] screen={screen} round={hb.get('round')} "
            f"HP host={(hs.get('player') or {}).get('hp')} comp={(cs.get('player') or {}).get('hp')} "
            f"| play host={hb.get('is_play_phase')} comp={cb.get('is_play_phase')} "
            f"| avail host={hs.get('available_actions')} comp={cs.get('available_actions')}",
            flush=True,
        )

        acted = False
        for d, st in ((comp, cs), (hosts, hs)):
            if not st.get("available_actions") and not (
                st.get("battle") or {}
            ).get("is_play_phase"):
                continue
            one = d.bot.next_action(st)
            if not one:
                continue
            try:
                res = await d.act(one)
            except Exception as e:  # noqa: BLE001
                print(f"    {d.label} {one} -> 异常 {e}")
                continue
            status = str(res.get("status"))
            print(f"    {d.label} {one.get('action')} -> {status} {str(res.get('message') or res.get('error') or '')[:80]}")
            acted = True

        if not acted:
            await asyncio.sleep(args.interval)
        else:
            await asyncio.sleep(args.interval)

        if screen in ("GAME_OVER",):
            print("对局结束")
            break

    for d in (hosts, comp):
        st = None
        try:
            st = await d.state()
        except Exception:  # noqa: BLE001
            pass
        await d.close()
        if st:
            print(f"\n=== {d.label} 最终 ===\n" + mod.render_state(st))
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://127.0.0.1:8081")
    p.add_argument("--comp", default="http://127.0.0.1:8082")
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--interval", type=float, default=0.8)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a)))
