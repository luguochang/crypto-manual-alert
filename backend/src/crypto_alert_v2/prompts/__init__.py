"""Prompts 模块 - System Prompt 版本管理。

设计文档 14 第三节：
- 当前生产版本在 system_prompt.py
- 历史版本在 system_prompt_v{N}.py
- get_system_prompt(version) 获取指定版本
"""
from crypto_alert_v2.prompts.system_prompt import SYSTEM_PROMPT, VERSION, get_system_prompt

__all__ = ["SYSTEM_PROMPT", "VERSION", "get_system_prompt"]
