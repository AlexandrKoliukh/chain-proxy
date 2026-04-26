import pytest

pytestmark = pytest.mark.unit


def test_ensure_initial_creates_hash_and_initial_file(ui_modules):
    auth = ui_modules["auth"]
    paths = ui_modules["paths"]

    plain = auth.ensure_initial("hunter2pw")

    assert plain == "hunter2pw"
    assert paths.AUTH_FILE.exists()
    assert paths.INITIAL_PASSWORD_FILE.exists()
    assert paths.INITIAL_PASSWORD_FILE.read_text().strip() == "hunter2pw"


def test_ensure_initial_idempotent(ui_modules):
    auth = ui_modules["auth"]

    auth.ensure_initial("first")
    again = auth.ensure_initial("second")

    assert again == ""
    assert auth.verify("admin", "first") is True
    assert auth.verify("admin", "second") is False


def test_ensure_initial_random_when_no_password_given(ui_modules):
    auth = ui_modules["auth"]

    plain = auth.ensure_initial()

    assert plain
    assert len(plain) >= 16
    assert auth.verify("admin", plain) is True


def test_verify_rejects_wrong_password(ui_modules):
    auth = ui_modules["auth"]
    auth.ensure_initial("right")

    assert auth.verify("admin", "right") is True
    assert auth.verify("admin", "wrong") is False
    assert auth.verify("guest", "right") is False


def test_verify_returns_false_when_no_auth_file(ui_modules):
    auth = ui_modules["auth"]

    assert auth.verify("admin", "anything") is False


def test_change_password_updates_hash_and_removes_initial(ui_modules):
    auth = ui_modules["auth"]
    paths = ui_modules["paths"]
    auth.ensure_initial("old-pass")
    assert paths.INITIAL_PASSWORD_FILE.exists()

    auth.change_password("new-pass-12345")

    assert auth.verify("admin", "old-pass") is False
    assert auth.verify("admin", "new-pass-12345") is True
    assert not paths.INITIAL_PASSWORD_FILE.exists()
