"""Health view: xray on VPS1, wg handshake on both, fwmark policy route."""
from __future__ import annotations

import re
import shlex
from typing import TypedDict

from .config import Config
from .runner import run_capture

_HANDSHAKE_RE = re.compile(r"^\S+\s+(\d+)\s*$", re.MULTILINE)


class HostStatus(TypedDict):
    label: str
    ok: bool
    items: list[dict[str, str]]


async def _local(cmd: list[str]) -> str:
    rc, out = await run_capture(cmd)
    if rc != 0:
        return f"(exit {rc}) {out.strip()}"
    return out.strip()


async def _ssh(cfg: Config, remote_cmd: str) -> str:
    if not (cfg.hosts.vps2_ip and cfg.hosts.vps2_password):
        return "VPS2 credentials not set"
    cmd = [
        "sshpass",
        "-p",
        cfg.hosts.vps2_password,
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=5",
        "-p",
        str(cfg.hosts.vps2_port),
        f"{cfg.hosts.vps2_user}@{cfg.hosts.vps2_ip}",
        remote_cmd,
    ]
    rc, out = await run_capture(cmd)
    if rc != 0:
        return f"(exit {rc}) {out.strip()}"
    return out.strip()


def _handshake_age(wg_output: str) -> str:
    """`wg show wg0 latest-handshakes` prints `<peer-pub> <unix-ts>`.

    Returns a human age or "never" if 0.
    """
    import time

    matches = _HANDSHAKE_RE.findall(wg_output)
    if not matches:
        return wg_output or "no peer"
    ts = int(matches[0])
    if ts == 0:
        return "never"
    age = int(time.time() - ts)
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m {age % 60}s ago"
    return f"{age // 3600}h {age % 3600 // 60}m ago"


async def collect(cfg: Config) -> dict:
    vps1: HostStatus = {"label": "VPS1 (entry)", "ok": True, "items": []}
    vps2: HostStatus = {"label": "VPS2 (exit)", "ok": True, "items": []}

    xray_active = await _local(["systemctl", "is-active", "xray"])
    vps1["items"].append({"name": "xray", "value": xray_active})
    if xray_active != "active":
        vps1["ok"] = False

    wg_local = await _local(["wg", "show", "wg0", "latest-handshakes"])
    vps1["items"].append({"name": "wg handshake", "value": _handshake_age(wg_local)})

    fwmark = await _local(["sh", "-c", "ip rule show fwmark 0xff || true"])
    vps1["items"].append({"name": "fwmark policy", "value": fwmark or "(missing)"})
    if not fwmark:
        vps1["ok"] = False

    if cfg.hosts.vps2_ip:
        wg_state = await _ssh(cfg, "systemctl is-active wg-quick@wg0")
        vps2["items"].append({"name": "wg-quick@wg0", "value": wg_state})
        if wg_state != "active":
            vps2["ok"] = False
        wg_remote = await _ssh(cfg, "wg show wg0 latest-handshakes")
        vps2["items"].append({"name": "wg handshake", "value": _handshake_age(wg_remote)})
    else:
        vps2["items"].append({"name": "config", "value": "VPS2 not configured"})
        vps2["ok"] = False

    return {"vps1": vps1, "vps2": vps2}
