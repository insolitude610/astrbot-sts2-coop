# -*- coding: utf-8 -*-
"""用 AstrBot 里「部署的那份 main.py」+「真实配置文件」跑托管循环。

和 live_drive.py 的区别：
  · live_drive 加载仓库根的 main.py，配置是脚本里写死的
  · 本脚本加载 AstrBot 实际部署的插件，配置读 AstrBot 的真实 json

这样能验证「AstrBot 实际加载的那份代码 + 实际那份配置」能不能驱动 8082，
唯一差别只剩 AstrBot 的事件循环本身（这里用 asyncio.run 模拟）。

    python plugin_live.py --state       # 只看状态
    python plugin_live.py --once        # 走一步
    python plugin_live.py --autopilot 30   # 跑托管循环 30 秒
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

ASTRBOT_ROOT = Path(r"D:\AstrBotLauncher-0.1.5.5\AstrBot")
DEPLOYED = ASTRBOT_ROOT / "data" / "plugins" / "astrbot_plugin_sts2_player" / "main.py"
CONFIG = (
    ASTRBOT_ROOT
    / "data"
    / "config"
    / "astrbot_plugin_sts2_player_config.json"
)


def load_real_cfg() -> dict:
    if not CONFIG.exists():
        raise SystemExit(f"找不到配置文件：{CONFIG}")
    # AstrBot 写的配置带 UTF-8 BOM，必须用 utf-8-sig
    return json.loads(CONFIG.read_text(encoding="utf-8-sig"))


def build(overrides: dict | None = None):
    if not DEPLOYED.exists():
        raise SystemExit(f"找不到部署的插件：{DEPLOYED}")
    cfg = load_real_cfg()
    if overrides:
        cfg.update(overrides)
    mod = sts2stub.load_plugin(DEPLOYED)
    provider = sts2stub.ScriptedProvider()
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(provider), cfg)
    event = sts2stub.AstrMessageEvent()
    return mod, plugin, provider, event, cfg


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--autopilot", type=float, default=0.0, help="托管跑多少秒")
    ap.add_argument("--no-llm", action="store_true", help="强制关掉 use_llm（省 token）")
    args = ap.parse_args()

    overrides = {}
    if args.no_llm:
        overrides = {"use_llm": False, "llm_combat": False, "llm_combat_plan": False}

    mod, plugin, provider, event, cfg = build(overrides)

    print("=" * 68)
    print(f"插件文件 : {DEPLOYED}")
    print(f"配置文件 : {CONFIG}")
    print(f"sts2_url : {cfg.get('sts2_url')}")
    print(f"use_llm  : {cfg.get('use_llm')}  llm_combat_plan: {cfg.get('llm_combat_plan')}")
    print("=" * 68, flush=True)

    mode = await plugin.client.detect()
    ok = await plugin.client.health()
    print(f"后端识别 : {mode}   健康: {ok}", flush=True)
    if not ok:
        print("连不上游戏，先按文档 §3 起两个实例")
        return 2

    st = await plugin.client.state()
    print(f"当前局面 : {mod.render_state(st).splitlines()[0] if mod.render_state(st) else '(空)'}", flush=True)

    if args.state:
        print()
        print(mod.render_state(st))
        return 0

    if args.once:
        act = plugin.bot.next_action(st)
        print(f"决策     : {act}", flush=True)
        if act and act.get("action") not in ("wait", "sleep", ""):
            name = act["action"]
            params = {
                k: v
                for k, v in act.items()
                if k not in ("action", "tool", "think", "reason")
            }
            res = await plugin.client.act(name, **params)
            print(f"执行结果 : {res.get('status') or res.get('message') or res}", flush=True)
        await plugin.client.close()
        return 0

    if args.autopilot > 0:
        umo = "webchat:FriendMessage:test"
        print(f"\n启动托管循环，跑 {args.autopilot} 秒…\n", flush=True)
        plugin._autopilot = True
        task = asyncio.create_task(plugin._autopilot_loop(umo))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=args.autopilot)
        except asyncio.TimeoutError:
            print(f"\n[到 {args.autopilot} 秒，停止托管]", flush=True)
        finally:
            await plugin._stop_autopilot(quiet=True)
            if not task.done():
                task.cancel()
            await asyncio.sleep(0.5)

        st2 = await plugin.client.state()
        print(f"\n结束局面 : {mod.render_state(st2).splitlines()[0] if mod.render_state(st2) else '(空)'}")
        print(f"LLM 调用 : {provider.calls}")
        print(f"通知条数 : {len(getattr(plugin, '_notify_log', []) or [])}")
        await plugin.client.close()
        return 0

    await plugin.client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
