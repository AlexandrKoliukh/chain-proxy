import re

import pytest

pytestmark = pytest.mark.unit

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_new_client_appends_entry_with_uuid4(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg = cfg_mod.new_client("alice", cfg)

    assert len(cfg.clients) == 1
    assert cfg.clients[0].name == "alice"
    assert _UUID_RE.match(cfg.clients[0].uuid)


def test_new_client_rejects_invalid_name(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()

    with pytest.raises(ValueError, match="Invalid client name"):
        cfg_mod.new_client("bad name!", cfg)


def test_new_client_rejects_empty_name(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()

    with pytest.raises(ValueError, match="Invalid client name"):
        cfg_mod.new_client("", cfg)


def test_new_client_rejects_duplicate_name(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg = cfg_mod.new_client("bob", cfg)

    with pytest.raises(ValueError, match="already exists"):
        cfg_mod.new_client("bob", cfg)


def test_remove_client_removes_by_name(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg = cfg_mod.new_client("alice", cfg)
    cfg = cfg_mod.new_client("bob", cfg)

    cfg = cfg_mod.remove_client("alice", cfg)

    assert [c.name for c in cfg.clients] == ["bob"]


def test_remove_client_noop_for_unknown_name(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg = cfg_mod.new_client("alice", cfg)

    cfg = cfg_mod.remove_client("nonexistent", cfg)

    assert len(cfg.clients) == 1


def test_migration_seeds_clients_from_legacy_uuids(ui_modules, tmp_data_dir):
    cfg_mod = ui_modules["config"]
    import yaml

    cfg = cfg_mod.Config()
    cfg.keys.entry_client_uuid = "aaaa-admin"
    cfg.keys.entry_friends_uuid = "bbbb-friends"
    cfg_mod.save(cfg)

    # Strip clients list to simulate a pre-migration config file
    data = yaml.safe_load((tmp_data_dir / "config.yml").read_text())
    data["clients"] = []
    (tmp_data_dir / "config.yml").write_text(yaml.safe_dump(data))

    loaded = cfg_mod.load()

    assert [c.name for c in loaded.clients] == ["admin", "friends"]
    assert loaded.clients[0].uuid == "aaaa-admin"
    assert loaded.clients[1].uuid == "bbbb-friends"


def test_to_env_emits_entry_clients_json(ui_modules):
    cfg_mod = ui_modules["config"]
    import json

    cfg = cfg_mod.Config()
    cfg = cfg_mod.new_client("alice", cfg)
    cfg = cfg_mod.new_client("bob", cfg)

    env = cfg.to_env()

    assert "ENTRY_CLIENTS_JSON" in env
    parsed = json.loads(env["ENTRY_CLIENTS_JSON"])
    assert parsed == [
        {"email": "alice", "id": cfg.clients[0].uuid},
        {"email": "bob",   "id": cfg.clients[1].uuid},
    ]


def test_to_env_omits_clients_json_when_empty(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()

    env = cfg.to_env()

    assert "ENTRY_CLIENTS_JSON" not in env


def test_vless_build_uses_clients_list(ui_modules):
    cfg_mod = ui_modules["config"]
    vless = ui_modules["vless"]

    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "1.2.3.4"
    cfg.keys.entry_public_key = "PK"
    cfg.keys.entry_short_id = "sid"
    cfg = cfg_mod.new_client("carol", cfg)

    result = vless.build(cfg)

    assert len(result) == 1
    assert result[0]["email"] == "carol"
    assert "vless://" in result[0]["uri"]


def test_clients_roundtrip_through_save_load(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg = cfg_mod.new_client("dave", cfg)
    saved_uuid = cfg.clients[0].uuid
    cfg_mod.save(cfg)

    loaded = cfg_mod.load()

    assert len(loaded.clients) == 1
    assert loaded.clients[0].name == "dave"
    assert loaded.clients[0].uuid == saved_uuid
