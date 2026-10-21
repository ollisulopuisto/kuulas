#!/bin/bash
# Run Codex unattended in one git worktree with OS-level write limits (macOS sandbox-exec).
#
#   scripts/codex-sandboxed.sh /private/tmp/kuulas-codex-c2 "Read .../codex.md and do task C2"
#
# Why: Codex's own workspace-write sandbox protects .git, so it cannot commit; its
# full-access mode has no file limits. This runs Codex in full-access mode INSIDE a macOS
# sandbox that allows writes only to: the worktree, the main repo's .git (a worktree's
# commits go there), the codex reply file, Codex's own state (~/.codex), a private temp
# folder and the uv/npm caches. Everything else is read-only, and the secret folders
# (~/.config, ~/.ssh, ...) cannot even be read. Network stays open (Codex needs its API).
# sandbox-exec is deprecated by Apple but works; test with `--selftest`.
set -euo pipefail

MAIN="${KUULAS_MAIN:-$HOME/Documents/koodi/kuulas}"
if [ "${1:-}" = "--selftest" ]; then SELFTEST=1; shift; else SELFTEST=0; fi
WT="$(cd "${1:?usage: codex-sandboxed.sh <worktree> <prompt>}" && pwd -P)"
PROMPT="${2:-}"
case "$WT" in /private/tmp/kuulas-*) ;; *) echo "worktree must be /private/tmp/kuulas-*" >&2; exit 2;; esac
[ -f "$WT/.git" ] || { echo "$WT is not a git worktree" >&2; exit 2; }
GITDIR="$(cd "$MAIN" && pwd -P)/.git"
TMP="/private/tmp/kuulas-codex-tmp"; mkdir -p "$TMP" "$HOME/.cache/uv" "$HOME/.npm" "$HOME/.codex"
REPLY="$(cd "$MAIN" && pwd -P)/.agents/codex-reply.md"; touch "$REPLY"

PROFILE="$(mktemp "$TMP/profile.XXXXXX")"
cat > "$PROFILE" <<EOF
(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath "$WT")
  (subpath "$GITDIR")
  (literal "$REPLY")
  (subpath "$HOME/.codex")
  (subpath "$HOME/.cache/uv")
  (subpath "$HOME/.npm")
  (subpath "$TMP")
  (subpath "/private/var/folders")
  (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper")
  (regex #"^/dev/ttys[0-9]+$") (subpath "/dev/fd"))
(deny file-read*
  (subpath "$HOME/.config") (subpath "$HOME/.ssh") (subpath "$HOME/.aws")
  (subpath "$HOME/.gnupg") (subpath "$HOME/Library/Keychains")
  (subpath "$HOME/.claude") (subpath "$HOME/.kube") (subpath "$HOME/.docker")
  (subpath "$HOME/Library/Application Support/Google/Chrome"))
EOF
trap 'rm -f "$PROFILE"' EXIT

export TMPDIR="$TMP/" UV_CACHE_DIR="$HOME/.cache/uv" UV_OFFLINE=0
if [ "$SELFTEST" = 1 ]; then
  ok=0
  t() { # t <expect: ok|deny> <description> <command...>
    local expect="$1" what="$2"; shift 2
    if sandbox-exec -f "$PROFILE" "$@" >/dev/null 2>&1; then got=ok; else got=deny; fi
    if [ "$got" = "$expect" ]; then echo "PASS  $what"; else echo "FAIL  $what (got $got)"; ok=1; fi
  }
  t ok   "write inside the worktree"            sh -c "touch '$WT/.selftest' && rm '$WT/.selftest'"
  t ok   "git commit data dir writable"          sh -c "touch '$GITDIR/.selftest' && rm '$GITDIR/.selftest'"
  t ok   "write the codex reply file"            sh -c ": >> '$REPLY'"
  t deny "write in the main checkout"            sh -c "touch '$MAIN/.selftest'"
  t deny "write in another worktree"             sh -c "touch /private/tmp/kuulas-o39/.selftest"
  t deny "write in the podcast repo"             sh -c "touch '$HOME/Documents/koodi/podcast/.selftest'"
  t deny "write in the home folder"              sh -c "touch '$HOME/.selftest'"
  t deny "read ~/.config"                        sh -c "ls '$HOME/.config'"
  t deny "read ~/.ssh"                           sh -c "ls '$HOME/.ssh'"
  t ok   "read the main checkout"                sh -c "ls '$MAIN' >/dev/null"
  t ok   "git status in the worktree"            sh -c "cd '$WT' && git status >/dev/null"
  exit $ok
fi

exec sandbox-exec -f "$PROFILE" codex --sandbox danger-full-access --ask-for-approval never \
  -C "$WT" "$PROMPT"
