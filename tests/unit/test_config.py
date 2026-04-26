import pytest

pytestmark = pytest.mark.unit


def test_to_env_drops_empty_values(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()

    env = cfg.to_env()

    assert "IP_VPS1" not in env
    assert "ENTRY_PRIVATE_KEY" not in env
    assert env["VPS2_USER"] == "root"
    assert env["VPS2_PORT"] == "22"
    assert env["REALITY_DEST_HOST"] == "www.microsoft.com"


def test_to_env_includes_filled_values(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "1.2.3.4"
    cfg.hosts.vps2_ip = "5.6.7.8"
    cfg.keys.entry_public_key = "PK"
    cfg.keys.wg_vps1_private = "wgpriv"

    env = cfg.to_env()

    assert env["IP_VPS1"] == "1.2.3.4"
    assert env["IP_VPS2"] == "5.6.7.8"
    assert env["ENTRY_PUBLIC_KEY"] == "PK"
    assert env["WG_VPS1_PRIVATE"] == "wgpriv"


def test_save_then_load_roundtrip(ui_modules):
    cfg_mod = ui_modules["config"]

    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "10.0.0.1"
    cfg.reality.dest_host = "example.com"
    cfg.keys.entry_short_id = "abcd"
    cfg_mod.save(cfg)

    loaded = cfg_mod.load()

    assert loaded.hosts.vps1_ip == "10.0.0.1"
    assert loaded.reality.dest_host == "example.com"
    assert loaded.keys.entry_short_id == "abcd"


def test_load_returns_default_when_no_file(ui_modules):
    cfg_mod = ui_modules["config"]

    cfg = cfg_mod.load()

    assert cfg.hosts.vps1_ip == ""
    assert cfg.reality.fingerprint == "chrome"


def test_parse_env_keys_file_extracts_block(ui_modules):
    cfg_mod = ui_modules["config"]
    paths = ui_modules["paths"]

    paths.ENV_KEYS_FILE.write_text(
        "noise above\n"
        "# === chain-proxy keys (do not edit by hand) ===\n"
        "ENTRY_CLIENT_UUID=uuid-1\n"
        "ENTRY_PUBLIC_KEY=pubkey\n"
        "WG_VPS1_PRIVATE=wgpriv\n"
        "# === end chain-proxy keys ===\n"
        "noise below\n"
        "ENTRY_FRIENDS_UUID=should-be-ignored\n"
    )

    raw = cfg_mod.parse_env_keys_file()

    assert raw == {
        "ENTRY_CLIENT_UUID": "uuid-1",
        "ENTRY_PUBLIC_KEY": "pubkey",
        "WG_VPS1_PRIVATE": "wgpriv",
    }


def test_parse_env_keys_file_returns_empty_when_missing(ui_modules):
    cfg_mod = ui_modules["config"]

    assert cfg_mod.parse_env_keys_file() == {}


def test_apply_generated_keys_maps_env_vars_to_attrs(ui_modules):
    cfg_mod = ui_modules["config"]
    cfg = cfg_mod.Config()

    out = cfg_mod.apply_generated_keys(
        cfg,
        {
            "ENTRY_CLIENT_UUID": "u1",
            "ENTRY_PUBLIC_KEY": "pk",
            "WG_VPS2_PUBLIC": "wgpub2",
            "UNKNOWN": "ignored",
        },
    )

    assert out.keys.entry_client_uuid == "u1"
    assert out.keys.entry_public_key == "pk"
    assert out.keys.wg_vps2_public == "wgpub2"
    assert out.keys.entry_short_id == ""
