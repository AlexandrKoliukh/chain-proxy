# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**chain-proxy** — Ansible-managed two-hop VLESS+Reality VPN chain across two VPS:

```
Client ──Reality──▶ VPS1 (home, entry) ──Reality──▶ VPS2 (foreign, exit) ──▶ Internet
                          │
                          └── geoip:ru / geosite:ru → direct egress from VPS1
                              geoip:private          → block
```

VPS1 (the home server, placed inside RU) routes Russian destinations out locally (so Yandex/VK/etc. see a local RU IP) and tunnels everything else to VPS2 (the foreign server) via an inner VLESS+Reality hop. Language: Ansible + Jinja2 templates + bash. No application code.

## Common commands

All commands run from repo root. `Makefile` auto-loads `.env` and exports its variables (`IP_VPS1`, `IP_VPS2`, and the `ENTRY_*` / `LINK_*` key block).

```bash
make help                   # list all targets
make install                # install Ansible via pipx (one-time)
make gen-keys               # generate UUIDs + x25519 pairs + short IDs into .env
make ping                   # ansible ping both hosts (SSH sanity check)
make syntax                 # ansible-playbook --syntax-check
make check                  # dry run (--check --diff)
make deploy                 # apply playbook to both VPS
make deploy-entry           # apply to VPS1 only (--limit entry)
make deploy-exit            # apply to VPS2 only (--limit exit)
make status / logs          # systemctl status / last 50 journal lines
make restart / reload / reset  # xray service control
make xray-test              # xray -test -config on both hosts
make tail-entry / tail-exit # live journalctl per host
```

Run a single role/task: `ansible-playbook -i ansible/inventory.yml ansible/playbooks/site.yml --tags <tag>` (tags are defined inside each role's `tasks/main.yml`). The `$(WITH_KEY)` wrapper in `Makefile` runs everything through `ansible/scripts/with-ssh-key.sh`, which loads `$SSH_KEY` (default `~/.ssh/id_ed25519`) into an agent so the passphrase is asked once.

## Architecture

**Source of truth for secrets is `.env`**, not inventory. `Makefile` exports env vars; `ansible/group_vars/*.yml` pulls them via `lookup('env', ...)`. Never hardcode UUIDs/keys in group_vars or templates — they must read from the environment.

- `ansible/inventory.yml` — two groups (`entry`, `exit`), each with one host. `ansible_host` is read from `IP_VPS1` / `IP_VPS2`.
- `ansible/playbooks/site.yml` — three plays: baseline on `all` (`common` + `xray` roles), `xray_entry` on `entry`, `xray_exit` on `exit`, then a localhost play that prints the `vless://` connection URI assembled from `hostvars`.
- `ansible/group_vars/all.yml` — shared knobs: `reality_dest_host` (SNI being impersonated), `xray_*` paths, firewall ports, geodata cron.
- `ansible/group_vars/entry.yml` / `exit.yml` — load the matching `ENTRY_*` / `LINK_*` secrets from env. VPS1 needs both the client-facing `ENTRY_*` keys AND the `LINK_*` public key to reach VPS2; VPS2 needs only `LINK_*` private/public.
- `ansible/roles/`:
  - `common` — OS updates, UFW/iptables firewall, chrony (Reality requires accurate clocks — any skew >30s breaks it), BBR.
  - `xray` — install Xray via XTLS `install-release.sh`, download geoip/geosite assets, systemd unit, weekly geodata refresh cron.
  - `xray_entry` — renders VPS1 `config.json` from `templates/config.json.j2`: inbound VLESS+Reality on 443, router rules (geosite:ru/geoip:ru → `direct`, geoip:private → `block`, default → outbound to VPS2), outbound VLESS+Reality to `IP_VPS2`.
  - `xray_exit` — renders VPS2 `config.json`: inbound VLESS+Reality listening for the `LINK_*` identity from VPS1, single freedom outbound.
- `ansible/scripts/gen-keys.sh` — generates UUIDs (uuidgen/python), short IDs (openssl), and two x25519 keypairs (via local `xray` binary, or fallback to `docker`/`podman` running `ghcr.io/xtls/xray-core`). Writes a block between `# === chain-proxy keys ...` markers in `.env`, replacing any previous block. Rerunning invalidates the client VLESS link.

**Two key pairs, not one**: `ENTRY_*` secures client↔VPS1; `LINK_*` secures VPS1↔VPS2. Mixing them breaks Reality handshake silently (connection just stalls).

## Editing rules specific to this repo

- If you change `.tsp`/code in some other project's instructions — ignore, this repo has neither TypeSpec nor a frontend. The global `~/CLAUDE.md` describes a different project (RuFlo); do not apply its build/test commands here.
- Do not edit `group_vars/entry.yml` or `group_vars/exit.yml` to put literal secrets — they must stay as `lookup('env', ...)` so the `.env` flow works.
- Do not commit `.env` (it is in `.gitignore`). Only `.env.example` is tracked.
- After editing any `templates/*.j2` or role tasks, validate with `make syntax && make check` before `make deploy`.
- `make deploy` is idempotent — safe to rerun. Prefer rerunning over manual ssh fixes on the VPS; anything done by hand gets overwritten next deploy.
- When Reality stops working after a change, first suspect: clock skew, a changed `reality_dest_host` that no longer serves TLS 1.3, or a stale key block in `.env` (regenerate with `make gen-keys` → `make deploy` → new VLESS link to client).
