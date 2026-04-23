#!/usr/bin/env bash
# Ensures the requested SSH key is loaded in an ssh-agent, then execs "$@".
# Effect: `make deploy` prompts for the key passphrase exactly once, then
# ansible, scp and anything else ssh-based runs silently for the rest of
# the command.
#
# Override the key with `SSH_KEY=~/.ssh/other_key make deploy`.
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"

if [ ! -f "$SSH_KEY" ]; then
  echo "ERROR: SSH key not found at $SSH_KEY" >&2
  echo "       Create one with:  ssh-keygen -t ed25519" >&2
  echo "       Or override:      SSH_KEY=~/.ssh/<other_key> make <target>" >&2
  exit 1
fi

# Start our own ssh-agent if none is available. The trap kills it on exit
# so we don't leave orphaned agents lying around.
_started_agent=0
if [ -z "${SSH_AUTH_SOCK:-}" ] || ! ssh-add -l >/dev/null 2>&1; then
  if [ -z "${SSH_AUTH_SOCK:-}" ]; then
    eval "$(ssh-agent -s)" >/dev/null
    _started_agent=1
    # shellcheck disable=SC2064
    trap "ssh-agent -k >/dev/null 2>&1 || true" EXIT
  fi
fi

# Load the key only if it's not already in the agent (fingerprint match).
key_fp="$(ssh-keygen -lf "$SSH_KEY" 2>/dev/null | awk '{print $2}')"
if [ -n "$key_fp" ] && ssh-add -l 2>/dev/null | grep -qF "$key_fp"; then
  :  # already loaded
else
  echo "🔑  Loading SSH key: $SSH_KEY" >&2
  # On macOS, also save passphrase to Keychain so future runs don't prompt.
  if [ "$(uname -s)" = "Darwin" ]; then
    ssh-add --apple-use-keychain "$SSH_KEY"
  else
    ssh-add "$SSH_KEY"
  fi
fi

exec "$@"
