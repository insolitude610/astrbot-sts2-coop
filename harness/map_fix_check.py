# -*- coding: utf-8 -*-
"""验证地图多人修复：构造「投完票、available_actions 里没有 choose_map_node」
的两种真实快照，对比修复前 / 修复后规则层的返回。

不连游戏，纯离线验证规则层语义，跑得稳。

    python map_fix_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"


def base_state(**over):
    st = {
        "state_type": "map",
        "screen": "MAP",
        "available_actions": ["choose_map_node"],
        "player": {"hp": 70, "max_hp": 80, "gold": 120},
        "map": {
            "current_position": {"row": 1, "col": 1},
            "next_options": [
                {"index": 0, "row": 2, "col": 0, "type": "Monster"},
                {"index": 1, "row": 2, "col": 2, "type": "RestSite"},
            ],
            "boss": {"row": 15, "col": 3},
            "can_vote": True,
            "local_vote": None,
            "voted_player_ids": [],
        },
    }
    st.update(over)
    return st


def main() -> int:
    mod = sts2stub.load_plugin(PLUGIN_MAIN)
    bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6, card_min=18.0)

    cases = []

    # 场景 A：还没投票 —— 应该投一票（修复前后都应如此）
    a = base_state()
    cases.append(("A 未投票（可投）", a))

    # 场景 B：已经投过票、等别人 —— 修复前返回 None（整局停下），修复后返回 wait
    b = base_state(
        available_actions=[],
        map={
            "current_position": {"row": 1, "col": 1},
            "next_options": [],
            "boss": {"row": 15, "col": 3},
            "can_vote": False,
            "local_vote": {"row": 2, "col": 2},
            "voted_player_ids": ["3"],
        },
    )
    cases.append(("B 已投票等别人", b))

    # 场景 C：投了票但字段缺失（老/异常 payload），靠 available_actions 判断
    c = base_state(
        available_actions=[],
        map={
            "current_position": {"row": 1, "col": 1},
            "next_options": [],
            "boss": {"row": 15, "col": 3},
            "voted_player_ids": ["1", "3"],
        },
    )
    cases.append(("C 已投票（local_vote 缺）", c))

    # 场景 D：投票窗口开着但节点为空 —— 应 wait，不能停下
    d = base_state(available_actions=["choose_map_node"], map={
        "current_position": {"row": 1, "col": 1},
        "next_options": [],
        "boss": {"row": 15, "col": 3},
        "can_vote": True,
        "voted_player_ids": [],
    })
    cases.append(("D 可投但节点空", d))

    # 场景 E：**已投过票、但 choose_map_node 仍在 available_actions 里**。
    # 真机踩到（2026-11-18 11:21）：游戏允许改票，动作不会消失，
    # 旧补丁只看动作在不在，结果 3.2 秒内重复投了 9 次同一票。
    e = base_state(
        available_actions=["choose_map_node"],
        map={
            "current_position": {"row": 1, "col": 1},
            "next_options": [{"index": 0, "row": 2, "col": 2, "type": "Monster"}],
            "boss": {"row": 15, "col": 3},
            "can_vote": True,
            "local_vote": {"row": 2, "col": 2},
            "voted_player_ids": ["8"],
        },
    )
    cases.append(("E 已投票但动作仍在", e))

    # 场景 F：别人投了、本方没投 —— 应该照常投票（别误判成自己投过）
    f = base_state(
        available_actions=["choose_map_node"],
        map={
            "current_position": {"row": 1, "col": 1},
            "next_options": [{"index": 0, "row": 2, "col": 2, "type": "Monster"}],
            "boss": {"row": 15, "col": 3},
            "can_vote": True,
            "local_vote": None,
            "voted_player_ids": ["1"],   # 别人投过
        },
    )
    cases.append(("F 别人投了我没投", f))

    print(f"{'场景':<24} {'规则层返回'}")
    print("-" * 70)
    bad = 0
    for name, st in cases:
        act = bot.next_action(st)
        print(f"{name:<24} {act}")
        if name.startswith(("B", "C", "D", "E")) and act is None:
            bad += 1
        if name.startswith("E") and act is not None and act.get("action") != "wait":
            print(f"    ↳ ✗ 场景 E 应返回 wait，实际 {act}")
            bad += 1
        if name.startswith("F") and (act is None or act.get("action") != "choose_map_node"):
            print(f"    ↳ ✗ 场景 F 应投票，实际 {act}")
            bad += 1

    print()
    if bad:
        print(f"✗ 有 {bad} 个多人场景不符合预期")
        return 1
    print("✓ 全部多人场景通过（含已投票不重投、别人投票不误判）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
