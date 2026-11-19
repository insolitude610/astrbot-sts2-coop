# -*- coding: utf-8 -*-
"""AstrBot 最小桩：只提供 sts2_player 插件 import 时用到的那几个符号。

用途：在 AstrBot 主进程之外，用「插件真实代码路径」直连游戏 mod 的 HTTP 接口做实测，
不污染正在运行的 AstrBot 实例（也不需要重启它）。

    from sts2stub import load_plugin       # 先 import 本模块（会注册 astrbot.* 桩）
    mod = load_plugin("sts2_plugin_main")  # 插件 main.py 的副本
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
import types
from pathlib import Path


# ---------------------------------------------------------------------------
# astrbot.api.logger / astrbot.api.event / astrbot.api.star
# ---------------------------------------------------------------------------
class _Logger:
    def _fmt(self, level: str, args) -> str:
        if not args:
            return ""
        head, rest = args[0], args[1:]
        try:
            text = str(head) % rest if rest else str(head)
        except Exception:  # noqa: BLE001
            text = " ".join(str(a) for a in args)
        return f"[{level}] {text}"

    def debug(self, *a, **kw):
        return None  # 静音 debug，避免模型输出刷屏

    def info(self, *a, **kw):
        print(self._fmt("INFO", a), flush=True)

    def warning(self, *a, **kw):
        print(self._fmt("WARN", a), flush=True)

    warn = warning

    def error(self, *a, **kw):
        print(self._fmt("ERROR", a), flush=True)


class _AstrMessageEvent:
    """够插件用就行：_authorized 读 sender_id，回复走 plain_result。"""

    def __init__(
        self,
        umo: str = "harness:local",
        sender_id: str = "10001",
        is_private: bool = True,
    ):
        self.unified_msg_origin = umo
        self._sender = sender_id
        self._is_private = is_private
        self.sent: list[str] = []

    def get_sender_id(self) -> str:
        return self._sender

    def is_private_chat(self) -> bool:
        """真机上由 AstrBot 提供；sts2_autopilot 用它判断私聊/群聊。"""
        return self._is_private

    def plain_result(self, text: str):
        self.sent.append(text)
        return text


class _EventMessageType:
    """占位枚举：插件里只用到 PRIVATE_MESSAGE。"""

    PRIVATE_MESSAGE = "PRIVATE_MESSAGE"
    GROUP_MESSAGE = "GROUP_MESSAGE"
    ALL = "ALL"


class _Filter:
    EventMessageType = _EventMessageType

    def command(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    def command_group(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    def event_message_type(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    def on_llm_request(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    def on_llm_response(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    def on_astrbot_loaded(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    llm_tool = command


class _Plain:
    type = "Plain"

    def __init__(self, text: str = ""):
        self.text = text

    def __str__(self):
        return self.text


class _MessageChain:
    def __init__(self, chain=None, **kw):
        self.chain = list(chain or [])

    def __str__(self):
        return "".join(str(c) for c in self.chain)


class Star:
    def __init__(self, context=None, config=None):
        self.context = context
        self.config = config or {}


def _install() -> None:
    if "astrbot" in sys.modules and getattr(sys.modules["astrbot"], "_sts2_stub", False):
        return

    astrbot = types.ModuleType("astrbot")
    astrbot._sts2_stub = True

    api = types.ModuleType("astrbot.api")
    api.logger = _Logger()

    event_mod = types.ModuleType("astrbot.api.event")
    event_mod.AstrMessageEvent = _AstrMessageEvent
    event_mod.filter = _Filter()
    event_mod.MessageChain = _MessageChain

    mc_mod = types.ModuleType("astrbot.api.message_components")
    mc_mod.Plain = _Plain

    star_mod = types.ModuleType("astrbot.api.star")
    star_mod.Context = type("Context", (), {})
    star_mod.Star = Star

    api.event = event_mod
    api.star = star_mod
    api.message_components = mc_mod
    astrbot.api = api

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event_mod
    sys.modules["astrbot.api.star"] = star_mod
    sys.modules["astrbot.api.message_components"] = mc_mod


_install()


# ---------------------------------------------------------------------------
# 假 provider：让 use_llm / llm_combat_plan 的代码路径也能跑（不需要真模型）
# ---------------------------------------------------------------------------
class ScriptedProvider:
    """按顺序返还预设文本；用完后返回空 JSON，让插件回退到规则层。"""

    def __init__(self, replies: list[str] | None = None):
        self.replies = list(replies or [])
        self.calls = 0
        self.last_prompt = ""

    async def text_chat(self, prompt: str = "", system_prompt: str = "", **kw):
        self.calls += 1
        self.last_prompt = prompt
        text = self.replies.pop(0) if self.replies else '{"think":"harness 无脚本","actions":[]}'
        return types.SimpleNamespace(completion_text=text)


class StubContext:
    def __init__(self, provider):
        self.provider = provider

    def get_using_provider(self, umo: str | None = None):
        return self.provider


def load_plugin(path: str | Path, module_name: str = "sts2_plugin_main"):
    """把插件 main.py 当模块加载（需要先 import 本文件装好桩）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec and spec.loader, f"加载失败：{path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def now() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


AstrMessageEvent = _AstrMessageEvent
