from __future__ import annotations

from typing import Any


def project_root_cause_graph(worker_results: Any) -> dict[str, list[dict[str, Any]]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edge_keys: set[tuple[str, str, str]] = set()
    edges: list[dict[str, Any]] = []
    dependency_map: dict[str, list[str]] = {}

    for item in _list(worker_results):
        result = _mapping(item)
        worker = str(result.get("agent_name") or "")
        contribution = _mapping(result.get("contribution"))
        constraints = _mapping(contribution.get("constraints"))
        for node in _list(constraints.get("root_cause_graph")):
            payload = _mapping(node)
            node_id = payload.get("node_id")
            if not node_id:
                continue
            node_id_text = str(node_id)
            depends_on = [str(value) for value in _list(payload.get("depends_on")) if value]
            dependency_map[node_id_text] = depends_on
            nodes_by_id.setdefault(
                node_id_text,
                _drop_none(
                    {
                        "node_id": node_id_text,
                        "worker": worker or None,
                        "layer": 0,
                        "factor_type": payload.get("factor_type"),
                        "query": payload.get("query"),
                        "evidence_refs": _evidence_refs(payload),
                        "confidence": payload.get("confidence"),
                        "fact_type": payload.get("fact_type"),
                    }
                ),
            )
            for parent in depends_on:
                edge_key = (parent, node_id_text, worker)
                if edge_key in edge_keys:
                    continue
                edge_keys.add(edge_key)
                edges.append(
                    _drop_none(
                        {
                            "from": parent,
                            "to": node_id_text,
                            "worker": worker or None,
                        }
                    )
                )

    layers = _layers(dependency_map)
    nodes = []
    for node_id in nodes_by_id:
        node = dict(nodes_by_id[node_id])
        node["layer"] = layers.get(node_id, 0)
        nodes.append(node)
    return {"nodes": nodes, "edges": edges}


def project_conflict_edges(lead_synthesis: dict[str, Any], worker_results: Any) -> list[dict[str, Any]]:
    refs = _list(lead_synthesis.get("conflict_refs"))
    if refs:
        return [_safe_conflict_ref(ref) for ref in refs if _safe_conflict_ref(ref)]

    edges: list[dict[str, Any]] = []
    for item in _list(worker_results):
        result = _mapping(item)
        worker = result.get("agent_name")
        contribution = _mapping(result.get("contribution"))
        for conflict in _list(contribution.get("conflicts")):
            edges.append(
                {
                    "worker_a": str(worker or contribution.get("agent_name") or "unknown"),
                    "worker_b": "unknown",
                    "claim_ref": str(conflict),
                    "conflict_type": "worker_conflict",
                    "severity": "unknown",
                }
            )
    return edges


def project_strongest_counter_thesis_ref(lead_synthesis: dict[str, Any]) -> str | None:
    value = lead_synthesis.get("strongest_counter_thesis_ref")
    if isinstance(value, str) and value.strip():
        return value
    counter_thesis = _list(lead_synthesis.get("counter_thesis"))
    if counter_thesis:
        return "counter_thesis[0]"
    conflicts = _list(lead_synthesis.get("conflict_refs"))
    if conflicts:
        return "conflict_refs[0]"
    return None


def _safe_conflict_ref(value: Any) -> dict[str, Any]:
    payload = _mapping(value)
    if not payload:
        return {}
    return _drop_none(
        {
            "worker_a": payload.get("worker_a") or payload.get("source_worker"),
            "worker_b": payload.get("worker_b") or payload.get("target_worker"),
            "claim_ref": payload.get("claim_ref") or payload.get("ref"),
            "conflict_type": payload.get("conflict_type") or payload.get("type"),
            "severity": payload.get("severity"),
        }
    )


def _evidence_refs(payload: dict[str, Any]) -> list[str]:
    refs = payload.get("evidence_refs")
    if refs is None:
        refs = payload.get("evidence_ids")
    return [str(value) for value in _list(refs) if value]


def _layers(dependency_map: dict[str, list[str]]) -> dict[str, int]:
    cache: dict[str, int] = {}

    def layer(node_id: str, seen: set[str]) -> int:
        if node_id in cache:
            return cache[node_id]
        if node_id in seen:
            cache[node_id] = 0
            return 0
        parents = dependency_map.get(node_id) or []
        if not parents:
            cache[node_id] = 0
            return 0
        value = 1 + max(layer(parent, {*seen, node_id}) for parent in parents)
        cache[node_id] = value
        return value

    for node_id in dependency_map:
        layer(node_id, set())
    return cache


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
