import pytest

pytestmark = pytest.mark.api


async def test_healthz_no_auth_required(client):
    resp = await client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
