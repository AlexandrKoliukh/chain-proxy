import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


async def test_client_page_shows_vless_link_when_keys_present(
    client, ui_modules, initial_password
):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "1.2.3.4"
    cfg.keys.entry_public_key = "PK"
    cfg.keys.entry_short_id = "abcd"
    cfg.keys.entry_client_uuid = "11111111-1111-1111-1111-111111111111"
    cfg_mod.save(cfg)

    resp = await client.get("/clients", auth=BASIC)

    assert resp.status_code == 200
    assert "vless://" in resp.text
    assert "1.2.3.4:443" in resp.text


async def test_client_page_shows_missing_reason_when_keys_absent(
    client, ui_modules, initial_password
):
    cfg_mod = ui_modules["config"]
    cfg_mod.save(cfg_mod.Config())

    resp = await client.get("/clients", auth=BASIC)

    assert resp.status_code == 200
    assert "vless://" not in resp.text
    assert "IP_VPS1" in resp.text or "ключи" in resp.text or "не задан" in resp.text
