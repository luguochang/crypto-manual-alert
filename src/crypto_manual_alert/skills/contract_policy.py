from __future__ import annotations


ALLOWED_FACTOR_TYPES = ("macro_event", "derivatives", "liquidity", "sentiment", "policy", "flow")
ALLOWED_MACRO_FIELDS = (
    "event_status",
    "actual",
    "consensus",
    "surprise",
    "market_reaction",
    "lagged_confirmation",
    "released_at",
)
ALLOWED_RESULT_TYPES = {
    "evidence_candidates",
    "exchange_execution_fact_candidates",
    "macro_event_candidates",
    "root_cause_factor_candidates",
    "sentiment_crowding_candidates",
}
ALLOWED_SENTIMENT_OUTPUTS = ("crowding", "priced_in", "reflexivity")
ALLOWED_SKILL_NAMES = {
    "liquidity_order_book",
    "macro_event",
    "market_sentiment",
    "realtime_search",
    "root_cause_search",
}
ALLOWED_SOURCE_TYPES = {
    "exchange_native",
    "official_or_event_pool",
    "search_derived",
}
ALLOWED_STATUSES = {"error", "ok", "partial"}
ALLOWED_TASK_IDS = {
    "skill:liquidity_order_book",
    "skill:macro_event",
    "skill:market_sentiment",
    "skill:realtime_search",
    "skill:root_cause",
    "skill:root_cause_search",
}
EXECUTION_FACTS = ("mark", "index", "order_book")
ALLOWED_MISSING_INPUTS = {"query", "symbol"}
_FORBIDDEN_PUBLIC_VALUE_TOKENS = (
    "allow_notification",
    "allow_production_journal_write",
    "entry_trigger",
    "final_decision",
    "journal",
    "live_order",
    "main_action",
    "max_leverage",
    "notification",
    "order_payload",
    "position_size",
    "production_final_input",
    "risk_pct",
    "risk_verdict",
    "side_effect",
    "stop_price",
    "target_1",
    "target_2",
)
_SKILL_CONTRACTS = {
    "liquidity_order_book": {
        "task_ids": {"skill:liquidity_order_book"},
        "result_type": "exchange_execution_fact_candidates",
        "source_type": "exchange_native",
        "can_satisfy_execution_fact": True,
    },
    "macro_event": {
        "task_ids": {"skill:macro_event"},
        "result_type": "macro_event_candidates",
        "source_type": "official_or_event_pool",
        "can_satisfy_execution_fact": False,
    },
    "market_sentiment": {
        "task_ids": {"skill:market_sentiment"},
        "result_type": "sentiment_crowding_candidates",
        "source_type": "search_derived",
        "can_satisfy_execution_fact": False,
    },
    "realtime_search": {
        "task_ids": {"skill:realtime_search"},
        "result_type": "evidence_candidates",
        "source_type": "search_derived",
        "can_satisfy_execution_fact": False,
    },
    "root_cause_search": {
        "task_ids": {"skill:root_cause", "skill:root_cause_search"},
        "result_type": "root_cause_factor_candidates",
        "source_type": "search_derived",
        "can_satisfy_execution_fact": False,
    },
}
