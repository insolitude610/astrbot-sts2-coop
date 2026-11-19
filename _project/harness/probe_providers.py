# -*- coding: utf-8 -*-
"""探测 AstrBot 各 provider 通道是否还能用（直接打上游，不经过 AstrBot）。

    python probe_providers.py
    python probe_providers.py --only 霓窝 aihubmix
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CMD_CONFIG = Path(
    r"D:\AstrBotLauncher-0.1.5.5\AstrBot\data\cmd_config.json"
)


def load() -> dict:
    return json.loads(CMD_CONFIG.read_text(encoding="utf-8-sig"))


def probe(base: str, key: str, model: str, timeout: float = 30.0) -> tuple[bool, str]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "reply with: ok"}],
        "max_tokens": 16,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "no op",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ],
        "tool_choice": "auto",
    }
    base = base.rstrip("/")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        txt = (msg.get("content") or "").strip()[:40]
        return True, f"HTTP {r.status}  content={txt!r}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:160]
        return False, f"HTTP {e.code}  {detail}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:140]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    cfg = load()
    sources = {s.get("id"): s for s in cfg.get("provider_sources", [])}
    providers = [p for p in cfg.get("provider", []) if p.get("enable")]

    chat_models = []
    for p in providers:
        pid = str(p.get("id") or "")
        src_id = p.get("provider_source_id")
        if not src_id or "modalities" not in p:
            continue
        src = sources.get(src_id)
        if not src:
            continue
        if "tool_use" not in (p.get("modalities") or []):
            continue
        chat_models.append((pid, str(p.get("model") or ""), src))

    if args.only:
        wanted = set(args.only)
        chat_models = [x for x in chat_models if any(w in x[0] for w in wanted)]

    print(f"探测 {len(chat_models)} 个支持 tool_use 的通道\n")
    ok_list = []
    for pid, model, src in chat_models:
        keys = src.get("key") or []
        if isinstance(keys, str):
            keys = [keys]
        base = str(src.get("api_base") or "")
        if not keys or not base:
            print(f"✗ {pid:38} 缺 key 或 base")
            continue
        ok, msg = probe(base, keys[0], model)
        mark = "✓" if ok else "✗"
        print(f"{mark} {pid:38} {msg}")
        if ok:
            ok_list.append(pid)

    print(f"\n可用通道（{len(ok_list)}）:")
    for x in ok_list:
        print(f"  · {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
