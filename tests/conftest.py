"""Shared fixtures: per-test tmp data dir, ASGI httpx client, subprocess mocks.

Each test runs in full isolation:
- CHAIN_PROXY_DATA / CHAIN_PROXY_ROOT point at a fresh tmp_path
- ui.paths is reloaded so module-level Path constants pick up the new env
- modules that captured old paths at import time (auth, tls, config, deploy, ...)
  are reloaded too
- nsenter wrapping is disabled (CHAIN_PROXY_NSENTER=0) so any accidental
  subprocess call won't try to enter the host pid namespace
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reload_ui(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    monkeypatch.setenv("CHAIN_PROXY_ROOT", str(tmp_path))
    monkeypatch.setenv("CHAIN_PROXY_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("CHAIN_PROXY_NSENTER", "0")

    modules = [
        "ui.paths",
        "ui.config",
        "ui.auth",
        "ui.tls",
        "ui.runner",
        "ui.keys",
        "ui.deploy",
        "ui.status",
        "ui.vless",
        "ui.main",
    ]
    for name in modules:
        sys.modules.pop(name, None)

    import ui.paths as paths
    paths.ensure_data_dirs()
    out = {"paths": paths}
    for name in modules[1:]:
        out[name.split(".")[1]] = importlib.import_module(name)
    return out


@pytest.fixture
def ui_modules(monkeypatch, tmp_path):
    """Return a dict of freshly-loaded ui.* modules bound to a tmp data dir."""
    return _reload_ui(monkeypatch, tmp_path)


@pytest.fixture
def tmp_data_dir(ui_modules) -> Path:
    return ui_modules["paths"].DATA


@pytest.fixture
def initial_password(ui_modules) -> str:
    return ui_modules["auth"].ensure_initial("testpass123")


@pytest.fixture
async def client(ui_modules):
    """httpx.AsyncClient bound to the FastAPI app via ASGITransport."""
    from httpx import ASGITransport, AsyncClient

    app = ui_modules["main"].app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as ac:
        yield ac
