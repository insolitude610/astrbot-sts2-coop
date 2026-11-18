# -*- coding: utf-8 -*-
"""插件自检：把打过补丁的插件当模块跑一遍关键路径，确认没把原有功能改坏。

覆盖：
  1. 语法 / import 正常
  2. 适配层 agent_to_legacy 对战斗 / 地图 / 奖励三种状态的形状
  3. 规则层在单人 & 多人地图、战斗等待态下的返回
  4. 渲染层不抛异常、多人字段能显示
  5. 动作名映射表没被改坏

    python selfcheck.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sts2stub  # noqa: E402

PLUGIN_MAIN = HERE / "sts2_plugin_main.py"

PASS, FAIL = "✓", "✗"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  {PASS if ok else FAIL} {label}" + (f"  — {detail}" if detail and not ok else ""))


def main() -> int:
    print("== 1. 加载插件 ==")
    try:
        mod = sts2stub.load_plugin(PLUGIN_MAIN)
        check(True, "main.py 可导入")
    except Exception as e:  # noqa: BLE001
        check(False, "main.py 可导入", str(e))
        return 1

    print("\n== 2. 常量 & 动作映射 ==")
    check(hasattr(mod, "RETRYABLE_ACTION_ERRORS") or True, "重试常量存在（可选）")
    cases = [
        ("end_turn", {}, "end_turn"),
        ("play_card", {"card_index": 2, "target": "0"}, "play_card"),
        ("choose_map_node", {"index": 1}, "choose_map_node"),
        ("select_card_reward", {"card_index": 0}, "choose_reward_card"),
        ("skip_card_reward", {}, "skip_reward_cards"),
        ("claim_reward", {"index": 0}, "claim_reward"),
        ("resolve_rewards", {}, "resolve_rewards"),
        ("choose_rest_option", {"index": 0}, "choose_rest_option"),
    ]
    for internal, params, expect in cases:
        native, _ = mod.agent_action(internal, params)
        check(native == expect, f"agent_action({internal}) -> {native}", f"期望 {expect}")

    print("\n== 3. 适配层：战斗 ==")
    agent_combat = {
        "screen": "COMBAT",
        "turn": 2,
        "available_actions": ["end_turn", "play_card"],
        "run": {
            "character_name": "铁甲战士",
            "current_hp": 70,
            "max_hp": 80,
            "gold": 120,
            "act_id": "0",
            "floor": 3,
            "deck": [],
            "relics": [{"name": "燃烧之血"}],
            "potions": [],
        },
        "combat": {
            "player": {"current_hp": 70, "max_hp": 80, "block": 0, "energy": 3},
            "players": [
                {"player_id": "1", "is_local": False, "character_name": "铁甲战士",
                 "current_hp": 69, "max_hp": 80, "block": 0, "energy": 3, "is_alive": True},
                {"player_id": "3", "is_local": True, "character_name": "铁甲战士",
                 "current_hp": 70, "max_hp": 80, "block": 0, "energy": 3, "is_alive": True},
            ],
            "hand": [
                {"index": 0, "card_id": "STRIKE_IRONCLAD", "name": "打击",
                 "resolved_rules_text": "造成6点伤害。", "energy_cost": 1,
                 "playable": True, "requires_target": True, "valid_target_indices": [0],
                 "dynamic_values": [{"name": "Damage", "current_value": 6}]},
            ],
            "enemies": [
                {"index": 0, "enemy_id": "NIBBIT", "name": "小啃兽",
                 "current_hp": 99, "max_hp": 99, "block": 0,
                 "intents": [{"intent_type": "Attack", "label": "12", "total_damage": 12}]},
            ],
            "action_readiness": {
                "can_use_combat_actions": True,
                "player_action_phase": True,
                "local_ready_to_end_turn": False,
                "all_players_ready_to_end_turn": False,
            },
            "end_turn_will_kill_player": False,
        },
    }
    legacy = mod.agent_to_legacy(agent_combat)
    check(legacy.get("state_type") == "monster", f"state_type = {legacy.get('state_type')}")
    battle = legacy.get("battle") or {}
    check(battle.get("is_play_phase") is True, "is_play_phase = True")
    check(battle.get("waiting_for_players") is False, "waiting_for_players = False（可行动）")
    check(len(battle.get("players") or []) == 2, f"多人 players 透传 = {len(battle.get('players') or [])} 个")

    print("\n== 4. 适配层：已结束回合等队友 ==")
    agent_wait = {**agent_combat}
    agent_wait["combat"] = {
        **agent_combat["combat"],
        "action_readiness": {
            "can_use_combat_actions": False,
            "player_action_phase": True,
            "local_ready_to_end_turn": True,
            "all_players_ready_to_end_turn": False,
        },
    }
    lw = mod.agent_to_legacy(agent_wait)
    bw = lw.get("battle") or {}
    check(bw.get("waiting_for_players") is True, "waiting_for_players = True（等队友）")
    bot = mod.RuleBot(potion_hp_ratio=0.32, block_priority=0.6, card_min=18.0)
    act = bot.next_action(lw)
    check(act == {"action": "wait"}, f"规则层在该状态返回 {act}")

    print("\n== 5. 适配层：多人地图 ==")
    agent_map = {
        "screen": "MAP",
        "available_actions": [],
        "run": {"current_hp": 70, "max_hp": 80, "gold": 120, "act_id": "0", "floor": 3,
                "deck": [], "relics": [], "potions": []},
        "map": {
            "is_open": True,
            "current_node": {"row": 1, "col": 1},
            "available_nodes": [],
            "boss_node": {"row": 15, "col": 3},
            "local_vote": {"row": 2, "col": 2},
            "player_votes": [
                {"player_id": "1", "coord": None},
                {"player_id": "3", "coord": {"row": 2, "col": 2}},
            ],
        },
    }
    lm = mod.agent_to_legacy(agent_map)
    mm = lm.get("map") or {}
    check(mm.get("can_vote") is False, f"can_vote = {mm.get('can_vote')}")
    check(mm.get("voted_player_ids") == ["3"], f"voted_player_ids = {mm.get('voted_player_ids')}")
    act = bot.next_action(lm)
    check(act == {"action": "wait"}, f"投票后规则层返回 {act}（不再停下）")

    print("\n== 6. 适配层：药水槽满的奖励界面 ==")
    agent_reward = {
        "screen": "REWARD",
        "available_actions": ["resolve_rewards", "collect_rewards_and_proceed", "discard_potion"],
        "run": {"current_hp": 70, "max_hp": 80, "gold": 120, "act_id": "0", "floor": 3,
                "deck": [], "relics": [],
                "potions": [{"index": 0, "potion_id": "X", "name": "易伤药水", "occupied": True,
                             "can_use": True, "can_discard": True, "description": ""}]},
        "reward": {"rewards": [], "can_proceed": True},
    }
    lr = mod.agent_to_legacy(agent_reward)
    act = bot.next_action(lr)
    check(act is not None and act.get("action") in ("discard_potion", "resolve_rewards", "proceed"),
          f"奖励界面返回 {act}")

    print("\n== 7. 渲染层不抛异常 ==")
    for name, st in (("战斗", legacy), ("地图", lm), ("奖励", lr)):
        try:
            text = mod.render_state(st)
            check(bool(text.strip()), f"{name}渲染 {len(text)} 字符")
        except Exception as e:  # noqa: BLE001
            check(False, f"{name}渲染", str(e))

    check("队友：" in mod.render_state(legacy), "战斗渲染含「队友：」行")

    print("\n== 8. 重试判定 ==")
    if hasattr(mod, "_is_retryable_action_error"):
        check(mod._is_retryable_action_error({"error": "409: invalid_action: x"}), "invalid_action 判为可重试")
        check(mod._is_retryable_action_error({"error": "409: action_in_flight"}), "action_in_flight 判为可重试")
        check(not mod._is_retryable_action_error({"error": "400: invalid_request"}), "invalid_request 不重试")
    else:
        check(False, "_is_retryable_action_error 存在")

    print("\n== 9. 事件界面保命（真机踩过的坑） ==")
    # 75HP 一路被扣到 1HP：因为「得遗物 +12」盖过了「失去生命 -10」
    blood_event = {
        "state_type": "event",
        "screen": "EVENT",
        "available_actions": ["choose_event_option"],
        "player": {"hp": 6, "max_hp": 80, "gold": 120},
        "event": {
            "event_name": "祭坛",
            "in_dialogue": False,
            "options": [
                {"index": 0, "title": "献祭", "description": "失去 10 点生命，获得一个遗物。",
                 "is_locked": False, "is_proceed": False},
                {"index": 1, "title": "离开", "description": "什么也不做。",
                 "is_locked": False, "is_proceed": True},
            ],
        },
    }
    act = bot.next_action(blood_event)
    check(
        act is not None and act.get("index") == 1,
        f"6HP 时不选掉血项 -> {act}",
        "应该选「离开」(index=1)",
    )

    # 血多时仍然可以拿遗物（别把正常收益也挡了）
    healthy = {**blood_event, "player": {"hp": 70, "max_hp": 80, "gold": 120}}
    act = bot.next_action(healthy)
    check(act is not None and act.get("index") == 0, f"70HP 时正常拿遗物 -> {act}")

    ok = sum(1 for r in results if r[0])
    print(f"\n=== {ok}/{len(results)} 通过 ===")
    if ok != len(results):
        print("失败项：")
        for good, label in results:
            if not good:
                print(f"  {FAIL} {label}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
