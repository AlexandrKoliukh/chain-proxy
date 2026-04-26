import time

import pytest

pytestmark = pytest.mark.unit


def test_handshake_age_never_when_zero(ui_modules):
    status = ui_modules["status"]

    out = "PEERPUBKEY\t0"

    assert status._handshake_age(out) == "never"


def test_handshake_age_seconds(ui_modules):
    status = ui_modules["status"]
    ts = int(time.time()) - 12

    out = f"PEERPUBKEY\t{ts}"

    assert status._handshake_age(out).endswith("s ago")
    assert "12" in status._handshake_age(out) or "13" in status._handshake_age(out)


def test_handshake_age_minutes(ui_modules):
    status = ui_modules["status"]
    ts = int(time.time()) - (3 * 60 + 15)

    out = f"PEERPUBKEY\t{ts}"

    assert "m " in status._handshake_age(out)
    assert " ago" in status._handshake_age(out)


def test_handshake_age_hours(ui_modules):
    status = ui_modules["status"]
    ts = int(time.time()) - (2 * 3600 + 30 * 60)

    out = f"PEERPUBKEY\t{ts}"

    rendered = status._handshake_age(out)
    assert "h " in rendered
    assert " ago" in rendered


def test_handshake_age_returns_input_when_no_match(ui_modules):
    status = ui_modules["status"]

    assert status._handshake_age("") == "no peer"
    assert status._handshake_age("garbage line") == "garbage line"
