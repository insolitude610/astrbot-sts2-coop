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

    print(f"{'场景':<24} {'规则层返回'}")
    print("-" * 70)
    bad = 0
    for name, st in cases:
        act = bot.next_action(st)
        print(f"{name:<24} {act}")
        if name.startswith(("B", "C", "D")) and act is None:
            bad += 1

    print()
    if bad:
        print(f"✗ 有 {bad} 个多人场景仍然返回 None（会整局停下）")
        return 1
    print("✓ 全部多人场景都不会返回 None（不会再卡死在地图）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
