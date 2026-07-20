from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from crypto_alert_v2.graph.runtime import AnalysisRuntime
from crypto_alert_v2.graph.state import AnalysisState
from crypto_alert_v2.monitors.models import MonitorIngressRequest
from crypto_alert_v2.monitors.runtime import admit_monitor_ingress


async def run_monitor_ingress(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> dict[str, Any]:
    request = MonitorIngressRequest.model_validate(state["request"])
    execution_info = runtime.execution_info
    if execution_info is None or not execution_info.run_id:
        raise RuntimeError(
            "monitor ingress requires LangGraph Runtime.execution_info.run_id"
        )
    receipt = await admit_monitor_ingress(
        request,
        official_run_id=execution_info.run_id,
        official_thread_id=execution_info.thread_id,
    )
    return {
        "monitor_trigger": receipt,
        "admitted_task_id": receipt["task_id"],
        "lifecycle": f"monitor_trigger_{receipt['status']}",
        "terminal_status": "succeeded",
    }


__all__ = ["run_monitor_ingress"]
