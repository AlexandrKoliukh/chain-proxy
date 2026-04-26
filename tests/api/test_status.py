import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


async def test_status_renders_with_mocked_collector(
    client, ui_modules, initial_password, monkeypatch
):
    status_mod = ui_modules["status"]

    async def fake_collect(cfg):
        return {
            "vps1": {
                "label": "VPS1 (entry)",
                "ok": True,
                "items": [
                    {"name": "xray", "value": "active"},
                    {"name": "wg handshake", "value": "12s ago"},
                    {"name": "fwmark policy", "value": "from all fwmark 0xff lookup 100"},
                ],
            },
            "vps2": {
                "label": "VPS2 (exit)",
                "ok": False,
                "items": [
                    {"name": "wg-quick@wg0", "value": "inactive"},
                ],
            },
        }

    monkeypatch.setattr(status_mod, "collect", fake_collect)

    resp = await client.get("/status", auth=BASIC)

    assert resp.status_code == 200
    body = resp.text
    assert "VPS1" in body
    assert "VPS2" in body
    assert "12s ago" in body
    assert "inactive" in body
