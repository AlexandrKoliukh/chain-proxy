# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**chain-proxy** — Ansible-managed two-hop VPN chain: VLESS+Reality on the censored leg (client↔VPS1), WireGuard on the inter-VPS leg (VPS1↔VPS2 via wg-easy).

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
                                                  VPS2 wg-easy (Docker) wg0
                                                          │
                                                  iptables MASQUERADE → Internet

Direct WireGuard client ──UDP/51820──▶ VPS2 wg-easy GUI (TCP/51821)
```

VPS1 (the home server, placed inside RU) terminates the client's Reality session, sends Russian destinations out locally (so Yandex/VK/etc. see a local RU IP), and forwards the rest to VPS2 over a WireGuard tunnel. **VPS2 runs wg-easy** (Docker container) — it is the WireGuard server for both the chain tunnel and direct client connections. VPS1 is a pre-configured peer in wg-easy; additional clients can be added via the wg-easy GUI at `http://<VPS2>:51821`. Language: Ansible + Jinja2 templates + bash. No application code.

**wg-easy credentials**: shown in the UI at `/settings → WireGuard Admin GUI`. Generated automatically by «Сгенерировать ключи» button.

**wg-easy password rotation**: either use the wg-easy GUI Settings → Change Password, OR: `ssh root@$IP_VPS2 'rm /etc/wg-easy/wg0.json'` → «Деплой» in UI (reseed from new `WG_EASY_PASSWORD`). The `wg0.json` preseed is only applied on first install (`force: false`).

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
- `ansible/playbooks/site.yml` — four plays: (1) baseline `common` on `all`, (2) `wireguard` + `xray` + `xray_entry` on `entry` (VPS1 only), (3) `wg_easy` on `exit` (VPS2 only), (4) localhost debug output with VLESS URIs and wg-easy GUI URL. **`exit` no longer runs Xray or kernel wg-quick.**
- `ansible/group_vars/all.yml` — shared knobs: `reality_dest_host` (SNI being impersonated), `xray_*` paths, firewall ports, geodata cron, and the inter-VPS WG block (`wg_subnet`, `wg_listen_port`, `wg_fwmark`, `wg_route_table`, …).
- `ansible/group_vars/entry.yml` / `exit.yml` — load the matching `ENTRY_*` and `WG_VPS{1,2}_*` secrets from env. The legacy `LINK_*` Reality keys are still produced by `gen-keys.sh` but are no longer consumed (kept for git-revert rollback to the all-Reality chain).
- `ansible/roles/`:
  - `common` — OS updates, UFW/iptables firewall (TCP + UDP via `firewall_allowed_{tcp,udp}_ports`), chrony (Reality requires accurate clocks — any skew >30s breaks it), BBR + buffer/MTU sysctl tuning.
  - `xray` — install Xray via XTLS `install-release.sh`, download geoip/geosite assets, systemd unit, weekly geodata refresh cron. After XTLS `install-geodata` runs, `geoip.dat` is **overwritten** with the [hydraponique/roscomvpn-geoip](https://github.com/hydraponique/roscomvpn-geoip) release (sha256-verified) — that build merges three independent geo-sources and exposes categories `geoip:direct` (RU + BY + curated Yandex/VK/Mail.Ru/CDNVideo CIDRs), `geoip:whitelist` (~4k CIDRs of RU hosting/cloud/DNS that public geoip sources mislabel as foreign — Yandex Cloud, Selectel, VK Cloud, Yandex DNS, dynamic resolves), and `geoip:private`. `geosite.dat` stays from XTLS. Toggle via `roscomvpn_geoip_enabled`. Applied **only on `entry`** now. Xray logs go to **stdout/stderr → journald** (no log files). Use `journalctl -u xray` — there is intentionally no `/var/log/xray/*.log`.
  - `xray_entry` — renders VPS1 `config.json`: inbound VLESS+Reality on 443, router rules (geosite:category-ru/yandex/vk/mailru + geoip:direct + geoip:whitelist → `direct`, geoip:private → `block`, default → `chain-proxy`), outbound `chain-proxy` is a `freedom` proto with `streamSettings.sockopt.mark = wg_fwmark` so the kernel routes those sockets via wg0.
  - `wireguard` — applied to `entry` only. Installs `wireguard`/`wireguard-tools`, renders `/etc/wireguard/wg0.conf` (VPS1 side: `Table = off` + fwmark PostUp rules, subnet `/24`), opens UDP/`wg_listen_port` in UFW, enables `wg-quick@wg0`. VPS2 no longer uses this role — wg-easy manages its own WG interface.
  - `wg_easy` — **new, applied to `exit` only**. Installs Docker on VPS2, stops+disables kernel `wg-quick@wg0`, deploys `ghcr.io/wg-easy/wg-easy:14` container via `community.docker`. On first install: preseeds `/etc/wg-easy/wg0.json` with server keypair and VPS1 as pre-configured peer. On re-deploy: idempotent — if container exists, does not recreate; only ensures VPS1 peer is present in `wg0.json`. Web GUI at TCP/51821. Container has `NET_ADMIN` capability and `network_mode: host`. Config persists in `/etc/wg-easy/` bind-mounted into container as `/etc/wireguard/`.
  - `xray_exit` — **legacy, no longer in any play**. Kept on disk so `git revert` of the WG migration restores the old all-Reality chain.
- `ansible/scripts/gen-keys.sh` — generates UUIDs (uuidgen/python), short IDs (openssl), two x25519 keypairs (via local `xray` binary, or fallback to `docker`/`podman` with `ghcr.io/xtls/xray-core`), two WireGuard keypairs (`wg genkey | wg pubkey` or fallback container), and a random `WG_EASY_PASSWORD`. Writes a block between `# === chain-proxy keys ...` markers in `.env`, replacing any previous block. Rerunning invalidates the client VLESS link and the WG handshake. The wg-easy password is NOT automatically rotated on VPS2 — see password rotation note above.

**Two key sets**: `ENTRY_*` (Reality x25519) secures client↔VPS1; `WG_VPS1_*` / `WG_VPS2_*` (WireGuard Curve25519) secure VPS1↔VPS2. Mixing them silently breaks the handshake (connection just stalls). The legacy `LINK_*` Reality pair is no longer used by the active config.

### Non-obvious invariants in `wireguard/templates/wg0.conf.j2`

These all looked like minor stylistic choices but each is load-bearing — flipping any one of them breaks the chain in a way that takes a long time to debug. **Do not change without rereading the rationale.**

- **VPS1 peer config: `AllowedIPs = 0.0.0.0/0`** (not `10.66.0.2/32`). WireGuard's `AllowedIPs` is *cryptokey routing*: the kernel WG module silently drops outbound packets whose dst doesn't match any peer's `AllowedIPs`, and drops inbound packets whose decrypted src doesn't match. Xray sends to arbitrary internet IPs through the tunnel, and reply src is also arbitrary. Restricting to `/32` makes WG drop everything except `ping 10.66.0.2`.
- **VPS1 interface config: `Table = off`**. With `AllowedIPs = 0.0.0.0/0`, `wg-quick` would otherwise auto-install a default route via wg0 (using its built-in fwmark trick) — which clobbers the host's main route and kills SSH. `Table = off` disables all wg-quick route management; our PostUp manually populates table 100.
- **VPS2 peer config: `AllowedIPs = 10.66.0.1/32`** (not `0.0.0.0/0`). VPS2 only ever talks to VPS1 over the tunnel; tightening this is a small defense.
- **VPS2 PostUp uses `iptables -I FORWARD 1` (insert at top), not `-A FORWARD` (append)**. When Docker is installed on VPS2 — which is common, since `make gen-keys` may pull docker for x25519 fallback — Docker prepends `DOCKER-USER` and `DOCKER-FORWARD` chains and silently drops non-Docker forwarded traffic. Appended rules never match. Insert-at-top guarantees our ACCEPT fires first regardless of Docker.
- **`ip route get <some-public-ip> mark 0xff` on VPS1** must show `dev wg0 src 10.66.0.1`. If it shows the main interface, fwmark policy routing is broken — usually the rule got removed or the table is empty. `make wg-restart` reapplies PostUp.

## Tests

### Structure

```
tests/
├── conftest.py          # shared fixtures (see below)
├── requirements.txt     # pytest, httpx, pytest-asyncio, pytest-mock, …
├── pytest.ini           # asyncio_mode=auto; markers: unit, api, docker_image
├── unit/                # pure Python tests of ui/* modules (no network, no subprocess)
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_vless.py
│   ├── test_status_parse.py
│   └── test_tls.py
└── api/                 # FastAPI endpoint tests via httpx ASGITransport
    ├── test_healthz.py
    ├── test_auth_flow.py
    ├── test_settings.py
    ├── test_gen_keys.py
    ├── test_deploy.py
    ├── test_status.py
    ├── test_client_link.py
    └── test_docker_image.py  # gate: CHAIN_PROXY_TEST_DOCKER=1
```

Molecule scenarios for each Ansible role live in `ansible/roles/<role>/molecule/default/`.

### Commands

```bash
make test-install   # create .venv-tests and pip install tests/requirements.txt
make test           # pytest tests/unit + tests/api  (fast; no network, no docker)
make test-unit      # only unit tests
make test-api       # only API tests
make test-docker    # docker build smoke test (requires docker)
make test-molecule  # molecule test for all 4 roles  (requires docker + Linux)
make test-all       # test + test-docker + test-molecule
```

All tests run in isolation — each test gets its own `tmp_path` as `CHAIN_PROXY_DATA`; subprocess calls (Ansible, gen-keys.sh) are mocked.

### Isolation contract (always enforce)

- **Never write to `/opt/chain-proxy` or `~/.config` in tests.** `CHAIN_PROXY_DATA` is always a fresh `tmp_path`.
- **Never run real subprocesses** (`ansible-playbook`, `gen-keys.sh`, `systemctl`, `wg`, `ssh`) in unit/api tests. Mock at the `ui.runner.run_capture` / `ui.keys.regenerate` / `ui.status.collect` / `ui.deploy.start_deploy` boundary.
- **Set `CHAIN_PROXY_NSENTER=0`** (already done in `conftest.py`) so no test tries to call `nsenter`.
- **Reload `ui.*` modules** after setting env vars — module-level `Path` constants bake in values at import time. The `ui_modules` fixture in `conftest.py` handles this via `sys.modules.pop` + `importlib.import_module`.

### How to add a new unit test

1. Create (or add to) `tests/unit/test_<module>.py`.
2. Decorate the module with `pytestmark = pytest.mark.unit`.
3. Accept `ui_modules` fixture — access any `ui.*` module via `ui_modules["<module>"]` (e.g. `ui_modules["auth"]`).
4. No `async` needed for pure Python code.

```python
import pytest
pytestmark = pytest.mark.unit

def test_something(ui_modules):
    auth = ui_modules["auth"]
    assert auth.verify("admin", "wrong") is False
```

### How to add a new API test

1. Create (or add to) `tests/api/test_<endpoint>.py`.
2. Use `pytestmark = pytest.mark.api`.
3. Accept the `client` fixture (async httpx client) and `initial_password` (sets up basic-auth for `("admin", "testpass123")`).
4. To mock a subprocess-backed operation, monkeypatch at the module level. Examples:
   - `monkeypatch.setattr(ui_modules["keys"], "regenerate", fake_fn)`
   - `monkeypatch.setattr(ui_modules["status"], "collect", fake_fn)`
   - `monkeypatch.setattr(ui_modules["deploy"], "start_deploy", fake_fn)`

```python
import pytest
pytestmark = pytest.mark.api
BASIC = ("admin", "testpass123")

async def test_my_endpoint(client, initial_password):
    resp = await client.get("/my-route", auth=BASIC)
    assert resp.status_code == 200
```

### How to add a new Molecule test

When you add or change a role task that has a verifiable side-effect (file created, service active, sysctl value, iptables rule), add an assertion in the role's `verify.yml`:

```
ansible/roles/<role>/molecule/default/verify.yml
```

Rules:
- Use `command:` / `shell:` + `failed_when:` for imperative checks (active service, file exists, command exit code).
- Use `slurp:` + `from_json` + `assert:` for checking rendered JSON configs (e.g. `xray_entry` config.json).
- Keep `changed_when: false` on all verify tasks.
- If the new role/task needs vars that come from `.env`, supply dummy values in `converge.yml` `vars:` block — never use real keys.

If you add a **new role**, copy the molecule scaffold from an existing role, adjust the platform count (1 or 2 containers), and add it to:
- `make test-molecule` loop in Makefile
- `matrix.role` list in `.github/workflows/tests.yml`

### CI (GitHub Actions)

`.github/workflows/tests.yml` runs on every push/PR to `main`:

| Job | What it tests | Gate |
|-----|---------------|------|
| `unit-api` | All pytest tests (unit + api) | always |
| `docker-image` | `docker build` + `/healthz` responds + logs show initial password | always |
| `molecule (common)` | Baseline packages, sysctl, chrony, UFW ports | always |
| `molecule (xray)` | xray binary, geoip.dat sha256, cron script | always |
| `molecule (xray_entry)` | `xray -test -config`, JSON routing/fwmark invariants | always |
| `molecule (wireguard)` | WG handshake between two containers, fwmark routing on entry, iptables on exit | always; requires `sudo modprobe wireguard` |

When a molecule job fails, check:
1. Did `converge.yml` error? → usually a missing var or package unavailable in the container.
2. Did `verify.yml` fail an `assert:`? → the role task produced wrong output; fix the task or template.
3. For `wireguard`: if handshake never happens, the kernel WG module may not be loaded — check the "Load wireguard kernel module" step in the GH Actions log.

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
4. **Are forwarded packets surviving on VPS2?** FORWARD/MASQUERADE rules are now managed by the **wg-easy container** (not kernel wg-quick PostUp). Check:
   - `ssh root@$IP_VPS2 'docker ps --filter name=wg-easy'` — container must be Up.
   - `ssh root@$IP_VPS2 'docker exec wg-easy iptables -nvL FORWARD | head -10'` — must have ACCEPT rules for wg0 with non-zero `pkts`.
   - `ssh root@$IP_VPS2 'docker exec wg-easy iptables -t nat -nvL POSTROUTING | head -5'` — must have MASQUERADE rule for `10.66.0.0/24`.
   - `ssh root@$IP_VPS2 'docker logs wg-easy --tail 50'` — wg-easy startup log shows any WireGuard errors.
   If counters stay 0 → packets never reach FORWARD on VPS2 (most likely Xray on VPS1 isn't sending — go back to step 1).
5. **`tcpdump -ni wg0` on VPS1 with the client actively loading a site** is the fastest single check that cuts through: if it shows IP packets `10.66.0.1.* > <public-ip>.443: ...`, the entire mark→route→tunnel path is working. If empty, Xray isn't pushing traffic.

A red herring worth memorising: `ping 10.66.0.2` from VPS1 over the tunnel **does not work** with the current config (ICMP to the peer's WG addr is dropped) — that is normal and not evidence of a broken tunnel. Use `curl --interface wg0` instead for liveness checks.
