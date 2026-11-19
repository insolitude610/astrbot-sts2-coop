# -*- coding: utf-8 -*-
"""真机联调：用插件真实代码路径驱动队友实例（8082），每步打印决策与结果。

    python live_drive.py --steps 5
    python live_drive.py --once          # 只走一步
    python live_drive.py --state         # 只看状态不动作
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"
BASE = "http://127.0.0.1:8082"


def build(cfg_extra: dict | None = None):
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    provider = sts2stub.ScriptedProvider()
    cfg = {
        "sts2_url": BASE,
        "sts2_timeout_sec": 25,
        "operator_ids": [],
        "max_steps": 60,
        "step_interval_sec": 0.4,
        "report_every": 1,
        "use_llm": False,          # 规则层，不烧 token
        "llm_combat": False,
        "llm_combat_plan": False,
        "potion_hp_ratio": 0.32,
        "block_priority": 0.6,
        "card_min": 18,
        "auto_restart": False,
    }
    if cfg_extra:
        cfg.update(cfg_extra)
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(provider), cfg)
    return mod, plugin, provider


def brief(st: dict) -> str:
    stype = st.get("state_type") or st.get("screen")
    parts = [f"screen={stype}"]
    run = st.get("run") or {}
    if run.get("floor"):
        parts.append(f"floor={run['floor']}")
    b = st.get("battle") or {}
    if b:
        parts.append(f"play_phase={b.get('is_play_phase')}")
        if b.get("energy") is not None:
            parts.append(f"energy={b.get('energy')}")
        hp = b.get("player_hp")
        if hp is not None:
            parts.append(f"hp={hp}")
    m = st.get("map") or {}
    if m.get("local_vote") is not None:
        parts.append(f"local_vote={m.get('local_vote')}")
    return "  ".join(parts)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--state", action="store_true")
    args = ap.parse_args()

    mod, plugin, provider = build()

    mode = await plugin.client.detect()
    ok = await plugin.client.health()
    print(f"后端识别: {mode}   健康: {ok}   LLM 调用: {provider.calls}", flush=True)

    st = await plugin.client.state()
    print(f"当前状态: {brief(st)}", flush=True)
    if args.state:
        print(json.dumps(st, ensure_ascii=False)[:2500])
        return 0

    steps = 1 if args.once else args.steps
    for i in range(steps):
        st = await plugin.client.state()
        before = brief(st)
        act = plugin.bot.next_action(st)
        if not act:
            print(f"[{i+1}] 无动作（{before}）", flush=True)
            await asyncio.sleep(1.0)
            continue
        name = act.get("action")
        params = {
            k: v
            for k, v in act.items()
            if k not in ("action", "tool", "think", "reason")
        }
        print(f"[{i+1}] {before}\n      -> {name} {params}", flush=True)
        if name in ("wait", "sleep", ""):
            await asyncio.sleep(1.0)
            continue
        try:
            res = await plugin.client.act(name, **params)
            status = (res or {}).get("status") or (res or {}).get("message") or res
            print(f"      结果: {str(status)[:200]}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"      失败: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(1.2)

    st = await plugin.client.state()
    print(f"\n结束状态: {brief(st)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
