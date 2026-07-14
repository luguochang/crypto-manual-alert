def test_graph_is_compiled() -> None:
    from crypto_alert_v2.graph import graph

    assert type(graph).__name__ == "CompiledStateGraph"
