#!/bin/bash
# Fetch static arm64 ffmpeg and ffprobe for the tester bundle (WP73) into a folder.
#
#   scripts/fetch_ffmpeg.sh <folder>
#
# Why: libsndfile (soundfile) reads WAV, FLAC, OGG, MP3 and AIFF, but not m4a, aac,
# mp4, mov, mkv or webm, and kuulas needs ffprobe to measure them, so a tester's Mac
# without Homebrew could not import a phone recording. See docs/desktop.md.
#
# Source: https://ffmpeg.martin-riedl.de (static, signed, GPLv3 builds of release
# versions). Licence: the binaries are GPLv3 and are shipped as separate programs
# next to the app, not linked into it; docs/desktop.md has the notice and the source
# link. `KUULAS_FFMPEG_DIR=<folder with ffmpeg and ffprobe>` skips the download (for an
# offline build, or a build with your own ffmpeg).
#
# Cache: `KUULAS_FFMPEG_CACHE=<folder>` keeps a copy of the last good download there (the
# dmg workflow restores and saves that folder with actions/cache). A fresh download writes
# the copy and a `.fresh` marker file (the workflow saves the cache only then); when the
# host is down (it returned 521 for hours on 2026-10-21) and the folder holds both
# binaries, they are used instead and the build goes on. With no cache either, the last
# resort is the same pair of binaries kept as an asset of this repository's `ffmpeg-cache`
# release (`KUULAS_FFMPEG_FALLBACK_URL` overrides the address).
set -euo pipefail

dest="${1:?usage: fetch_ffmpeg.sh <folder>}"
mkdir -p "$dest"

cache="${KUULAS_FFMPEG_CACHE:-}"
fallback_url="${KUULAS_FFMPEG_FALLBACK_URL:-https://github.com/ollisulopuisto/kuulas/releases/download/ffmpeg-cache/ffmpeg-arm64-macos.zip}"

download() {
  # Into $1; fails (non-zero) on any curl or unzip error.
  local tmp="$1" name
  for name in ffmpeg ffprobe; do
    # The default environment may route curl through a local proxy that refuses this host.
    env -u HTTPS_PROXY -u HTTP_PROXY curl -fsSL --retry 3 -o "$tmp/$name.zip" \
      "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$name.zip" || return 1
    unzip -qo "$tmp/$name.zip" -d "$tmp" || return 1
    [ -f "$tmp/$name" ] || return 1
  done
}

if [ -n "${KUULAS_FFMPEG_DIR:-}" ]; then
  cp "$KUULAS_FFMPEG_DIR/ffmpeg" "$KUULAS_FFMPEG_DIR/ffprobe" "$dest/"
else
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  if download "$tmp"; then
    install -m 755 "$tmp/ffmpeg" "$dest/ffmpeg"
    install -m 755 "$tmp/ffprobe" "$dest/ffprobe"
    if [ -n "$cache" ]; then
      mkdir -p "$cache"
      install -m 755 "$tmp/ffmpeg" "$cache/ffmpeg"
      install -m 755 "$tmp/ffprobe" "$cache/ffprobe"
      : > "$cache/.fresh"
    fi
  elif [ -n "$cache" ] && [ -x "$cache/ffmpeg" ] && [ -x "$cache/ffprobe" ]; then
    echo "NOTICE: the ffmpeg download host is not answering; using the cached copy in $cache" >&2
    install -m 755 "$cache/ffmpeg" "$dest/ffmpeg"
    install -m 755 "$cache/ffprobe" "$dest/ffprobe"
  else
    echo "NOTICE: the ffmpeg download host is not answering and there is no cache; trying the fallback copy" >&2
    rm -rf "$tmp/fb" && mkdir -p "$tmp/fb"
    if env -u HTTPS_PROXY -u HTTP_PROXY curl -fsSL --retry 3 -o "$tmp/fb/ffmpeg.zip" "$fallback_url" \
        && unzip -qo "$tmp/fb/ffmpeg.zip" -d "$tmp/fb" && [ -f "$tmp/fb/ffmpeg" ] && [ -f "$tmp/fb/ffprobe" ]; then
      install -m 755 "$tmp/fb/ffmpeg" "$dest/ffmpeg"
      install -m 755 "$tmp/fb/ffprobe" "$dest/ffprobe"
    else
      echo "ERROR: could not download ffmpeg, no cached copy and the fallback failed" >&2
      exit 1
    fi
  fi
fi

chmod 755 "$dest/ffmpeg" "$dest/ffprobe"
"$dest/ffmpeg" -version | head -1
"$dest/ffprobe" -version | head -1
shasum -a 256 "$dest/ffmpeg" "$dest/ffprobe"
