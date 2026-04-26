"""Wraps ansible/scripts/gen-keys.sh — writes the generated block to
data/.env-keys (off the repo) and parses it back into the YAML config.
"""
from __future__ import annotations

from . import config as cfg_mod
from .paths import ENV_KEYS_FILE, GEN_KEYS_SCRIPT
from .runner import base_env, run_capture


async def regenerate(cfg: cfg_mod.Config) -> tuple[int, str, cfg_mod.Config]:
    env = base_env({"ENV_FILE": str(ENV_KEYS_FILE)})
    rc, out = await run_capture(["bash", str(GEN_KEYS_SCRIPT)], env=env)
    if rc == 0:
        raw = cfg_mod.parse_env_keys_file()
        cfg = cfg_mod.apply_generated_keys(cfg, raw)
        cfg_mod.save(cfg)
    return rc, out, cfg
