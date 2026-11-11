import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def post_json(url: str, headers: dict[str, str] | None, payload: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, headers=headers or {})
        response.raise_for_status()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _post_json_response(client: httpx.AsyncClient, url: str, headers: dict[str, str] | None, payload: dict[str, Any]) -> httpx.Response:
    print(url,payload)
    response = await client.post(url, json=payload, headers=headers or {})
    response.raise_for_status()
    return response


async def submit_and_await_result(
    url: str,
    headers: dict[str, str] | None,
    payload: dict[str, Any],
    job_id: str,
    poll_interval: float = 10.0,
    max_wait: float = 600.0,
) -> Any:
    """For an external lookup whose own processing can take minutes, not
    just seconds (e.g. the Missing Terms worker's candidate search): POSTs
    the job (job_id included in the body so the external API can track it),
    then either uses its immediate response -- a fast API can reply with
    the full result body straight away, HTTP 200 -- or, on HTTP 202,
    switches to polling `GET {url}?job_id=...` every poll_interval seconds
    (202 = still running, 200 = done) until ready or max_wait elapses."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await _post_json_response(client, url, headers, payload)
        if response.status_code != 202:
            return response.json()

        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            response = await client.get(url, params={"job_id": job_id}, headers=headers or {})
            if response.status_code == 202:
                continue
            response.raise_for_status()
            return response.json()

        raise TimeoutError(f"External API did not return a result for job {job_id} within {int(max_wait)}s")
