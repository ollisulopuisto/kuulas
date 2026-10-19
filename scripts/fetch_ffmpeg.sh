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
set -euo pipefail

dest="${1:?usage: fetch_ffmpeg.sh <folder>}"
mkdir -p "$dest"

if [ -n "${KUULAS_FFMPEG_DIR:-}" ]; then
  cp "$KUULAS_FFMPEG_DIR/ffmpeg" "$KUULAS_FFMPEG_DIR/ffprobe" "$dest/"
else
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  for name in ffmpeg ffprobe; do
    # The default environment may route curl through a local proxy that refuses this host.
    env -u HTTPS_PROXY -u HTTP_PROXY curl -fsSL --retry 3 -o "$tmp/$name.zip" \
      "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$name.zip"
    unzip -qo "$tmp/$name.zip" -d "$tmp"
    install -m 755 "$tmp/$name" "$dest/$name"
  done
fi

chmod 755 "$dest/ffmpeg" "$dest/ffprobe"
"$dest/ffmpeg" -version | head -1
"$dest/ffprobe" -version | head -1
shasum -a 256 "$dest/ffmpeg" "$dest/ffprobe"
