"""Ansible deploy orchestration with single-job lock and SSE streaming."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Literal, Optional

from .config import Config
from .paths import INVENTORY, PLAYBOOK
from .runner import base_env, stream_lines

Limit = Literal["all", "entry", "exit"]


class JobLog:
    """Ring buffer of log lines + an asyncio.Event signalling new lines."""

    def __init__(self, max_lines: int = 5000) -> None:
        self.lines: deque[str] = deque(maxlen=max_lines)
        self._waiters: list[asyncio.Event] = []
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.kind: str = ""

    def append(self, line: str) -> None:
        self.lines.append(line)
        for ev in self._waiters:
            ev.set()

    def finish(self, exit_code: int) -> None:
        self.finished_at = time.time()
        self.exit_code = exit_code
        for ev in self._waiters:
            ev.set()

    def is_running(self) -> bool:
        return self.finished_at is None

    async def follow(self):
        """Async generator: yields existing lines, then new ones until finish."""
        idx = 0
        while True:
            while idx < len(self.lines):
                yield self.lines[idx]
                idx += 1
            if not self.is_running():
                return
            ev = asyncio.Event()
            self._waiters.append(ev)
            try:
                await ev.wait()
            finally:
                self._waiters.remove(ev)


class JobManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.current: Optional[JobLog] = None
        self.last: Optional[JobLog] = None

    def status(self) -> dict:
        job = self.current or self.last
        if job is None:
            return {"state": "idle"}
        return {
            "state": "running" if job.is_running() else "done",
            "kind": job.kind,
            "exit_code": job.exit_code,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "lines": len(job.lines),
        }

    async def run(self, kind: str, cmd: list[str], env: dict[str, str]) -> JobLog:
        if self._lock.locked():
            raise RuntimeError("another job is already running")
        async with self._lock:
            log = JobLog()
            log.kind = kind
            self.current = log
            try:
                exit_code = 0
                async for line in stream_lines(cmd, env=env):
                    log.append(line)
                    if line.startswith("[exit "):
                        try:
                            exit_code = int(line.strip()[len("[exit ") : -1])
                        except ValueError:
                            pass
                log.finish(exit_code)
            except Exception as exc:
                log.append(f"\n[runner error] {exc}\n")
                log.finish(-1)
            finally:
                self.last = log
                self.current = None
            return log


jobs = JobManager()


def build_deploy_cmd(limit: Limit) -> list[str]:
    cmd = ["ansible-playbook", "-i", str(INVENTORY), str(PLAYBOOK)]
    if limit != "all":
        cmd += ["--limit", limit]
    return cmd


def build_env(cfg: Config, *, local_entry: bool) -> dict[str, str]:
    env = base_env(cfg.to_env())
    if local_entry:
        env["CHAIN_PROXY_LOCAL_ENTRY"] = "1"
    return env


async def start_deploy(cfg: Config, limit: Limit, local_entry: bool) -> JobLog:
    cmd = build_deploy_cmd(limit)
    env = build_env(cfg, local_entry=local_entry)
    return await jobs.run(f"deploy ({limit})", cmd, env)
