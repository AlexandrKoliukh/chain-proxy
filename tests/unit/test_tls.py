import shutil

import pytest

pytestmark = pytest.mark.unit


def _have_openssl() -> bool:
    return shutil.which("openssl") is not None


@pytest.mark.skipif(not _have_openssl(), reason="openssl binary not available")
def test_ensure_creates_self_signed_cert(ui_modules):
    tls = ui_modules["tls"]
    paths = ui_modules["paths"]

    cert_path, key_path = tls.ensure("test-cn")

    assert paths.TLS_CERT.exists()
    assert paths.TLS_KEY.exists()
    assert cert_path == str(paths.TLS_CERT)
    assert key_path == str(paths.TLS_KEY)
    assert "BEGIN CERTIFICATE" in paths.TLS_CERT.read_text()


@pytest.mark.skipif(not _have_openssl(), reason="openssl binary not available")
def test_ensure_does_not_regenerate_when_cert_present(ui_modules):
    tls = ui_modules["tls"]
    paths = ui_modules["paths"]

    tls.ensure("first")
    cert_first = paths.TLS_CERT.read_bytes()

    tls.ensure("second")
    cert_second = paths.TLS_CERT.read_bytes()

    assert cert_first == cert_second
