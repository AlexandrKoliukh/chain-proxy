"""Subprocess runner for ansible / shell commands.

The container runs with --pid host --privileged. Real system mutations must
happen in the host's namespaces, so we wrap commands with `nsenter -t 1 -a`.
Set CHAIN_PROXY_NSENTER=0 (or run on a non-Linux dev machine) to skip nsenter
and run commands directly — useful for unit-testing the UI on a laptop.
"""
from __future__ import annotations

import asyncio
import os
import shlex
from typing import AsyncIterator, Sequence

from .paths import KNOWN_HOSTS, ROOT


def _use_nsenter() -> bool:
    return os.environ.get("CHAIN_PROXY_NSENTER", "1") != "0"


def wrap(cmd: Sequence[str]) -> list[str]:
    if _use_nsenter():
        return ["nsenter", "-t", "1", "-a", "--", *cmd]
    return list(cmd)


def base_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["CHAIN_PROXY_KNOWN_HOSTS"] = str(KNOWN_HOSTS)
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["ANSIBLE_FORCE_COLOR"] = "True"
    env["ANSIBLE_STDOUT_CALLBACK"] = "default"
    env["ANSIBLE_CONFIG"] = str(ROOT / "ansible" / "ansible.cfg")
    if extra:
        env.update(extra)
    return env


async def run_capture(cmd: Sequence[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run a command, return (returncode, combined-stdout-stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *wrap(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env if env is not None else base_env(),
        cwd=str(ROOT),
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


async def stream_lines(cmd: Sequence[str], env: dict[str, str] | None = None) -> AsyncIterator[str]:
    """Run a command, yield stdout/stderr lines as they arrive."""
    yield f"$ {shlex.join(wrap(cmd))}\n"
    proc = await asyncio.create_subprocess_exec(
        *wrap(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env if env is not None else base_env(),
        cwd=str(ROOT),
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield line.decode("utf-8", errors="replace")
    rc = await proc.wait()
    yield f"\n[exit {rc}]\n"
