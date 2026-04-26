"""Smoke test of the production docker image.

Builds the image, runs it, polls /healthz, asserts logs contain the initial
admin password line. Gated on CHAIN_PROXY_TEST_DOCKER=1 because docker is
not always available in dev environments.
"""
import os
import shutil
import ssl
import subprocess
import time
import urllib.request
import uuid

import pytest

pytestmark = [pytest.mark.api, pytest.mark.docker_image]


def _docker_available() -> bool:
    if os.environ.get("CHAIN_PROXY_TEST_DOCKER") != "1":
        return False
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "info"], check=True, capture_output=True, timeout=5
        )
        return True
    except Exception:
        return False


pytestmark.append(
    pytest.mark.skipif(
        not _docker_available(),
        reason="docker unavailable or CHAIN_PROXY_TEST_DOCKER!=1",
    )
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMAGE = "chain-proxy-ui:test"
PORT = 18443


def test_docker_image_starts_and_healthz_responds():
    container = f"cpx-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["docker", "build", "-t", IMAGE, REPO_ROOT],
        check=True, capture_output=True,
    )
    proc = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "--name", container,
            "-p", f"{PORT}:8443",
            "-e", "CHAIN_PROXY_DATA=/tmp/cpx",
            "-e", "CHAIN_PROXY_CN=test",
            IMAGE,
        ],
        check=True, capture_output=True, text=True,
    )
    try:
        ctx = ssl._create_unverified_context()
        deadline = time.time() + 30
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"https://127.0.0.1:{PORT}/healthz", context=ctx, timeout=2
                ) as resp:
                    assert resp.status == 200
                    break
            except Exception as exc:
                last_err = exc
                time.sleep(0.5)
        else:
            pytest.fail(f"/healthz never responded: {last_err}")

        logs = subprocess.run(
            ["docker", "logs", container],
            check=True, capture_output=True, text=True,
        ).stdout + subprocess.run(
            ["docker", "logs", container],
            check=True, capture_output=True, text=True,
        ).stderr
        assert "initial admin password:" in logs
    finally:
        subprocess.run(["docker", "stop", container], capture_output=True)
