"""Shared helpers for recovering from expired DSM sessions.

DSM invalidates idle session IDs after a timeout. Both py-synologydsm-api's
own ``_request`` and our :class:`~synology_mcp.direct_client.DirectApiClient`
historically only auto-retried on error code 119 ("session ID not valid"), so
a 106 ("session timeout") — which DSM hands out for an idle session — left
every subsequent call failing until the process was restarted.

These helpers centralise the recovery: detect a session-expiry error, then
re-login and retry the call exactly once.
"""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from synology_dsm.exceptions import (
    API_AUTH,
    SynologyDSMAPIErrorException,
    SynologyDSMNotLoggedInException,
)

# DSM error codes that mean "your session is gone, log in again":
#   106 - session timeout (idle expiry — the case that broke us)
#   107 - session interrupted by a duplicate login
#   119 - session ID not valid
# Note: 105 ("insufficient permission") is deliberately excluded — it is not a
# session-lifetime problem and re-logging-in would not help.
SESSION_RETRY_CODES: frozenset[int] = frozenset({106, 107, 119})

T = TypeVar("T")


def api_error_code(exc: Exception) -> int | None:
    """Return the DSM error code from a SynologyDSMAPIErrorException, else None.

    py-synologydsm-api stores the error as a dict in ``exc.args[0]``:
    ``{"api": ..., "code": ..., "reason": ..., "details": ...}``.
    """
    if not isinstance(exc, SynologyDSMAPIErrorException):
        return None
    try:
        payload = exc.args[0]
    except IndexError:
        return None
    if isinstance(payload, dict):
        return payload.get("code")
    return None


def is_session_error(exc: Exception) -> bool:
    """True if the exception indicates an expired/invalid DSM session."""
    if isinstance(exc, SynologyDSMNotLoggedInException):
        return True
    return api_error_code(exc) in SESSION_RETRY_CODES


async def with_session_retry(
    call: Callable[[], Awaitable[T]],
    login: Callable[[], Awaitable[Any]],
    *,
    api: str = "",
) -> T:
    """Run ``await call()``; on a session-expiry error, re-login and retry once.

    Args:
        call: Zero-arg coroutine that performs the API call.
        login: Zero-arg coroutine that re-authenticates the session.
        api: The DSM API being called. Auth-API calls are never retried here
            (that would risk an infinite login loop), so they propagate as-is.

    Non-session errors propagate unchanged. If the single retry also fails,
    that second exception propagates.
    """
    try:
        return await call()
    except (SynologyDSMNotLoggedInException, SynologyDSMAPIErrorException) as exc:
        if api == API_AUTH or not is_session_error(exc):
            raise
        await login()
        return await call()
