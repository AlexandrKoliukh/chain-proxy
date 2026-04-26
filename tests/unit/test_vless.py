import base64
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.unit


def _ready_cfg(cfg_mod):
    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "1.2.3.4"
    cfg.reality.dest_host = "www.microsoft.com"
    cfg.reality.fingerprint = "chrome"
    cfg.keys.entry_public_key = "PUBKEY"
    cfg.keys.entry_short_id = "abcd1234"
    cfg.keys.entry_client_uuid = "11111111-1111-1111-1111-111111111111"
    cfg.keys.entry_friends_uuid = "22222222-2222-2222-2222-222222222222"
    return cfg


def test_build_returns_two_clients_when_both_uuids_present(ui_modules):
    vless = ui_modules["vless"]
    cfg = _ready_cfg(ui_modules["config"])

    clients = vless.build(cfg)

    assert [c["email"] for c in clients] == ["admin", "friends"]


def test_build_uri_has_required_query_parameters(ui_modules):
    vless = ui_modules["vless"]
    cfg = _ready_cfg(ui_modules["config"])

    uri = vless.build(cfg)[0]["uri"]

    parsed = urlparse(uri)
    assert parsed.scheme == "vless"
    assert parsed.username == "11111111-1111-1111-1111-111111111111"
    assert parsed.hostname == "1.2.3.4"
    assert parsed.port == 443

    qs = parse_qs(parsed.query)
    assert qs["security"] == ["reality"]
    assert qs["pbk"] == ["PUBKEY"]
    assert qs["sni"] == ["www.microsoft.com"]
    assert qs["sid"] == ["abcd1234"]
    assert qs["fp"] == ["chrome"]
    assert qs["flow"] == ["xtls-rprx-vision"]
    assert parsed.fragment == "chain-ru-admin"


def test_build_qr_is_valid_base64_png(ui_modules):
    vless = ui_modules["vless"]
    cfg = _ready_cfg(ui_modules["config"])

    qr_b64 = vless.build(cfg)[0]["qr"]
    raw = base64.b64decode(qr_b64)

    assert raw.startswith(b"\x89PNG\r\n\x1a\n")


def test_build_returns_empty_when_no_ip(ui_modules):
    vless = ui_modules["vless"]
    cfg = _ready_cfg(ui_modules["config"])
    cfg.hosts.vps1_ip = ""

    assert vless.build(cfg) == []


def test_build_returns_empty_when_no_public_key(ui_modules):
    vless = ui_modules["vless"]
    cfg = _ready_cfg(ui_modules["config"])
    cfg.keys.entry_public_key = ""

    assert vless.build(cfg) == []


def test_build_skips_empty_uuid(ui_modules):
    vless = ui_modules["vless"]
    cfg = _ready_cfg(ui_modules["config"])
    cfg.keys.entry_friends_uuid = ""

    clients = vless.build(cfg)

    assert [c["email"] for c in clients] == ["admin"]


def test_missing_reasons(ui_modules):
    vless = ui_modules["vless"]
    cfg_mod = ui_modules["config"]

    empty = cfg_mod.Config()
    assert vless.missing_reasons(empty) == "IP_VPS1 не задан"

    cfg = cfg_mod.Config()
    cfg.hosts.vps1_ip = "1.2.3.4"
    assert vless.missing_reasons(cfg) and "ключи" in vless.missing_reasons(cfg)

    cfg.keys.entry_public_key = "pk"
    assert vless.missing_reasons(cfg) == "short_id отсутствует"

    cfg.keys.entry_short_id = "sid"
    assert vless.missing_reasons(cfg) is None
