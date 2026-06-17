"""Tests for session-expiry detection and re-login/retry behavior.

Runnable two ways:
  * ``pytest`` (no async plugin required — each test wraps asyncio.run)
  * ``python tests/test_session_retry.py`` (self-contained runner)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from synology_dsm.exceptions import (  # noqa: E402
    API_AUTH,
    SynologyDSMAPIErrorException,
    SynologyDSMNotLoggedInException,
)

from synology_mcp.session_retry import (  # noqa: E402
    SESSION_RETRY_CODES,
    api_error_code,
    is_session_error,
    with_session_retry,
)


def _api_error(code: int) -> SynologyDSMAPIErrorException:
    """Build the exact exception py-synologydsm-api raises for a DSM error."""
    return SynologyDSMAPIErrorException("SYNO.DSM.Info", code, None)


# --- pure helpers --------------------------------------------------------- #

def test_api_error_code_extracts_code():
    assert api_error_code(_api_error(106)) == 106
    assert api_error_code(_api_error(119)) == 119
    assert api_error_code(ValueError("not an api error")) is None


def test_is_session_error():
    for code in (106, 107, 119):
        assert is_session_error(_api_error(code)) is True, code
    assert is_session_error(SynologyDSMNotLoggedInException()) is True
    # 105 = insufficient permission, NOT a session-lifetime error
    assert is_session_error(_api_error(105)) is False
    assert is_session_error(ValueError("nope")) is False


def test_retry_codes_membership():
    assert SESSION_RETRY_CODES == frozenset({106, 107, 119})


# --- retry orchestration -------------------------------------------------- #

class _Caller:
    """Async callable that raises ``exc`` on the first ``fail_times`` calls."""

    def __init__(self, exc, fail_times=1, value="ok"):
        self.exc = exc
        self.fail_times = fail_times
        self.value = value
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self.value


class _Login:
    def __init__(self):
        self.calls = 0

    async def __call__(self):
        self.calls += 1


async def _retry_then_success(exc):
    caller = _Caller(exc, fail_times=1)
    login = _Login()
    result = await with_session_retry(caller, login, api="SYNO.DSM.Info")
    assert result == "ok"
    assert caller.calls == 2, "should call once, fail, re-login, call again"
    assert login.calls == 1, "should re-login exactly once"


def test_retries_once_on_106():
    asyncio.run(_retry_then_success(_api_error(106)))


def test_retries_once_on_not_logged_in():
    asyncio.run(_retry_then_success(SynologyDSMNotLoggedInException()))


async def _no_retry(exc, api, expected_exc):
    caller = _Caller(exc, fail_times=1)
    login = _Login()
    raised = False
    try:
        await with_session_retry(caller, login, api=api)
    except expected_exc:
        raised = True
    assert raised, f"expected {expected_exc.__name__} to propagate"
    assert caller.calls == 1, "must not retry"
    assert login.calls == 0, "must not re-login"


def test_does_not_retry_non_session_error():
    asyncio.run(_no_retry(ValueError("boom"), "SYNO.DSM.Info", ValueError))


def test_does_not_retry_auth_api():
    # A session error on the auth API itself must not trigger another login.
    asyncio.run(_no_retry(_api_error(106), API_AUTH, SynologyDSMAPIErrorException))


async def _second_failure_propagates():
    caller = _Caller(_api_error(106), fail_times=2)  # fails twice
    login = _Login()
    raised = False
    try:
        await with_session_retry(caller, login, api="SYNO.DSM.Info")
    except SynologyDSMAPIErrorException:
        raised = True
    assert raised, "second failure should propagate"
    assert caller.calls == 2, "original call + exactly one retry"
    assert login.calls == 1, "re-login attempted exactly once"


def test_second_failure_propagates():
    asyncio.run(_second_failure_propagates())


if __name__ == "__main__":
    failures = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {_name}: {exc!r}")
    print(f"\n{'ALL PASSED' if failures == 0 else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
