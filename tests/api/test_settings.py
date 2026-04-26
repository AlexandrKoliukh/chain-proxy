import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


async def test_get_settings_requires_auth(client, initial_password):
    resp = await client.get("/settings")
    assert resp.status_code == 401


async def test_get_settings_renders_for_authed_user(client, initial_password):
    resp = await client.get("/settings", auth=BASIC)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_post_settings_persists_to_yaml(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    resp = await client.post(
        "/settings",
        data={
            "vps1_ip": "10.0.0.1",
            "vps2_ip": "20.0.0.2",
            "vps2_user": "ubuntu",
            "vps2_password": "secret-pw",
            "vps2_port": "2222",
            "reality_dest_host": "example.com",
            "reality_fingerprint": "firefox",
        },
        auth=BASIC,
    )

    assert resp.status_code == 200
    cfg = cfg_mod.load()
    assert cfg.hosts.vps1_ip == "10.0.0.1"
    assert cfg.hosts.vps2_ip == "20.0.0.2"
    assert cfg.hosts.vps2_user == "ubuntu"
    assert cfg.hosts.vps2_password == "secret-pw"
    assert cfg.hosts.vps2_port == 2222
    assert cfg.reality.dest_host == "example.com"
    assert cfg.reality.fingerprint == "firefox"


async def test_post_settings_does_not_clear_password_on_empty_submit(
    client, ui_modules, initial_password
):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg.hosts.vps2_password = "preserved"
    cfg_mod.save(cfg)

    await client.post(
        "/settings",
        data={
            "vps1_ip": "1.1.1.1",
            "vps2_ip": "2.2.2.2",
            "vps2_user": "root",
            "vps2_password": "",
            "vps2_port": "22",
            "reality_dest_host": "www.microsoft.com",
            "reality_fingerprint": "chrome",
        },
        auth=BASIC,
    )

    assert cfg_mod.load().hosts.vps2_password == "preserved"
