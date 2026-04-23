ANSIBLE_DIR  := ansible
INVENTORY    := $(ANSIBLE_DIR)/inventory.yml
PLAYBOOK     := $(ANSIBLE_DIR)/playbooks/site.yml

# Путь к SSH-ключу. Переопределить: SSH_KEY=~/.ssh/other make deploy
SSH_KEY      ?= $(HOME)/.ssh/id_ed25519

# Обёртка: прогоняет команду через ssh-agent, один раз спрашивая пароль от
# ключа. На macOS пароль запоминается в Keychain — в следующий раз не спросит.
WITH_KEY     := SSH_KEY=$(SSH_KEY) bash $(ANSIBLE_DIR)/scripts/with-ssh-key.sh

# Подхватываем .env, если он есть. Все переменные автоматически экспортируются
# в окружение дочерних процессов (ansible читает их через lookup('env', ...)).
-include .env
export IP_VPS1 IP_VPS2
export ENTRY_CLIENT_UUID ENTRY_FRIENDS_UUID ENTRY_PRIVATE_KEY ENTRY_PUBLIC_KEY ENTRY_SHORT_ID
export LINK_UUID LINK_PUBLIC_KEY LINK_PRIVATE_KEY LINK_SHORT_ID
export ANSIBLE_CONFIG := $(ANSIBLE_DIR)/ansible.cfg

.DEFAULT_GOAL := help

.PHONY: help install gen-keys ping syntax lint check deploy deploy-entry deploy-exit \
        restart reload reset status logs xray-test tail-entry tail-exit facts clean

## ── Help ──────────────────────────────────────────────────────────
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nchain-proxy — VLESS+Reality two-hop (home entry → foreign exit)\n\nUsage:\n  make <target>\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ''
	@echo 'First-time setup:'
	@echo '  1. make install              # install ansible (one time)'
	@echo '  2. cp .env.example .env      # затем впишите IP_VPS1 и IP_VPS2'
	@echo '  3. make gen-keys             # генерирует и дозаписывает ключи в .env'
	@echo '  4. make ping                 # verify SSH access'
	@echo '  5. make syntax && make check # validate'
	@echo '  6. make deploy               # run playbook'
	@echo ''

## ── Prerequisites ─────────────────────────────────────────────────
install:  ## Install Ansible locally (uses pipx)
	@command -v pipx >/dev/null 2>&1 || { echo "pipx not found. Install: brew install pipx OR python3 -m pip install --user pipx"; exit 1; }
	pipx install --include-deps ansible
	ansible --version

gen-keys:  ## Generate UUIDs, x25519 keypairs and shortIds (uses xray or docker)
	@bash $(ANSIBLE_DIR)/scripts/gen-keys.sh

## ── Preflight ─────────────────────────────────────────────────────
ping:  ## ansible -m ping all hosts (verify SSH)
	$(WITH_KEY) ansible -i $(INVENTORY) all -m ping

syntax:  ## Validate playbook syntax
	ansible-playbook -i $(INVENTORY) $(PLAYBOOK) --syntax-check

check:  ## Dry-run (--check --diff)
	$(WITH_KEY) ansible-playbook -i $(INVENTORY) $(PLAYBOOK) --check --diff

lint:  ## Run ansible-lint if installed
	@command -v ansible-lint >/dev/null 2>&1 && ansible-lint $(PLAYBOOK) || echo "ansible-lint not installed (pipx install ansible-lint)"

## ── Deployment ────────────────────────────────────────────────────
deploy:  ## Deploy to both VPS
	$(WITH_KEY) ansible-playbook -i $(INVENTORY) $(PLAYBOOK)

deploy-entry:  ## Deploy only VPS1 (entry, home)
	$(WITH_KEY) ansible-playbook -i $(INVENTORY) $(PLAYBOOK) --limit entry

deploy-exit:  ## Deploy only VPS2 (exit, foreign)
	$(WITH_KEY) ansible-playbook -i $(INVENTORY) $(PLAYBOOK) --limit exit

## ── Operations ────────────────────────────────────────────────────
restart:  ## systemctl restart xray on both
	$(WITH_KEY) ansible -i $(INVENTORY) all -b -m systemd -a 'name=xray state=restarted daemon_reload=yes'

reload:  ## systemctl reload xray on both
	$(WITH_KEY) ansible -i $(INVENTORY) all -b -m systemd -a 'name=xray state=reloaded'

reset:  ## reset-failed + start xray (unblock systemd rate-limit after crashes)
	$(WITH_KEY) ansible -i $(INVENTORY) all -b -a 'bash -lc "systemctl reset-failed xray && systemctl start xray"'

status:  ## systemctl status xray on both
	$(WITH_KEY) ansible -i $(INVENTORY) all -b -a 'systemctl --no-pager status xray'

logs:  ## Last 50 journal lines per host
	$(WITH_KEY) ansible -i $(INVENTORY) all -b -a 'journalctl -u xray -n 50 --no-pager'

xray-test:  ## xray -test -config on both
	$(WITH_KEY) ansible -i $(INVENTORY) all -b -a '/usr/local/bin/xray -test -config /usr/local/etc/xray/config.json'

tail-entry:  ## Tail xray logs on VPS1
	$(WITH_KEY) ansible -i $(INVENTORY) entry -b -a 'journalctl -u xray -f --no-pager' || true

tail-exit:  ## Tail xray logs on VPS2
	$(WITH_KEY) ansible -i $(INVENTORY) exit -b -a 'journalctl -u xray -f --no-pager' || true

facts:  ## Gather ansible facts (diagnostics)
	$(WITH_KEY) ansible -i $(INVENTORY) all -m setup

clean:  ## Remove cached facts
	rm -rf $(ANSIBLE_DIR)/.facts
