# -*- coding: utf-8 -*-
"""验证 detect() 缓存缺陷的修复。

原缺陷（v0.4.8）：`_mode` 永久缓存，且**连接失败时也缓存成 "mcp"**。
后果：只要第一次请求时游戏没开，这个 Client 就永久锁在 MCP 分支，
之后游戏起来了也只会打 `/api/v1/singleplayer`（STS2-Agent 没这个路由），
永远 404，只能重启 AstrBot 才能恢复。

修复后应有行为：
  1. 连不上 → 本次按 mcp 处理，但 `_mode` 保持 None（可重探）
  2. 游戏起来后再调 → 自动识别成 agent
  3. MCP 路由拿到 404 → 自动 _reset_mode() 并重试一次
  4. 已经确认 agent 后 → 缓存照旧（不重复探测，省一次往返）

    python detect_fix_check.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE.parent.parent / "main.py"   # 仓库根的插件本体

DEAD = "http://127.0.0.1:9999"      # 保证不通
LIVE = "http://127.0.0.1:8082"      # 真队友（需要游戏开着）

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f"  — {detail}" if detail and not ok else ""))


async def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)

    # 需要真实游戏实例才能验证的项（2~4）先探一下，没开就跳过而不是报失败。
    # 队友实例经常被关掉，测试不该因此变红。
    live_ok = False
    try:
        probe = mod.Sts2Client(LIVE, timeout=3)
        live_ok = await probe.health()
        await probe.close()
    except Exception:  # noqa: BLE001
        live_ok = False
    if not live_ok:
        print(f"⚠ 没探到 {LIVE}（队友实例未运行），跳过需要真机实例的 2/3/4 项\n")

    print("== 1. 连不上时不缓存 _mode ==")
    c = mod.Sts2Client(DEAD, timeout=2)
    mode = await c.detect()
    check(mode == "mcp", f"本次返回 {mode}（按 mcp 处理）")
    check(c._mode is None, f"_mode 未被污染（当前 {c._mode!r}）")
    await c.close()

    if live_ok:
        print("\n== 2. 同一实例，游戏起来后能重新识别 ==")
        c2 = mod.Sts2Client(DEAD, timeout=2)
        first = await c2.detect()
        check(first == "mcp", f"先返回 {first}")
        # 模拟「游戏起来了、配置也指向真地址」
        c2.base_url = LIVE
        c2._configured_url = LIVE
        second = await c2.detect()
        check(second == "agent", f"重探后返回 {second}")
        check(c2._mode == "agent", f"_mode 已缓存为 {c2._mode}")
        await c2.close()

        print("\n== 3. 已识别 agent 后走缓存（不重复探测） ==")
        c3 = mod.Sts2Client(LIVE, timeout=5)
        m1 = await c3.detect()
        m2 = await c3.detect()
        check(m1 == "agent" and m2 == "agent", f"两次都是 {m1}/{m2}")
        await c3.close()

        print("\n== 4. 误判成 mcp 后，state() 能自愈 ==")
        c4 = mod.Sts2Client(LIVE, timeout=5)
        c4._mode = "mcp"          # 人为制造「11:03 那种锁死状态」
        check(c4._mode == "mcp", "已人为锁成 mcp")
        try:
            st = await c4.state()
            ok = isinstance(st, dict) and bool(st.get("state_type"))
            check(ok, f"state() 自愈成功，state_type={st.get('state_type')}")
            check(c4._mode == "agent", f"_mode 已纠正为 {c4._mode}")
        except Exception as e:  # noqa: BLE001
            check(False, "state() 自愈", str(e))
        await c4.close()
    else:
        print("\n== 2/3/4. （跳过：需要运行中的队友实例）==")

    print("\n== 5. _reset_mode 能退回配置地址 ==")
    c5 = mod.Sts2Client(LIVE, timeout=3)
    c5.base_url = "http://127.0.0.1:8080"
    c5._mode = "mcp"
    c5._reset_mode()
    check(c5.base_url == LIVE, f"base_url 退回 {c5.base_url}")
    check(c5._mode is None, "_mode 已清空")
    await c5.close()

    ok = sum(1 for r in results if r[0])
    print(f"\n=== {ok}/{len(results)} 通过 ===")
    if ok != len(results):
        for good, label in results:
            if not good:
                print(f"  ✗ {label}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
