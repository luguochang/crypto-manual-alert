# 2026-07-18 Deep Agents Fallback Checklist Alignment

ADR 0009 is the approved Research architecture decision: the current release
uses the official LangChain `create_agent` Research Harness and does not
activate `create_deep_agent`. The reason is bounded citation extraction does
not require filesystem, execute, task delegation, long-term memory or planning;
activating the pre-1.0 Deep Agents defaults would add permission and upgrade
surface without product value.

The delivery checklist previously left “lock Deep Agents 0.x” unchecked even
though the accepted fallback decision explicitly says the package is not part
of the current release. It now records the fallback as complete and points to
ADR 0009. This does not mark the broader Task 13 lifecycle work complete:
background Deep Research, scheduled monitoring, retention, outcome, memory and
usage remain open.

The canonical framework boundary remains unchanged: one production Graph,
official LangChain `create_agent` factories, official LangGraph Runtime/HITL
and `@langchain/react` streaming. V2 remains `PARTIAL`; `Production Ready: NO`.

