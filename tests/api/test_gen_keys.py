import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


async def test_gen_keys_writes_keys_into_config(client, ui_modules, initial_password, monkeypatch):
    cfg_mod = ui_modules["config"]
    keys_mod = ui_modules["keys"]
    paths = ui_modules["paths"]

    async def fake_regenerate(cfg):
        paths.ENV_KEYS_FILE.write_text(
            "# === chain-proxy keys ===\n"
            "ENTRY_CLIENT_UUID=11111111-1111-1111-1111-111111111111\n"
            "ENTRY_PUBLIC_KEY=PUBKEY\n"
            "ENTRY_SHORT_ID=abcd1234\n"
            "WG_VPS1_PRIVATE=wgpriv1\n"
            "# === end chain-proxy keys ===\n"
        )
        raw = cfg_mod.parse_env_keys_file()
        cfg = cfg_mod.apply_generated_keys(cfg, raw)
        cfg_mod.save(cfg)
        return 0, "ok", cfg

    monkeypatch.setattr(keys_mod, "regenerate", fake_regenerate)

    resp = await client.post("/api/gen-keys", auth=BASIC)

    assert resp.status_code == 200
    cfg = cfg_mod.load()
    assert cfg.keys.entry_public_key == "PUBKEY"
    assert cfg.keys.entry_short_id == "abcd1234"
    assert cfg.keys.wg_vps1_private == "wgpriv1"


async def test_gen_keys_returns_500_on_script_failure(
    client, ui_modules, initial_password, monkeypatch
):
    keys_mod = ui_modules["keys"]

    async def failing(cfg):
        return 1, "openssl missing", cfg

    monkeypatch.setattr(keys_mod, "regenerate", failing)

    resp = await client.post("/api/gen-keys", auth=BASIC)

    assert resp.status_code == 500
    assert "gen-keys failed" in resp.text
