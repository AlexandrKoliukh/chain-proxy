"""Persistent UI config — single YAML replacing the .env flow.

The shape mirrors the env-vars consumed by ansible's `lookup('env', ...)` calls
in inventory.yml and group_vars/*.yml. `to_env()` produces the dict that the
deploy/keys subprocesses are launched with.
"""
from __future__ import annotations

import json
import os
import re
import uuid as _uuid_mod
from dataclasses import asdict, dataclass, field, fields
from typing import Any

import yaml

from .paths import CONFIG_FILE, ENV_KEYS_FILE


@dataclass
class Hosts:
    vps1_ip: str = ""
    vps2_ip: str = ""
    vps2_user: str = "root"
    vps2_password: str = ""
    vps2_port: int = 22


@dataclass
class Reality:
    dest_host: str = "www.microsoft.com"
    fingerprint: str = "chrome"


@dataclass
class Keys:
    entry_client_uuid: str = ""
    entry_friends_uuid: str = ""
    entry_private_key: str = ""
    entry_public_key: str = ""
    entry_short_id: str = ""
    link_uuid: str = ""
    link_public_key: str = ""
    link_private_key: str = ""
    link_short_id: str = ""
    wg_vps1_private: str = ""
    wg_vps1_public: str = ""
    wg_vps2_private: str = ""
    wg_vps2_public: str = ""


@dataclass
class ClientEntry:
    name: str   # used as Xray email field
    uuid: str


@dataclass
class Config:
    hosts: Hosts = field(default_factory=Hosts)
    reality: Reality = field(default_factory=Reality)
    keys: Keys = field(default_factory=Keys)
    clients: list = field(default_factory=list)  # list[ClientEntry]

    def to_env(self) -> dict[str, str]:
        env = {
            "IP_VPS1": self.hosts.vps1_ip,
            "IP_VPS2": self.hosts.vps2_ip,
            "VPS2_USER": self.hosts.vps2_user,
            "VPS2_PASSWORD": self.hosts.vps2_password,
            "VPS2_PORT": str(self.hosts.vps2_port),
            # Reality SNI/fingerprint are still group_vars defaults; only export
            # if user changed them so ansible's lookup falls through otherwise.
            "REALITY_DEST_HOST": self.reality.dest_host,
            "REALITY_FINGERPRINT": self.reality.fingerprint,
        }
        env.update(
            {
                "ENTRY_CLIENT_UUID": self.keys.entry_client_uuid,
                "ENTRY_FRIENDS_UUID": self.keys.entry_friends_uuid,
                "ENTRY_PRIVATE_KEY": self.keys.entry_private_key,
                "ENTRY_PUBLIC_KEY": self.keys.entry_public_key,
                "ENTRY_SHORT_ID": self.keys.entry_short_id,
                "LINK_UUID": self.keys.link_uuid,
                "LINK_PUBLIC_KEY": self.keys.link_public_key,
                "LINK_PRIVATE_KEY": self.keys.link_private_key,
                "LINK_SHORT_ID": self.keys.link_short_id,
                "WG_VPS1_PRIVATE": self.keys.wg_vps1_private,
                "WG_VPS1_PUBLIC": self.keys.wg_vps1_public,
                "WG_VPS2_PRIVATE": self.keys.wg_vps2_private,
                "WG_VPS2_PUBLIC": self.keys.wg_vps2_public,
            }
        )
        if self.clients:
            env["ENTRY_CLIENTS_JSON"] = json.dumps(
                [{"email": c.name, "id": c.uuid} for c in self.clients]
            )
        return {k: v for k, v in env.items() if v != ""}


def _from_dict(cls, data: dict[str, Any]):
    field_names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in field_names})


def load() -> Config:
    if not CONFIG_FILE.exists():
        return Config()
    raw = yaml.safe_load(CONFIG_FILE.read_text()) or {}
    clients_raw = raw.get("clients", []) or []
    clients = [
        ClientEntry(name=c["name"], uuid=c["uuid"])
        for c in clients_raw
        if isinstance(c, dict) and c.get("name") and c.get("uuid")
    ]
    cfg = Config(
        hosts=_from_dict(Hosts, raw.get("hosts", {})),
        reality=_from_dict(Reality, raw.get("reality", {})),
        keys=_from_dict(Keys, raw.get("keys", {})),
        clients=clients,
    )
    # One-time migration: promote legacy UUID key fields into the clients list
    if not cfg.clients:
        if cfg.keys.entry_client_uuid:
            cfg.clients.append(ClientEntry(name="admin", uuid=cfg.keys.entry_client_uuid))
        if cfg.keys.entry_friends_uuid:
            cfg.clients.append(ClientEntry(name="friends", uuid=cfg.keys.entry_friends_uuid))
        if cfg.clients:
            save(cfg)
    return cfg


def save(cfg: Config) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".yml.tmp")
    tmp.write_text(yaml.safe_dump(asdict(cfg), sort_keys=False, allow_unicode=True))
    tmp.replace(CONFIG_FILE)
    os.chmod(CONFIG_FILE, 0o600)


_KEY_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")
_BEGIN_MARK = "# === chain-proxy keys"


def parse_env_keys_file() -> dict[str, str]:
    """Read the auto-generated key block written by gen-keys.sh."""
    if not ENV_KEYS_FILE.exists():
        return {}
    out: dict[str, str] = {}
    in_block = False
    for line in ENV_KEYS_FILE.read_text().splitlines():
        if line.startswith(_BEGIN_MARK):
            in_block = True
            continue
        if line.startswith("# === end chain-proxy keys"):
            in_block = False
            continue
        if not in_block:
            continue
        m = _KEY_LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def apply_generated_keys(cfg: Config, raw: dict[str, str]) -> Config:
    mapping = {
        "ENTRY_CLIENT_UUID": "entry_client_uuid",
        "ENTRY_FRIENDS_UUID": "entry_friends_uuid",
        "ENTRY_PRIVATE_KEY": "entry_private_key",
        "ENTRY_PUBLIC_KEY": "entry_public_key",
        "ENTRY_SHORT_ID": "entry_short_id",
        "LINK_UUID": "link_uuid",
        "LINK_PUBLIC_KEY": "link_public_key",
        "LINK_PRIVATE_KEY": "link_private_key",
        "LINK_SHORT_ID": "link_short_id",
        "WG_VPS1_PRIVATE": "wg_vps1_private",
        "WG_VPS1_PUBLIC": "wg_vps1_public",
        "WG_VPS2_PRIVATE": "wg_vps2_private",
        "WG_VPS2_PUBLIC": "wg_vps2_public",
    }
    for env_key, attr in mapping.items():
        if env_key in raw:
            setattr(cfg.keys, attr, raw[env_key])
    # Seed clients list from freshly-generated UUIDs if list is still empty
    if not cfg.clients:
        if cfg.keys.entry_client_uuid:
            cfg.clients.append(ClientEntry(name="admin", uuid=cfg.keys.entry_client_uuid))
        if cfg.keys.entry_friends_uuid:
            cfg.clients.append(ClientEntry(name="friends", uuid=cfg.keys.entry_friends_uuid))
    return cfg


_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def new_client(name: str, cfg: Config) -> Config:
    if not _NAME_RE.match(name):
        raise ValueError(f"Invalid client name: {name!r}")
    if any(c.name == name for c in cfg.clients):
        raise ValueError(f"Client {name!r} already exists")
    cfg.clients.append(ClientEntry(name=name, uuid=str(_uuid_mod.uuid4())))
    return cfg


def remove_client(name: str, cfg: Config) -> Config:
    cfg.clients = [c for c in cfg.clients if c.name != name]
    return cfg
