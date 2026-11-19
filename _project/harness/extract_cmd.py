# -*- coding: utf-8 -*-
"""从历史会话里抽出 STS2 双开的真实启动命令。"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import zstandard

ROOT = Path(r"C:\Users\solitude\.dsh\sessions\--D-Code--")

SESSIONS = [
    "session-a6d92132-628f-4b5c-85ea-59bc68dd15c5",  # 11-18 08:57，双开 67 次
    "session-fff7c963-9d85-4929-b107-c576e5d63b96",  # 11-19 14:59
    "session-fd378b16-774c-4e6d-a82e-b4609849fb1b",  # 11-19 22:14
    "d6018295-bdf5-4a74-8318-50993573a22a",          # 11-17 16:44，双开 136 次
]


def load(name: str) -> str:
    d = ROOT / name
    if not d.exists():
        # 模糊匹配
        cands = [x for x in ROOT.iterdir() if x.is_dir() and name.startswith(x.name[:8])]
        if not cands:
            return ""
        d = cands[0]
    fs = list(d.glob("session.v*.jsonl.zstd"))
    if not fs:
        return ""
    return zstandard.ZstdDecompressor().stream_reader(
        io.BytesIO(fs[0].read_bytes())
    ).read().decode("utf-8", "replace")


def show_chunks(txt: str, needle: str, limit: int = 3) -> None:
    pat = re.compile(re.escape(needle))
    n = 0
    for m in pat.finditer(txt):
        s = max(0, m.start() - 1400)
        e = min(len(txt), m.end() + 900)
        seg = txt[s:e]
        if "Start-Process" not in seg and "ArgumentList" not in seg:
            continue
        n += 1
        seg = seg.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        print(f"\n{'#' * 30} 命中 {n} {'#' * 30}")
        print(seg[:2400])
        if n >= limit:
            return


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else "force-steam"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    for name in SESSIONS:
        txt = load(name)
        if not txt:
            print(f"--- {name}: 读不到 ---")
            continue
        hits = len(re.findall(re.escape(needle), txt))
        print(f"\n{'=' * 70}\n会话 {name}  长度={len(txt)}  命中={hits}\n{'=' * 70}")
        if hits:
            show_chunks(txt, needle, limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
