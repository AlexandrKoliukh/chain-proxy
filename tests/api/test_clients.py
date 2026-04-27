import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


def _ready_cfg(cfg_mod):
    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "1.2.3.4"
    cfg.keys.entry_public_key = "PK"
    cfg.keys.entry_short_id = "sid"
    return cfg


async def test_clients_page_requires_auth(client, initial_password):
    resp = await client.get("/clients")
    assert resp.status_code == 401


async def test_clients_page_shows_add_form(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg_mod.save(_ready_cfg(cfg_mod))

    resp = await client.get("/clients", auth=BASIC)

    assert resp.status_code == 200
    assert "Добавить клиента" in resp.text


async def test_add_client_creates_entry_and_redirects(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg_mod.save(_ready_cfg(cfg_mod))

    resp = await client.post(
        "/clients", data={"name": "alice"}, auth=BASIC, follow_redirects=False
    )

    assert resp.status_code == 303
    assert "/clients" in resp.headers["location"]
    cfg = cfg_mod.load()
    assert any(c.name == "alice" for c in cfg.clients)


async def test_add_client_rejects_invalid_name(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg_mod.save(_ready_cfg(cfg_mod))

    resp = await client.post("/clients", data={"name": "bad name!"}, auth=BASIC)

    assert resp.status_code == 400
    assert "Имя клиента" in resp.text


async def test_add_client_rejects_duplicate(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg = _ready_cfg(cfg_mod)
    cfg = cfg_mod.new_client("alice", cfg)
    cfg_mod.save(cfg)

    resp = await client.post("/clients", data={"name": "alice"}, auth=BASIC)

    assert resp.status_code == 400
    assert "уже существует" in resp.text


async def test_delete_client_removes_entry_and_redirects(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg = _ready_cfg(cfg_mod)
    cfg = cfg_mod.new_client("alice", cfg)
    cfg = cfg_mod.new_client("bob", cfg)
    cfg_mod.save(cfg)

    resp = await client.post(
        "/clients/alice/delete", auth=BASIC, follow_redirects=False
    )

    assert resp.status_code == 303
    cfg = cfg_mod.load()
    assert not any(c.name == "alice" for c in cfg.clients)
    assert any(c.name == "bob" for c in cfg.clients)


async def test_delete_last_client_returns_400(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg = _ready_cfg(cfg_mod)
    cfg = cfg_mod.new_client("solo", cfg)
    cfg_mod.save(cfg)

    resp = await client.post("/clients/solo/delete", auth=BASIC)

    assert resp.status_code == 400
    assert "последнего" in resp.text


async def test_download_config_returns_vless_uri(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg = _ready_cfg(cfg_mod)
    cfg = cfg_mod.new_client("carol", cfg)
    cfg_mod.save(cfg)

    resp = await client.get("/clients/carol/config", auth=BASIC)

    assert resp.status_code == 200
    assert "vless://" in resp.text
    assert "carol" in resp.headers.get("content-disposition", "")


async def test_download_config_404_for_unknown_client(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg_mod.save(_ready_cfg(cfg_mod))

    resp = await client.get("/clients/ghost/config", auth=BASIC)

    assert resp.status_code == 404


async def test_old_client_url_redirects(client, ui_modules, initial_password):
    resp = await client.get("/client", auth=BASIC, follow_redirects=False)

    assert resp.status_code == 301
    assert resp.headers["location"] == "/clients"


async def test_clients_page_shows_deploy_banner_after_add(client, ui_modules, initial_password):
    cfg_mod = ui_modules["config"]
    cfg_mod.save(_ready_cfg(cfg_mod))

    resp = await client.post(
        "/clients", data={"name": "alice"}, auth=BASIC, follow_redirects=True
    )

    assert resp.status_code == 200
    assert "Deploy" in resp.text
