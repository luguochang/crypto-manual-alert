from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.store_namespace import rewrite_namespace


def test_namespace_is_always_prefixed_with_actor_boundary() -> None:
    actor = ActorContext(
        tenant_id="t1",
        workspace_id="w1",
        user_id="u1",
        roles=("member",),
        permissions=("memory:read", "memory:write"),
    )

    assert rewrite_namespace(
        actor,
        scope="private",
        principal_id="u1",
        namespace=("preferences",),
    ) == (
        "tenant",
        "t1",
        "workspace",
        "w1",
        "scope",
        "private",
        "principal",
        "u1",
        "preferences",
    )


def test_private_namespace_cannot_target_another_user() -> None:
    actor = ActorContext(
        tenant_id="t1",
        workspace_id="w1",
        user_id="u1",
        roles=("member",),
        permissions=("memory:read",),
    )

    try:
        rewrite_namespace(
            actor,
            scope="private",
            principal_id="u2",
            namespace=("preferences",),
        )
    except PermissionError as exc:
        assert "private" in str(exc)
    else:
        raise AssertionError("private namespace accepted another principal")
