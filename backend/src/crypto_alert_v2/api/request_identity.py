from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import Request, Response


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_MAX_LENGTH = 128
_request_id: ContextVar[str | None] = ContextVar("product_request_id", default=None)


def resolve_request_id(value: str | None) -> str:
    candidate = value.strip() if value is not None else ""
    if (
        1 <= len(candidate) <= _REQUEST_ID_MAX_LENGTH
        and candidate[0].isalnum()
        and candidate[0].isascii()
        and all(
            character.isascii() and (character.isalnum() or character in "._:-")
            for character in candidate
        )
    ):
        return candidate
    return str(uuid4())


def new_request_id() -> str:
    return str(uuid4())


def current_request_id() -> str:
    request_id = _request_id.get()
    return request_id if request_id is not None else new_request_id()


def correlation_id_for_task(task_id: str | UUID) -> str:
    stable_task_id = str(task_id).strip()
    if not stable_task_id:
        raise ValueError("task_id is required for execution correlation")
    return str(uuid5(NAMESPACE_URL, f"urn:crypto-alert-v2:task:{stable_task_id}"))


def execution_metadata(
    *,
    task_id: str | UUID,
    request_id: str,
    operation: str,
    product_run_id: str,
    parent_official_run_id: str | None = None,
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    lineage = {
        "operation": operation,
        "product_run_id": product_run_id,
        **(
            {"parent_official_run_id": parent_official_run_id}
            if parent_official_run_id is not None
            else {}
        ),
        **({"checkpoint_id": checkpoint_id} if checkpoint_id is not None else {}),
    }
    return {
        "correlation_id": correlation_id_for_task(task_id),
        "request_id": request_id,
        "lineage": lineage,
    }


async def request_identity_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    token = _request_id.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def transport_headers(
    *,
    request_id: str,
    authorization: str | None = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    headers = {"x-request-id": request_id}
    if authorization is not None:
        headers["authorization"] = authorization
    if extra is not None:
        headers.update(extra)
    return headers
