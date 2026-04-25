# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**chain-proxy** — Ansible-managed two-hop VPN chain: VLESS+Reality on the censored leg (client↔VPS1), kernel WireGuard on the inter-VPS leg (VPS1↔VPS2).

```
Client ──VLESS+Reality(TCP/443)──▶ VPS1 (home, entry, Xray)
                                        │
                                        ├── geosite:ru / geoip:ru → freedom (RU exit via VPS1)
                                        ├── geoip:private          → block
                                        └── default → freedom + sockopt.mark=0xff
                                                          │
                                                  ip rule fwmark → wg0
                                                          │
                                                  WireGuard UDP/51820
                                                          │
                                                          ▼
                                                  VPS2 (foreign, exit) wg0
                                                          │
                                                  iptables MASQUERADE → Internet
```

VPS1 (the home server, placed inside RU) terminates the client's Reality session, sends Russian destinations out locally (so Yandex/VK/etc. see a local RU IP), and forwards the rest to VPS2 over a kernel WireGuard tunnel. **VPS2 no longer runs Xray** — it is a thin WG NAT gateway. Language: Ansible + Jinja2 templates + bash. No application code.

## Common commands

All commands run from repo root. `Makefile` auto-loads `.env` and exports its variables (`IP_VPS1`, `IP_VPS2`, the `ENTRY_*` / `LINK_*` key block, and `WG_VPS1_*` / `WG_VPS2_*`).

```bash
make help                   # list all targets
make install                # install Ansible via pipx (one-time)
make gen-keys               # generate UUIDs + x25519 + WG keypairs into .env
make ping                   # ansible ping both hosts (SSH sanity check)
make syntax                 # ansible-playbook --syntax-check
make check                  # dry run (--check --diff)
make deploy                 # apply playbook to both VPS
make deploy-entry           # apply to VPS1 only (--limit entry)
make deploy-exit            # apply to VPS2 only (--limit exit)
make status / logs          # xray (VPS1) + wg-quick@wg0 (both)
make restart / reload / reset  # xray on VPS1 + wg-quick on both
make xray-test              # xray -test -config on VPS1
make wg-show                # `wg show` on both — peer + last handshake
make wg-restart             # restart wg-quick@wg0 on both
make tail-entry / tail-exit # live journalctl per host (xray on entry, wg on exit)
```

Run a single role/task: `ansible-playbook -i ansible/inventory.yml ansible/playbooks/site.yml --tags <tag>` (tags are defined inside each role's `tasks/main.yml`). The `$(WITH_KEY)` wrapper in `Makefile` runs everything through `ansible/scripts/with-ssh-key.sh`, which loads `$SSH_KEY` (default `~/.ssh/id_ed25519`) into an agent so the passphrase is asked once.

## Architecture

**Source of truth for secrets is `.env`**, not inventory. `Makefile` exports env vars; `ansible/group_vars/*.yml` pulls them via `lookup('env', ...)`. Never hardcode UUIDs/keys in group_vars or templates — they must read from the environment.

- `ansible/inventory.yml` — two groups (`entry`, `exit`), each with one host. `ansible_host` is read from `IP_VPS1` / `IP_VPS2`.
- `ansible/playbooks/site.yml` — three plays: baseline on `all` (`common` + `wireguard` roles), `xray` + `xray_entry` on `entry`, then a localhost play that prints the `vless://` connection URI assembled from `hostvars`. **`exit` no longer runs Xray.**
- `ansible/group_vars/all.yml` — shared knobs: `reality_dest_host` (SNI being impersonated), `xray_*` paths, firewall ports, geodata cron, and the inter-VPS WG block (`wg_subnet`, `wg_listen_port`, `wg_fwmark`, `wg_route_table`, …).
- `ansible/group_vars/entry.yml` / `exit.yml` — load the matching `ENTRY_*` and `WG_VPS{1,2}_*` secrets from env. The legacy `LINK_*` Reality keys are still produced by `gen-keys.sh` but are no longer consumed (kept for git-revert rollback to the all-Reality chain).
- `ansible/roles/`:
  - `common` — OS updates, UFW/iptables firewall (TCP + UDP via `firewall_allowed_{tcp,udp}_ports`), chrony (Reality requires accurate clocks — any skew >30s breaks it), BBR + buffer/MTU sysctl tuning.
  - `xray` — install Xray via XTLS `install-release.sh`, download geoip/geosite assets, systemd unit, weekly geodata refresh cron. Applied **only on `entry`** now. Xray logs go to **stdout/stderr → journald** (no log files). Use `journalctl -u xray` — there is intentionally no `/var/log/xray/*.log`.
  - `xray_entry` — renders VPS1 `config.json`: inbound VLESS+Reality on 443, router rules (geosite:ru/geoip:ru → `direct`, geoip:private → `block`, default → `chain-proxy`), outbound `chain-proxy` is a `freedom` proto with `streamSettings.sockopt.mark = wg_fwmark` so the kernel routes those sockets via wg0.
  - `wireguard` — installs `wireguard`/`wireguard-tools`, renders `/etc/wireguard/wg0.conf` (template branches on `inventory_hostname in groups['entry']`), opens UDP/`wg_listen_port` in UFW, enables `wg-quick@wg0`. On VPS1 the PostUp installs `ip rule add fwmark <wg_fwmark> lookup <wg_route_table>` and `default dev wg0` in that table; on VPS2 PostUp adds FORWARD + MASQUERADE so traffic egresses the public iface.
  - `xray_exit` — **legacy, no longer in any play**. Kept on disk so `git revert` of the WG migration restores the old all-Reality chain.
- `ansible/scripts/gen-keys.sh` — generates UUIDs (uuidgen/python), short IDs (openssl), two x25519 keypairs (via local `xray` binary, or fallback to `docker`/`podman` with `ghcr.io/xtls/xray-core`), and two WireGuard keypairs (`wg genkey | wg pubkey` or fallback container). Writes a block between `# === chain-proxy keys ...` markers in `.env`, replacing any previous block. Rerunning invalidates both the client VLESS link AND the WG handshake.

**Two key sets**: `ENTRY_*` (Reality x25519) secures client↔VPS1; `WG_VPS1_*` / `WG_VPS2_*` (WireGuard Curve25519) secure VPS1↔VPS2. Mixing them silently breaks the handshake (connection just stalls). The legacy `LINK_*` Reality pair is no longer used by the active config.

### Non-obvious invariants in `wireguard/templates/wg0.conf.j2`

These all looked like minor stylistic choices but each is load-bearing — flipping any one of them breaks the chain in a way that takes a long time to debug. **Do not change without rereading the rationale.**

- **VPS1 peer config: `AllowedIPs = 0.0.0.0/0`** (not `10.66.0.2/32`). WireGuard's `AllowedIPs` is *cryptokey routing*: the kernel WG module silently drops outbound packets whose dst doesn't match any peer's `AllowedIPs`, and drops inbound packets whose decrypted src doesn't match. Xray sends to arbitrary internet IPs through the tunnel, and reply src is also arbitrary. Restricting to `/32` makes WG drop everything except `ping 10.66.0.2`.
- **VPS1 interface config: `Table = off`**. With `AllowedIPs = 0.0.0.0/0`, `wg-quick` would otherwise auto-install a default route via wg0 (using its built-in fwmark trick) — which clobbers the host's main route and kills SSH. `Table = off` disables all wg-quick route management; our PostUp manually populates table 100.
- **VPS2 peer config: `AllowedIPs = 10.66.0.1/32`** (not `0.0.0.0/0`). VPS2 only ever talks to VPS1 over the tunnel; tightening this is a small defense.
- **VPS2 PostUp uses `iptables -I FORWARD 1` (insert at top), not `-A FORWARD` (append)**. When Docker is installed on VPS2 — which is common, since `make gen-keys` may pull docker for x25519 fallback — Docker prepends `DOCKER-USER` and `DOCKER-FORWARD` chains and silently drops non-Docker forwarded traffic. Appended rules never match. Insert-at-top guarantees our ACCEPT fires first regardless of Docker.
- **`ip route get <some-public-ip> mark 0xff` on VPS1** must show `dev wg0 src 10.66.0.1`. If it shows the main interface, fwmark policy routing is broken — usually the rule got removed or the table is empty. `make wg-restart` reapplies PostUp.

## Editing rules specific to this repo

- If you change `.tsp`/code in some other project's instructions — ignore, this repo has neither TypeSpec nor a frontend. The global `~/CLAUDE.md` describes a different project (RuFlo); do not apply its build/test commands here.
- Do not edit `group_vars/entry.yml` or `group_vars/exit.yml` to put literal secrets — they must stay as `lookup('env', ...)` so the `.env` flow works.
- Do not commit `.env` (it is in `.gitignore`). Only `.env.example` is tracked.
- After editing any `templates/*.j2` or role tasks, validate with `make syntax && make check` before `make deploy`.
- `make deploy` is idempotent — safe to rerun. Prefer rerunning over manual ssh fixes on the VPS; anything done by hand gets overwritten next deploy.
- When Reality stops working after a change, first suspect: clock skew, a changed `reality_dest_host` that no longer serves TLS 1.3, or a stale key block in `.env` (regenerate with `make gen-keys` → `make deploy` → new VLESS link to client).
- When non-RU traffic egresses via VPS1 instead of VPS2 (wrong public IP), the WG fwmark policy route is missing. Check on VPS1: `ip rule | grep fwmark` (must show `fwmark 0xff lookup 100`), `ip route show table 100` (must show `default dev wg0`), `wg show` (handshake age must be < a few minutes). `make wg-restart` reinstalls the PostUp rules.

## Debugging the chain end-to-end

Symptom: client connects via VLESS-link but **all internet stops working**. Walk the chain in order, do not skip steps — each one rules out a layer:

1. **Is Xray actually running on VPS1?** `ssh root@$IP_VPS1 'systemctl is-active xray && journalctl -u xray -n 30 --no-pager'`. If `failed`, the rest doesn't matter — fix Xray first. Common cause: misrendered `config.json` after a template change (run `make xray-test`). Logs go to journald, not files.
2. **Is the WG tunnel up?** `make wg-show`. Both ends must show `latest handshake: <Ns ago>` with N < ~3 min. If never, suspect UDP/51820 blocked (hoster firewall outside UFW), wrong peer pubkey, or clock skew.
3. **Does VPS1 actually push data into the tunnel?** From VPS1: `curl --interface wg0 -s --max-time 10 https://api.ipify.org`. Must return VPS2's public IP. If this works but the client still has no internet, the bug is upstream of wg0 (Xray's `sockopt.mark` not being applied, fwmark rule missing, etc.) — check `ip route get 8.8.8.8 mark 0xff` returns `dev wg0`.
4. **Are forwarded packets surviving on VPS2?** `ssh root@$IP_VPS2 'iptables -nvL FORWARD --line-numbers | head -5; iptables -t nat -nvL POSTROUTING | grep 10.66'`. The two `wg0` ACCEPT rules must be at positions 1–2 (above any DOCKER chain) and have non-zero `pkts` while the client is generating traffic. The MASQUERADE rule for `10.66.0.0/30` must also have non-zero `pkts`. If counters stay 0 while client tries to load a site → packets never reach FORWARD on VPS2 (most likely Xray on VPS1 isn't sending — go back to step 1).
5. **`tcpdump -ni wg0` on VPS1 with the client actively loading a site** is the fastest single check that cuts through: if it shows IP packets `10.66.0.1.* > <public-ip>.443: ...`, the entire mark→route→tunnel path is working. If empty, Xray isn't pushing traffic.

A red herring worth memorising: `ping 10.66.0.2` from VPS1 over the tunnel **does not work** with the current config (ICMP to the peer's WG addr is dropped) — that is normal and not evidence of a broken tunnel. Use `curl --interface wg0` instead for liveness checks.
