import os
from pathlib import Path

ROOT = Path(os.environ.get("CHAIN_PROXY_ROOT", "/opt/chain-proxy"))
DATA = Path(os.environ.get("CHAIN_PROXY_DATA", str(ROOT / "data")))

CONFIG_FILE = DATA / "config.yml"
AUTH_FILE = DATA / "auth.json"
INITIAL_PASSWORD_FILE = DATA / "initial-password.txt"
TLS_DIR = DATA / "tls"
TLS_CERT = TLS_DIR / "cert.pem"
TLS_KEY = TLS_DIR / "key.pem"
KNOWN_HOSTS = DATA / "known_hosts"
ENV_KEYS_FILE = DATA / ".env-keys"

ANSIBLE_DIR = ROOT / "ansible"
INVENTORY = ANSIBLE_DIR / "inventory.yml"
PLAYBOOK = ANSIBLE_DIR / "playbooks" / "site.yml"
GEN_KEYS_SCRIPT = ANSIBLE_DIR / "scripts" / "gen-keys.sh"

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"


def ensure_data_dirs() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    if not KNOWN_HOSTS.exists():
        KNOWN_HOSTS.touch(mode=0o600)
