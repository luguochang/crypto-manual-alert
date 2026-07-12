"""agent_node - Phase 0 兼容模块（已废弃）。

Phase 1 已将此节点拆分为多个节点：
- analyze_market：LLM 市场分析
- confirm_analysis：HITL 人工确认

此文件保留向后兼容，新代码请使用 analyze_market 和 confirm_analysis。
"""

# Phase 1：agent_node 不再直接使用，Graph 使用 analyze_market + confirm_analysis
# 此文件保留避免旧导入报错
