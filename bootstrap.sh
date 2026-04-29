#!/usr/bin/env bash
# chain-proxy bootstrap — run on VPS1 as root.
#
# Один шаг:
#   curl -fsSL https://raw.githubusercontent.com/<user>/chain-proxy/main/bootstrap.sh | bash
#
# Что делает:
#   1. Проверяет Debian/Ubuntu и root.
#   2. apt install: docker.io ansible-core sshpass openssl curl jq qrencode git
#   3. Клонит/обновляет репо в /opt/chain-proxy.
#   4. Готовит /opt/chain-proxy/data (700) и .env-keys.
#   5. docker compose up -d --build.
#   6. Печатает URL UI и initial-password.
set -euo pipefail

REPO_URL="${CHAIN_PROXY_REPO:-https://github.com/AlexandrKoliukh/chain-proxy.git}"
REPO_BRANCH="${CHAIN_PROXY_BRANCH:-main}"
INSTALL_DIR="${CHAIN_PROXY_DIR:-/opt/chain-proxy}"

log()  { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[bootstrap]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[bootstrap] %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "запустите как root (sudo bash bootstrap.sh)"

if [ -f /etc/os-release ]; then
  . /etc/os-release
  case "${ID:-}" in
    debian|ubuntu) : ;;
    *) warn "ID=$ID — скрипт тестировался на Debian/Ubuntu, продолжаю на свой страх и риск" ;;
  esac
else
  warn "/etc/os-release не найден — пропускаю проверку дистрибутива"
fi

log "apt update + установка зависимостей"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates curl git jq openssl qrencode sshpass \
  docker.io docker-compose-v2 \
  ansible-core python3 python3-yaml \
  python3-passlib python3-bcrypt python3-docker >/dev/null

systemctl enable --now docker >/dev/null

log "установка Ansible-коллекций (community.general, ansible.posix, community.docker)"
ansible-galaxy collection install community.general ansible.posix community.docker --upgrade -p /usr/share/ansible/collections

log "git clone $REPO_URL → $INSTALL_DIR (branch $REPO_BRANCH)"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" fetch --quiet origin "$REPO_BRANCH"
  git -C "$INSTALL_DIR" checkout --quiet "$REPO_BRANCH"
  git -C "$INSTALL_DIR" reset --hard --quiet "origin/$REPO_BRANCH"
else
  git clone --quiet --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

log "подготовка $INSTALL_DIR/data"
install -d -m 0700 "$INSTALL_DIR/data"
install -d -m 0700 "$INSTALL_DIR/data/tls"
[ -f "$INSTALL_DIR/data/known_hosts" ] || install -m 0600 /dev/null "$INSTALL_DIR/data/known_hosts"

cd "$INSTALL_DIR"

log "docker compose up -d --build (это займёт пару минут на первый раз)"
docker compose up -d --build

# Determine the IP we'll print in the URL — best-effort.
PUBLIC_IP=$(curl -fsS --max-time 3 https://api.ipify.org 2>/dev/null \
  || hostname -I | awk '{print $1}' \
  || echo 'YOUR_VPS1_IP')

# initial-password.txt is created by the UI on first start. Wait briefly,
# then print it (or instruct the user where to find it).
PASS_FILE="$INSTALL_DIR/data/initial-password.txt"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -f "$PASS_FILE" ] && break
  sleep 1
done

cat <<EOF

═══════════════════════════════════════════════════════════════
✓ chain-proxy UI поднят.

  URL:   https://${PUBLIC_IP}:8443
  Login: admin
EOF

if [ -f "$PASS_FILE" ]; then
  printf '  Pass:  %s\n' "$(cat "$PASS_FILE")"
  printf '         (пароль также лежит в %s; смените в UI и удалите файл)\n' "$PASS_FILE"
else
  printf '  Pass:  не успел сгенерироваться. Подождите 10 сек и:\n'
  printf '         cat %s\n' "$PASS_FILE"
fi

cat <<EOF

  Логи:  docker compose logs -f ui
  Стоп:  cd $INSTALL_DIR && docker compose down
  Репо:  $INSTALL_DIR

  Браузер пожалуется на self-signed cert — это ожидаемо, примите.
═══════════════════════════════════════════════════════════════
EOF
