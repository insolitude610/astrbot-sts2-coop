# -*- coding: utf-8 -*-
"""单点验证：把当前状态喂给规则层，看它到底会做什么（不实际发动作）。

专门用来复现 / 验证多人局卡点，比如「地图投票后规则层返回 None 导致整局停下」。

    python rule_check.py --base http://127.0.0.1:8082
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

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"


async def main(args) -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    client = mod.Sts2Client(args.base, timeout=25.0)
    await client.detect()
    raw = None
    try:
        st = await client.state()
    except Exception as e:  # noqa: BLE001
        print(f"读状态失败：{e}")
        await client.close()
        return 1

    print(f"state_type={st.get('state_type')} screen={st.get('screen')}")
    print(f"available_actions={st.get('available_actions')}")
    if st.get("map"):
        m = st["map"]
        print(f"map.next_options={json.dumps(m.get('next_options'), ensure_ascii=False)}")
        print(f"map.can_vote={m.get('can_vote')} local_vote={m.get('local_vote')} "
              f"voted={m.get('voted_player_ids')}")
    if st.get("battle"):
        b = st["battle"]
        print(f"battle: round={b.get('round')} play={b.get('is_play_phase')} "
              f"wait_players={b.get('waiting_for_players')} players={b.get('players')}")

    bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6, card_min=18.0)
    act = bot.next_action(st)
    print(f"\n规则层决定：{act}")

    print("\n--- 渲染 ---")
    print(mod.render_state(st))

    await client.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8082")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a)))
