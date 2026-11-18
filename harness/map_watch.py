# -*- coding: utf-8 -*-
"""盯住地图界面：把「有 available_actions 但没有 available_nodes」的瞬间抓下来。

用来验证假设：多人地图里本方投完票后，available_nodes 变空，但
available_actions 里仍然有 choose_map_node —— 规则层看到空列表就以为「不认识这个界面」，
于是整局停下（这是真机上复现到的卡点）。

    python map_watch.py --seconds 40
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

import aiohttp  # noqa: E402

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"


async def get(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
            return await r.json()
    except Exception:  # noqa: BLE001
        return None


async def main(args) -> int:
    seen = 0
    async with aiohttp.ClientSession() as s:
        for i in range(int(args.seconds / args.interval)):
            for port in (args.host_port, args.comp_port):
                data = await get(s, f"http://127.0.0.1:{port}/state")
                if not data:
                    continue
                d = data.get("data") or {}
                if d.get("screen") != "MAP":
                    continue
                m = d.get("map") or {}
                av = d.get("available_actions") or []
                nodes = m.get("available_nodes") or []
                mp = d.get("multiplayer") or {}
                tag = "WAIT-VOTE" if (av and not nodes) else "OK"
                if tag == "WAIT-VOTE":
                    seen += 1
                print(
                    f"[{i}] :{port} role={(mp.get('net_game_type'))} "
                    f"avail={av} nodes={len(nodes)} "
                    f"local_vote={m.get('local_vote')} "
                    f"votes={[ (v.get('player_id'), v.get('coord')) for v in (m.get('player_votes') or []) ]} "
                    f"=> {tag}",
                    flush=True,
                )
            await asyncio.sleep(args.interval)
    print(f"\n共捕获 WAIT-VOTE 快照 {seen} 次")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host-port", type=int, default=8081)
    p.add_argument("--comp-port", type=int, default=8082)
    p.add_argument("--seconds", type=float, default=40)
    p.add_argument("--interval", type=float, default=0.7)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a)))
