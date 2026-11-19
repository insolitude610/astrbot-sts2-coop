# -*- coding: utf-8 -*-
"""对比 codex-for / commandcode 两条通道在真机场景下的表现。

复现 AstrBot 日志里的异常：
    OpenAI completion has no usable output: finish_reason='stop' 但 content 为空

用法：
    python compare_providers.py                 # 跑全部用例
    python compare_providers.py --rounds 5      # 每用例重复 5 次（看稳定性）
    python compare_providers.py --only codex    # 只测一条通道
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

CMD_CONFIG = Path(r"D:\AstrBotLauncher-0.1.5.5\AstrBot\data\cmd_config.json")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class Target:
    name: str
    base: str
    key: str
    model: str


@dataclass
class Result:
    target: str
    case: str
    ok_http: bool = False
    content_len: int = 0
    has_tool: bool = False
    finish: str = ""
    reasoning_len: int = 0
    elapsed: float = 0.0
    error: str = ""
    empty_anomaly: bool = False   # finish=stop 且 content 空 → 就是日志里那种


CASES = [
    {
        "name": "闲聊（短）",
        "messages": [{"role": "user", "content": "在吗"}],
        "max_tokens": 128,
        "tools": False,
    },
    {
        "name": "闲聊（长）",
        "messages": [
            {"role": "system", "content": "你是陪玩伙伴，说话自然口语化。"},
            {"role": "user", "content": "今天打得有点累，你觉得我这局怎么样？"},
        ],
        "max_tokens": 256,
        "tools": False,
    },
    {
        "name": "工具调用",
        "messages": [
            {"role": "system", "content": "你是陪玩伙伴。"},
            {"role": "user", "content": "帮我打牌吧"},
        ],
        "max_tokens": 256,
        "tools": True,
    },
    {
        "name": "带 tool 定义的闲聊",
        "messages": [
            {"role": "system", "content": "你是陪玩伙伴，说话自然。"},
            {"role": "user", "content": "这局有什么建议吗"},
        ],
        "max_tokens": 256,
        "tools": True,
    },
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sts2_autopilot",
            "description": "接手后台托管，替玩家一直打下去",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "为什么认为玩家想让你接手"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sts2_state",
            "description": "查看当前对局状态",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def load_targets(only: str | None) -> list[Target]:
    cfg = json.loads(CMD_CONFIG.read_text(encoding="utf-8-sig"))
    srcs = {s.get("id"): s for s in cfg.get("provider_sources", [])}
    provs = [p for p in cfg.get("provider", []) if p.get("enable")]

    wanted = {
        "codex": "codex-for/gemini-3.8-flash",
        "cmd": "commandcode/deepseek/deepseek-v4.1-flash",
        "deesc": "deepseek_default_source/deepseek-v4-flash",
        "wo": "霓窝/gemini-3.8-flash",
        "hub": "aihubmix/gemini-3.8-flash",
    }
    if only:
        keep = wanted.get(only)
        targets = []
        for p in provs:
            if keep and p.get("id") == keep:
                s = srcs.get(p.get("provider_source_id"))
                if s and s.get("key"):
                    targets.append(
                        Target(str(p["id"]), str(s["api_base"]), s["key"][0], str(p["model"]))
                    )
        if targets:
            return targets

    out = []
    for pid in (
        "codex-for/gemini-3.8-flash",
        "commandcode/deepseek/deepseek-v4.1-flash",
    ):
        for p in provs:
            if p.get("id") != pid:
                continue
            s = srcs.get(p.get("provider_source_id"))
            if not s:
                continue
            keys = s.get("key") or []
            if not keys:
                continue
            out.append(Target(pid, str(s["api_base"]), keys[0], str(p["model"])))
    return out


def call(t: Target, case: dict) -> Result:
    r = Result(target=t.name, case=case["name"])
    body = {
        "model": t.model,
        "messages": case["messages"],
        "max_tokens": case["max_tokens"],
    }
    if case["tools"]:
        body["tools"] = TOOLS
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        t.base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {t.key}",
            "User-Agent": UA,
            "Accept": "application/json",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            d = json.load(resp)
        r.elapsed = time.time() - t0
        r.ok_http = True
        ch = (d.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        r.content_len = len((msg.get("content") or "").strip())
        r.finish = str(ch.get("finish_reason") or "")
        r.has_tool = bool(msg.get("tool_calls"))
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        r.reasoning_len = len(str(reasoning))
        # 日志里那种异常：finish=stop 但既没 content 也没 tool_calls
        if r.finish == "stop" and r.content_len == 0 and not r.has_tool:
            r.empty_anomaly = True
    except urllib.error.HTTPError as e:
        r.elapsed = time.time() - t0
        r.error = f"HTTP {e.code} {e.read().decode('utf-8', 'replace')[:120]}"
    except Exception as e:  # noqa: BLE001
        r.elapsed = time.time() - t0
        r.error = f"{type(e).__name__}: {str(e)[:110]}"
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    targets = load_targets(args.only)
    if not targets:
        print("没有可用通道")
        return 2

    print(f"{'='*78}")
    print(f"对比 {len(targets)} 条通道 × {len(CASES)} 个用例 × {args.rounds} 轮")
    print(f"{'='*78}\n")

    all_results: dict[str, list[Result]] = {t.name: [] for t in targets}
    for t in targets:
        print(f"--- {t.name}  (model={t.model}) ---")
        for case in CASES:
            for i in range(args.rounds):
                r = call(t, case)
                all_results[t.name].append(r)
                flag = "⚠空" if r.empty_anomaly else ("✓" if r.ok_http else "✗")
                detail = (
                    f"content={r.content_len}字 tool={'Y' if r.has_tool else 'N'} "
                    f"reasoning={r.reasoning_len} finish={r.finish} {r.elapsed:.1f}s"
                )
                if r.error:
                    detail = r.error
                suffix = f" [{i+1}]" if args.rounds > 1 else ""
                print(f"  {flag} {case['name']:16}{suffix:5} {detail}")
        print()

    print(f"{'='*78}")
    print("汇总")
    print(f"{'='*78}")
    for name, rs in all_results.items():
        total = len(rs)
        errs = sum(1 for r in rs if not r.ok_http)
        empties = sum(1 for r in rs if r.empty_anomaly)
        tools = sum(1 for r in rs if r.has_tool)
        avg = sum(r.elapsed for r in rs) / total if total else 0
        print(
            f"{name:42} 成功 {total-errs}/{total}  空异常 {empties}  "
            f"调工具 {tools}  平均 {avg:.1f}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
