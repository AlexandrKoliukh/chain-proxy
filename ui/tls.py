"""Self-signed TLS cert generated on first start."""
from __future__ import annotations

import os
import subprocess

from .paths import TLS_CERT, TLS_DIR, TLS_KEY


def ensure(common_name: str = "chain-proxy") -> tuple[str, str]:
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    if TLS_CERT.exists() and TLS_KEY.exists():
        return str(TLS_CERT), str(TLS_KEY)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "3650",
            "-subj",
            f"/CN={common_name}",
            "-keyout",
            str(TLS_KEY),
            "-out",
            str(TLS_CERT),
        ],
        check=True,
        capture_output=True,
    )
    os.chmod(TLS_KEY, 0o600)
    os.chmod(TLS_CERT, 0o644)
    return str(TLS_CERT), str(TLS_KEY)
