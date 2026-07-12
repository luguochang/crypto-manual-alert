"""Graph 节点模块 - Phase 1 完整 10+ 节点。

节点清单（设计文档 7.3 节）：
1.  bootstrap_run            - 注入开发身份、生成 run_id
2.  validate_request         - 校验 symbol/horizon/query
3.  collect_market_snapshot  - OKX 行情采集（并行）
4.  research_events          - 事件研究（并行）
5.  analyze_market           - LLM 市场分析（Structured Output）
6.  validate_evidence        - 证据门禁
7.  apply_risk_policy        - 14 条风控规则
8.  build_final_result       - 合并最终结果
9.  confirm_analysis         - HITL 人工确认（interrupt）
10. commit_final_artifact    - 写入数据库 + 发送通知
11. complete_run             - 完成
"""

from crypto_alert_v2.graph.nodes.bootstrap import bootstrap_run
from crypto_alert_v2.graph.nodes.collect_market_snapshot import collect_market_snapshot
from crypto_alert_v2.graph.nodes.commit_final_artifact import commit_final_artifact
from crypto_alert_v2.graph.nodes.complete import complete_run
from crypto_alert_v2.graph.nodes.confirm_analysis import confirm_analysis
from crypto_alert_v2.graph.nodes.apply_risk_policy import apply_risk_policy
from crypto_alert_v2.graph.nodes.analyze_market import analyze_market
from crypto_alert_v2.graph.nodes.build_final_result import build_final_result
from crypto_alert_v2.graph.nodes.research_events import research_events
from crypto_alert_v2.graph.nodes.validate_evidence import validate_evidence
from crypto_alert_v2.graph.nodes.validate_request import validate_request

__all__ = [
    "bootstrap_run",
    "validate_request",
    "collect_market_snapshot",
    "research_events",
    "analyze_market",
    "validate_evidence",
    "apply_risk_policy",
    "build_final_result",
    "confirm_analysis",
    "commit_final_artifact",
    "complete_run",
]
