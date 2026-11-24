from unittest.mock import Mock
import httpx
import pytest
import requests
from postgrest.exceptions import APIError
from prefect.states import Failed

from pipeline.llm_enrich.enrich import EnrichmentDatabaseError
from pipeline.llm_enrich.openrouter_client import (
    OpenRouterBudgetExhausted,
    OpenRouterRateLimited,
)
from pipeline.orchestration.tasks import is_transient_error

pytestmark = pytest.mark.unit

def _wrap_from(exc, wrapper=RuntimeError):
    try:
        try:
            raise exc
        except Exception as e:
            raise wrapper(f"wrapped: {e}") from e
    except Exception as wrapped:
        return wrapped


def _wrap_from_none(exc):
    try:
        try:
            raise exc
        except Exception:
            raise RuntimeError("Could not reach OpenWeather") from None
    except Exception as wrapped:
        return wrapped


def _requests_http_error(status_code):
    resp = Mock(status_code=status_code)
    return requests.exceptions.HTTPError(f"HTTP {status_code}", response=resp)


@pytest.mark.parametrize(
    "exc",
    [
        _wrap_from(httpx.TimeoutException("timeout")),
        _wrap_from(httpx.ConnectError("connect failed")),
        _wrap_from(APIError({"code": "503", "message": "Service Unavailable"})),
        _wrap_from(httpx.TimeoutException("db timeout"), wrapper=EnrichmentDatabaseError),
        _wrap_from_none(requests.exceptions.Timeout("openweather timeout")),
        _requests_http_error(500),
        _requests_http_error(429),
        OpenRouterRateLimited("rate limited"),
    ],
)
def test_is_transient_error_retries(exc):
    assert is_transient_error(None, None, Failed(data=exc)) is True


@pytest.mark.parametrize(
    "exc",
    [
        _wrap_from(ValueError("bad payload")),
        _wrap_from(APIError({"code": "23505", "message": "duplicate key"})),
        _requests_http_error(401),
        _requests_http_error(404),
        OpenRouterBudgetExhausted("out of credits"),
        RuntimeError("plain unwrapped error"),
    ],
)
def test_is_transient_error_does_not_retry(exc):
    assert is_transient_error(None, None, Failed(data=exc)) is False