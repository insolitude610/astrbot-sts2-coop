# -*- coding: utf-8 -*-
"""真机监控探针：盯端口 8081/8082 的 /health，起来了就打印摘要。

用途：你拉游戏实例，我这边不需要反复手敲 probe——
脚本会一直轮询，哪个端口先通就立刻打印后端身份和当前局面。

    python watch_live.py                 # 一直盯，直到两边都通或超时
    python watch_live.py --timeout 600   # 最多等 10 分钟
    python watch_live.py --once          # 只看一眼，不通就退出
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import aiohttp  # noqa: E402

PORTS = (8081, 8082)


async def probe(port: int, timeout: float = 3.0) -> dict | None:
    url = f"http://127.0.0.1:{port}/health"
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                return await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
        return None


def is_agent(health: dict | None) -> bool:
    if not isinstance(health, dict):
        return False
    inner = health.get("data") or {}
    return str(inner.get("service", "")).startswith("sts2-ai-agent")


def summarize(port: int, health: dict) -> str:
    inner = health.get("data") or {}
    keys = (
        "service",
        "mod_version",
        "game_version",
        "status",
        "api_port",
        "instance_role",
        "play_running",
        "play_phase",
        "mcp_enabled",
    )
    body = "  ".join(
        f"{k}={inner[k]}" for k in keys if k in inner
    )
    return f"[{port}] {body or json.dumps(inner, ensure_ascii=False)[:300]}"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    seen: dict[int, dict] = {}
    loops = 0
    while True:
        loops += 1
        for port in PORTS:
            if port in seen:
                continue
            h = await probe(port)
            if h is None:
                continue
            seen[port] = h
            tag = "AGENT" if is_agent(h) else "非 AGENT"
            print(f"\n{'='*70}")
            print(f"端口 {port} 通了（{tag}）")
            print(summarize(port, h))
            print("=" * 70, flush=True)

        if args.once:
            if not seen:
                print("两个端口都不通", flush=True)
                return 2
            return 0

        if len(seen) >= len(PORTS):
            print("\n两个实例都起来了。", flush=True)
            return 0

        if loops * args.interval >= args.timeout:
            up = sorted(seen)
            print(
                f"\n等待超时。已通：{up or '无'}；"
                f"未通：{[p for p in PORTS if p not in seen]}",
                flush=True,
            )
            return 1

        await asyncio.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
