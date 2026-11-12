import httpx
import pytest

from app.core.webhook_client import submit_and_await_result


def _patch_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


async def test_submit_and_await_result_fast_path_skips_polling(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[{"sub_domain": "Alterations", "term_name": "Roof", "candidates": []}])

    _patch_transport(monkeypatch, handler)

    result = await submit_and_await_result("http://test/lookup", None, {"job_id": "j1", "rows": []}, job_id="j1")

    assert len(calls) == 1
    assert result == [{"sub_domain": "Alterations", "term_name": "Roof", "candidates": []}]


async def test_submit_and_await_result_polls_until_ready(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(202)
        # First two GET polls still processing, third one is ready.
        if len([c for c in calls if c.method == "GET"]) < 3:
            return httpx.Response(202)
        return httpx.Response(200, json=[{"sub_domain": "Alterations", "term_name": "Roof", "candidates": [{"Page": "4"}]}])

    _patch_transport(monkeypatch, handler)

    result = await submit_and_await_result("http://test/lookup", None, {"job_id": "j2", "rows": []}, job_id="j2", poll_interval=0)

    assert calls[0].method == "POST"
    assert all(c.method == "GET" and c.url.params["job_id"] == "j2" for c in calls[1:])
    assert result == [{"sub_domain": "Alterations", "term_name": "Roof", "candidates": [{"Page": "4"}]}]


async def test_submit_and_await_result_survives_a_transient_poll_timeout(monkeypatch):
    # Regression: a real external API observed in practice can occasionally
    # take longer than the client timeout just to answer a "still running?"
    # status check -- that single slow/flaky poll must not fail the whole
    # job, since there's still plenty of max_wait budget left to try again.
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(202)
        gets_so_far = len([c for c in calls if c.method == "GET"])
        if gets_so_far == 1:
            raise httpx.ReadTimeout("")
        return httpx.Response(200, json=[{"sub_domain": "Alterations", "term_name": "Roof", "candidates": [{"Page": "4"}]}])

    _patch_transport(monkeypatch, handler)

    result = await submit_and_await_result("http://test/lookup", None, {"job_id": "j4", "rows": []}, job_id="j4", poll_interval=0)

    assert len([c for c in calls if c.method == "GET"]) == 2
    assert result == [{"sub_domain": "Alterations", "term_name": "Roof", "candidates": [{"Page": "4"}]}]


async def test_submit_and_await_result_times_out_if_never_ready(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202)

    _patch_transport(monkeypatch, handler)

    with pytest.raises(TimeoutError):
        await submit_and_await_result("http://test/lookup", None, {"job_id": "j3", "rows": []}, job_id="j3", poll_interval=0, max_wait=0)
