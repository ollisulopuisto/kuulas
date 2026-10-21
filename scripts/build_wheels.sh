#!/bin/bash
# Build the wheels the tester bundle installs instead of the ../podcast path
# dependencies (WP73): speechmix, nhsx, silencelearn, the automixer app (shipped so a
# new user can mix without a podcast checkout; Kuulas runs it as its own process), and
# proxy_tools (pywebview needs it and publishes no wheel; Briefcase installs wheels only).
#
#   scripts/build_wheels.sh <out-folder>
#
# The podcast repo is read, never written: its origin/main is cloned (local
# clone, no network) into a temporary folder and built there, so a dirty or
# half-edited checkout cannot leak into a build. `PODCAST_SRC=<folder>` uses a
# clean checkout you made yourself (for example /private/tmp/podcast-main);
# `PODCAST_REPO=<folder>` says where the podcast repo is (default ../podcast).
set -euo pipefail

out="${1:?usage: build_wheels.sh <out-folder>}"
here="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$out"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if [ -n "${PODCAST_SRC:-}" ]; then
  src="$PODCAST_SRC"
  if [ -n "$(git -C "$src" status --porcelain)" ]; then
    echo "PODCAST_SRC is not clean: $src" >&2
    exit 1
  fi
else
  repo="${PODCAST_REPO:-$here/../podcast}"
  sha="$(git -C "$repo" rev-parse origin/main)"
  git clone -q --local --no-hardlinks "$repo" "$tmp/podcast"
  git -C "$tmp/podcast" checkout -q --detach "$sha"
  src="$tmp/podcast"
fi
echo "podcast commit: $(git -C "$src" rev-parse --short HEAD)"

for pkg in speechmix nhsx silencelearn; do
  uv build --wheel --out-dir "$out" "$src/packages/$pkg" >/dev/null
done
# Apps, not libraries: no dependency of Kuulas, but the bundle ships them
# (stage_bundle.APPS; the selftest runs `automixer --help` from the bundle).
# Built from a copy whose unused mlx and textual requirements are dropped (trim_deps.py
# says why: no macOS 12 wheel of mlx); the podcast source is never edited.
for app in automixer; do
  cp -R "$src/apps/$app" "$tmp/app-$app"
  python3 "$here/scripts/trim_deps.py" "$tmp/app-$app/pyproject.toml"
  uv build --wheel --no-sources --out-dir "$out" "$tmp/app-$app" >/dev/null
done

# proxy_tools is a one-file pure-Python package; build its wheel from the sdist.
# The default environment may route pip through a local proxy that refuses PyPI.
env -u HTTPS_PROXY -u HTTP_PROXY uvx pip wheel --no-deps --quiet \
  "proxy_tools==0.1.0" -w "$out"

ls -1 "$out"
