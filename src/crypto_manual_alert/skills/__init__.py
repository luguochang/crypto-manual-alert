__all__ = [
    "CommandDecisionEngine",
    "DecisionEngine",
    "EvidenceCandidate",
    "FixtureDecisionEngine",
    "OpenAICompatibleDecisionEngine",
    "LiquidityOrderBookSkill",
    "MacroEventSkill",
    "MarketSentimentSkill",
    "RealtimeSearchSkill",
    "RootCauseSearchSkill",
    "SkillConstraints",
    "SkillContext",
    "SkillExecutor",
    "SkillTaskContext",
    "SkillInfo",
    "SkillRuntime",
    "SkillToolResult",
    "SourceFreshness",
    "ToolBudget",
    "ToolCallArtifact",
    "DEFAULT_SKILL_NAMES",
    "build_default_skill_registry",
]

_EXPORT_MODULES = {
    "CommandDecisionEngine": "crypto_manual_alert.decision.final_engine",
    "DecisionEngine": "crypto_manual_alert.decision.final_engine",
    "EvidenceCandidate": "crypto_manual_alert.skills.facade",
    "FixtureDecisionEngine": "crypto_manual_alert.decision.final_engine",
    "LiquidityOrderBookSkill": "crypto_manual_alert.skills.facade",
    "MacroEventSkill": "crypto_manual_alert.skills.facade",
    "MarketSentimentSkill": "crypto_manual_alert.skills.facade",
    "OpenAICompatibleDecisionEngine": "crypto_manual_alert.decision.final_engine",
    "RealtimeSearchSkill": "crypto_manual_alert.skills.facade",
    "RootCauseSearchSkill": "crypto_manual_alert.skills.facade",
    "SkillConstraints": "crypto_manual_alert.skills.facade",
    "SkillContext": "crypto_manual_alert.skills.context_loader",
    "SkillExecutor": "crypto_manual_alert.skills.executor",
    "SkillTaskContext": "crypto_manual_alert.skills.facade",
    "SkillInfo": "crypto_manual_alert.skills.context_loader",
    "SkillRuntime": "crypto_manual_alert.skills.context_loader",
    "SkillToolResult": "crypto_manual_alert.skills.facade",
    "SourceFreshness": "crypto_manual_alert.skills.source_freshness",
    "ToolBudget": "crypto_manual_alert.skills.tool_budget",
    "ToolCallArtifact": "crypto_manual_alert.skills.tool_call_artifact",
    "DEFAULT_SKILL_NAMES": "crypto_manual_alert.skills.registry",
    "build_default_skill_registry": "crypto_manual_alert.skills.registry",
}


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
