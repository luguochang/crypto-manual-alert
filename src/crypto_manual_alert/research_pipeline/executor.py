from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from crypto_manual_alert.telemetry.observability import ObservabilityRecorder, use_observability
from crypto_manual_alert.research_pipeline.models import ResearchAudit, ResearchPlan, ResearchQuery, SearchResult
from crypto_manual_alert.research_pipeline.protocols import SearchAdapter


def execute_research(
    plan: ResearchPlan,
    adapter: SearchAdapter,
    max_workers: int = 4,
    recorder: ObservabilityRecorder | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
) -> ResearchAudit:
    results: dict[str, list[SearchResult]] = {}
    unavailable: list[str] = []
    if not plan.queries:
        return ResearchAudit(plan=plan)
    worker_count = max(1, min(max_workers, len(plan.queries)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_query = {
            executor.submit(
                _run_research_query,
                query,
                adapter,
                recorder,
                trace_id,
                parent_span_id,
            ): query
            for query in plan.queries
        }
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                query_results = future.result()
            except Exception as exc:  # noqa: BLE001 - search degradation enters audit, not main-flow failure.
                unavailable.append(f"{query.name}: {type(exc).__name__}: {exc}")
                continue
            if query_results:
                results[query.name] = query_results
            elif query.required:
                unavailable.append(f"{query.name}: no search results")
    return ResearchAudit(plan=plan, results=dict(sorted(results.items())), unavailable=sorted(unavailable))


def _run_research_query(
    query: ResearchQuery,
    adapter: SearchAdapter,
    recorder: ObservabilityRecorder | None,
    trace_id: str | None,
    parent_span_id: str | None,
) -> list[SearchResult]:
    if recorder is None or trace_id is None:
        return adapter.search(query)
    with use_observability(recorder, trace_id):
        with recorder.span(
            trace_id,
            "research.search.query",
            "research.search.query",
            input_summary={"query_name": query.name, "query": query.query, "purpose": query.purpose},
            parent_span_id=parent_span_id,
            metadata={"query_name": query.name, "required": query.required},
        ) as span:
            try:
                results = adapter.search(query)
            except Exception:
                span.set_output({"query_name": query.name, "result_count": 0, "required": query.required})
                raise
            span.set_output({"query_name": query.name, "result_count": len(results), "required": query.required})
            return results
