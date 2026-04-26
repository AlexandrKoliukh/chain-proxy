"""Build vless:// URIs (matches ansible/playbooks/site.yml's Jinja formula)
and render QR codes as base64 PNG.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

import qrcode

from .config import Config


def _uri(client_id: str, email: str, ip: str, cfg: Config) -> str:
    return (
        f"vless://{client_id}@{ip}:443"
        f"?type=tcp&security=reality"
        f"&pbk={cfg.keys.entry_public_key}"
        f"&fp={cfg.reality.fingerprint}"
        f"&sni={cfg.reality.dest_host}"
        f"&sid={cfg.keys.entry_short_id}"
        f"&flow=xtls-rprx-vision#chain-ru-{email}"
    )


def _qr_png_b64(text: str) -> str:
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build(cfg: Config) -> list[dict]:
    """Returns a list of {email, uri, qr} for each entry client.

    Returns an empty list if the config isn't ready (no IP, no public key, etc.).
    """
    ip = cfg.hosts.vps1_ip
    if not ip or not cfg.keys.entry_public_key or not cfg.keys.entry_short_id:
        return []
    clients: list[tuple[str, str]] = []
    if cfg.keys.entry_client_uuid:
        clients.append(("admin", cfg.keys.entry_client_uuid))
    if cfg.keys.entry_friends_uuid:
        clients.append(("friends", cfg.keys.entry_friends_uuid))
    out = []
    for email, uuid in clients:
        uri = _uri(uuid, email, ip, cfg)
        out.append({"email": email, "uri": uri, "qr": _qr_png_b64(uri)})
    return out


def missing_reasons(cfg: Config) -> Optional[str]:
    if not cfg.hosts.vps1_ip:
        return "IP_VPS1 не задан"
    if not cfg.keys.entry_public_key:
        return "ключи ещё не сгенерированы (нажмите Gen keys)"
    if not cfg.keys.entry_short_id:
        return "short_id отсутствует"
    return None
