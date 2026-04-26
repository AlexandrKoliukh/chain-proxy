import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


async def test_unauthenticated_request_to_root_returns_401(client, initial_password):
    resp = await client.get("/")

    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate", "").lower().startswith("basic")


async def test_wrong_password_returns_401(client, initial_password):
    resp = await client.get("/", auth=("admin", "wrong"))

    assert resp.status_code == 401


async def test_root_redirects_to_settings_when_authenticated(client, initial_password):
    resp = await client.get("/", auth=BASIC, follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings"


async def test_password_change_too_short_returns_400(client, initial_password):
    resp = await client.post(
        "/settings/password",
        data={"new_password": "short"},
        auth=BASIC,
    )

    assert resp.status_code == 400


async def test_password_change_replaces_credentials_and_removes_initial(
    client, ui_modules, initial_password
):
    paths = ui_modules["paths"]
    auth = ui_modules["auth"]

    resp = await client.post(
        "/settings/password",
        data={"new_password": "new-strong-pass"},
        auth=BASIC,
    )

    assert resp.status_code == 200
    assert auth.verify("admin", "testpass123") is False
    assert auth.verify("admin", "new-strong-pass") is True
    assert not paths.INITIAL_PASSWORD_FILE.exists()


async def test_old_password_stops_working_after_change(client, ui_modules, initial_password):
    await client.post(
        "/settings/password",
        data={"new_password": "another-good-pw"},
        auth=BASIC,
    )

    resp = await client.get("/settings", auth=BASIC)

    assert resp.status_code == 401
