# -*- coding: utf-8 -*-
"""扫 DSH 会话存档（zstd 压缩的 jsonl），找跟 STS2 双开相关的历史对话。

    python scan_sessions.py --grep "STS2_API_PORT"
    python scan_sessions.py --list
    python scan_sessions.py --dump <session_id>   # 打印该会话里匹配的行
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

import zstandard

ROOT = Path.home() / ".dsh" / "sessions" / "--D-Code--"


def iter_sessions():
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        f = d / "session.v3.jsonl.zstd"
        if f.exists():
            yield d.name, f


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        dctx = zstandard.ZstdDecompressor()
        with dctx.stream_reader(io.BytesIO(raw)) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        try:
            return zstandard.ZstdDecompressor().decompress(
                raw, max_output_size=256 * 1024 * 1024
            ).decode("utf-8", errors="replace")
        except Exception as e:
            return f"__ERROR__ {type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grep", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dump", default="")
    ap.add_argument("--context", type=int, default=2)
    ap.add_argument("--max-hits", type=int, default=40)
    args = ap.parse_args()

    if args.list:
        n = 0
        for name, f in iter_sessions():
            n += 1
            print(f"{name}  {f.stat().st_size:>10}  {f.stat().st_mtime:.0f}")
        print(f"\n共 {n} 个会话")
        return 0

    if not args.grep and not args.dump:
        print("需要 --grep 或 --dump 或 --list")
        return 2

    pat = re.compile(args.grep, re.I) if args.grep else None

    if args.dump:
        target = ROOT / args.dump / "session.v3.jsonl.zstd"
        if not target.exists():
            print(f"找不到 {target}")
            return 1
        text = read_text(target)
        lines = text.splitlines()
        print(f"会话 {args.dump} 共 {len(lines)} 行，{len(text)} 字符")
        if pat:
            for i, ln in enumerate(lines):
                if pat.search(ln):
                    lo = max(0, i - args.context)
                    hi = min(len(lines), i + args.context + 1)
                    print(f"\n===== 命中 @ 行 {i} =====")
                    for j in range(lo, hi):
                        print(f"[{j}] {lines[j][:2000]}")
        else:
            for ln in lines[:200]:
                print(ln[:1500])
        return 0

    hits = []
    for name, f in iter_sessions():
        text = read_text(f)
        if text.startswith("__ERROR__"):
            continue
        m = pat.findall(text) if pat else []
        if m:
            hits.append((name, f, len(m), f.stat().st_mtime))

    hits.sort(key=lambda x: x[3], reverse=True)
    print(f"匹配 {pat.pattern!r} 的会话：{len(hits)} 个\n")
    for name, f, count, mt in hits[: args.max_hits]:
        import datetime

        ts = datetime.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M")
        print(f"{name}  命中{count:>4}  {ts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
