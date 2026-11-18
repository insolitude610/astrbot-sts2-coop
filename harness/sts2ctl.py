# -*- coding: utf-8 -*-
"""直连游戏 mod HTTP 接口的探针 / 驱动脚本（不经过 AstrBot、不需要 QQ）。

子命令：

    probe                    打印 /health + /state 摘要 + available_actions
    raw-state [--out FILE]   把 /state 原始 JSON 落盘（适配多人字段时用）
    actions                  打印 /actions/available 原始 JSON
    act <action> [k=v ...]   POST /action（例：act choose_map_node option_index=0）
    play [--steps N]         用插件真实代码路径跑 _auto 自动推进
    lobby                    自动推进到「大厅 / 角色选择」并打印两边能做什么

一切只打 127.0.0.1 上的端口，默认 8082（队友实例）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402  必须先装 AstrBot 桩

import aiohttp  # noqa: E402

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"


async def http(method: str, url: str, payload: dict | None = None, timeout: float = 20.0):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.request(method, url, json=payload) as r:
                text = await r.text()
                try:
                    return r.status, json.loads(text)
                except json.JSONDecodeError:
                    return r.status, {"raw": text[:800]}
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


async def cmd_probe(base: str) -> int:
    st, health = await http("GET", f"{base}/health")
    if not st:
        print(f"GET {base}/health 连不上：{health.get('error')}")
        return 2
    print(f"GET /health -> {st}")
    inner = (health or {}).get("data") or {}
    for k in (
        "service",
        "mod_version",
        "game_version",
        "status",
        "api_port",
        "instance_role",
        "play_running",
        "play_phase",
        "mcp_enabled",
    ):
        if k in inner:
            print(f"  {k}: {inner[k]}")

    st, state = await http("GET", f"{base}/state")
    data = (state or {}).get("data") or {}
    print(f"\nGET /state -> {st}")
    if not data:
        print("  原始：", json.dumps(state, ensure_ascii=False)[:800])
        return 1
    for k in ("screen", "run_id", "available_actions", "session", "multiplayer", "turn", "modal"):
        if k in data:
            v = data[k]
            if isinstance(v, (dict, list)):
                print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:500]}")
            else:
                print(f"  {k}: {v}")
    print("  顶层键：", ", ".join(sorted(data.keys())))
    return 0


async def cmd_raw(base: str, out: str) -> int:
    st, state = await http("GET", f"{base}/state")
    data = (state or {}).get("data") or {}
    path = Path(out)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {path}（{len(json.dumps(data, ensure_ascii=False))} 字符，HTTP {st}）")
    return 0


async def cmd_actions(base: str) -> int:
    st, payload = await http("GET", f"{base}/actions/available")
    print(f"GET /actions/available -> {st}")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:6000])
    return 0


def parse_kv(parts: list[str]) -> dict:
    body: dict = {}
    for part in parts:
        if not part:
            continue
        if part.startswith("{"):
            body.update(json.loads(part))
            continue
        if "=" not in part:
            raise SystemExit(f"看不懂的参数：{part}")
        k, v = part.split("=", 1)
        if re.fullmatch(r"-?\d+", v):
            body[k] = int(v)
        elif v.lower() in ("true", "false"):
            body[k] = v.lower() == "true"
        else:
            body[k] = v
    return body


async def cmd_act(base: str, action: str, params: list[str]) -> int:
    body = parse_kv(params)
    st, res = await http("POST", f"{base}/action", {"action": action, **body})
    print(f"POST /action {action} {body} -> {st}")
    print(json.dumps(res, ensure_ascii=False, indent=2)[:2500])
    return 0


def build_plugin(base: str, *, use_llm: bool = False, plan: bool = False, cfg_extra=None):
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    provider = sts2stub.ScriptedProvider()
    cfg = {
        "sts2_url": base,
        "sts2_timeout_sec": 25,
        "operator_ids": [],
        "max_steps": 60,
        "step_interval_sec": 0.5,
        "report_every": 1,
        "use_llm": use_llm,
        "llm_combat": False,
        "llm_combat_plan": plan,
        "potion_hp_ratio": 0.32,
        "block_priority": 0.6,
        "card_min": 18,
        "auto_restart": False,
    }
    if cfg_extra:
        cfg.update(cfg_extra)
    plugin = mod.Sts2PlayerPlugin(sts2stub.StubContext(provider), cfg)
    event = sts2stub.AstrMessageEvent()
    return mod, plugin, provider, event


async def cmd_play(base: str, steps: int, use_llm: bool, plan: bool) -> int:
    mod, plugin, provider, event = build_plugin(base, use_llm=use_llm, plan=plan)
    mode = await plugin.client.detect()
    ok = await plugin.client.health()
    print(f"后端：{mode}　健康：{ok}　LLM 调用：{provider.calls}", flush=True)
    if not ok:
        print("游戏 mod 接口没起来：先启动游戏并确认 STS2AIAgent 已加载。")
        await plugin.client.close()
        return 2
    st = await plugin.client.state()
    print(f"起始界面：{st.get('state_type')} / screen={st.get('screen')}", flush=True)
    n = 0
    async for msg in plugin._auto(event, steps):
        n += 1
        print(f"\n[{n}] {msg}", flush=True)
    print(f"\n共 {n} 步，LLM 调用 {provider.calls} 次")
    await plugin.client.close()
    return 0


async def cmd_lobby(base: str) -> int:
    mod, plugin, provider, event = build_plugin(base)
    if not await plugin.client.health():
        print("接口没起来")
        await plugin.client.close()
        return 2
    for i in range(40):
        st = await plugin.client.state()
        scr = st.get("screen")
        avail = st.get("available_actions") or []
        print(f"[{i}] screen={scr} avail={avail}")
        if scr == "CHARACTER_SELECT" and "embark" in avail:
            print("-> 已在角色选择且可出发")
            break
        if scr == "CHARACTER_SELECT" and "select_character" in avail:
            step = ("select_character", {"option_index": 0})
        elif scr == "MAIN_MENU" and "continue_run" in avail:
            step = ("continue_run", {})
        elif scr == "MAIN_MENU" and "open_character_select" in avail:
            step = ("open_character_select", {})
        elif scr == "MODAL" and "dismiss_modal" in avail:
            step = ("dismiss_modal", {})
        elif "close_main_menu_submenu" in avail:
            step = ("close_main_menu_submenu", {})
        else:
            print("-> 没有可推进的动作，停下")
            break
        res = await plugin.client.act(step[0], **step[1])
        print(f"    {step[0]} -> {res}")
        await asyncio.sleep(1.5)
    await plugin.client.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["probe", "raw-state", "actions", "act", "play", "lobby"])
    p.add_argument("arg", nargs="?", default="")
    p.add_argument("params", nargs="*", default=[])
    p.add_argument("--base", default="http://127.0.0.1:8082")
    p.add_argument("--out", default=str(HERE / "state_raw.json"))
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--use-llm", action="store_true")
    p.add_argument("--plan", action="store_true")
    a = p.parse_args()
    base = a.base.rstrip("/")

    if a.cmd == "probe":
        return asyncio.run(cmd_probe(base))
    if a.cmd == "raw-state":
        return asyncio.run(cmd_raw(base, a.out))
    if a.cmd == "actions":
        return asyncio.run(cmd_actions(base))
    if a.cmd == "act":
        return asyncio.run(cmd_act(base, a.arg, a.params))
    if a.cmd == "play":
        return asyncio.run(cmd_play(base, a.steps, a.use_llm, a.plan))
    if a.cmd == "lobby":
        return asyncio.run(cmd_lobby(base))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
