"""AI tests never use a developer credential or an unmocked HTTP transport."""

import httpx
import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def no_live_model_network(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-dummy-not-a-real-key")

    async def reject_async(*args, **kwargs):
        raise AssertionError("Unmocked model network is forbidden in tests")

    def reject_sync(*args, **kwargs):
        raise AssertionError("Unmocked model network is forbidden in tests")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_sync)


@pytest.fixture(scope="session")
def ai_redis_url():
    from testcontainers.core.container import DockerContainer
    with DockerContainer("redis:7-alpine").with_exposed_ports(6379) as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}/0"


@pytest_asyncio.fixture
async def ai_redis(ai_redis_url):
    import redis.asyncio as redis
    client = redis.from_url(ai_redis_url, decode_responses=True)
    await client.flushdb()  # Only this fixture's newly created disposable container.
    try:
        yield client
    finally:
        await client.aclose()
