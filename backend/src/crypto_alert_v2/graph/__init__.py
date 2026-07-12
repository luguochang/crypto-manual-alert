"""Graph 模块 - 导出编译后的 canonical graph。

langgraph.json 指向此文件的 graph 变量。
Agent Server 加载时自动注入 checkpointer 和 store，代码中不配置。
"""
from crypto_alert_v2.graph.graph import graph

__all__ = ["graph"]
