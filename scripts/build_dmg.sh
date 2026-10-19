#!/bin/bash
# Build the unsigned tester .dmg of Kuulas for macOS (WP73), from the committed code.
#
#   scripts/build_dmg.sh [--out <folder>]      (default: ./dist)
#
# What it does, in order:
#   1. exports HEAD with `git archive` into a work folder (an uncommitted change is not
#      in the build; the script says so),
#   2. builds the wheels of speechmix and nhsx from the podcast repo's origin/main
#      (build_wheels.sh) and fetches static ffmpeg and ffprobe (fetch_ffmpeg.sh),
#   3. stages a Briefcase project (stage_bundle.py), creates and builds Kuulas.app,
#   4. runs `Kuulas.app --selftest` (headless: libraries, ffmpeg, UI files, a project,
#      the server, the loudness meter, the recorder, and the transcription worker started
#      as the editor starts it, which must run a no-op job to "completed") and stops if
#      it fails,
#   5. packages "Kuulas <version>.dmg" (ad-hoc signed, NOT notarised: the first open
#      needs right-click > Open, see docs/TESTERS.md), mounts it and runs --selftest
#      again on the app inside, and prints the file, its size and its checksum.
#
# Needs: macOS on Apple silicon, uv, git, network (Briefcase template and wheels, ffmpeg).
# Everything it writes is under <repo>/build/dmg and the --out folder; the Briefcase
# cache is kept in build/dmg too (BRIEFCASE_HOME), not in ~/Library/Caches. Nothing is
# registered with Launch Services and nothing needs sudo. The selftest runs with a
# throw-away HOME so the build leaves no logs or caches in yours.
set -euo pipefail

BRIEFCASE="briefcase==0.4.6"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="$here/dist"
while [ $# -gt 0 ]; do
  case "$1" in
    --out) out="$(mkdir -p "$2" && cd "$2" && pwd)"; shift 2 ;;
    *) echo "usage: build_dmg.sh [--out <folder>]" >&2; exit 2 ;;
  esac
done

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "build_dmg.sh builds the Apple-silicon app and runs on an Apple-silicon Mac." >&2
  exit 1
fi

work="$here/build/dmg"
rm -rf "$work"
mkdir -p "$work/src" "$work/briefcase-home" "$out"

if [ -n "$(git -C "$here" status --porcelain)" ]; then
  echo "note: uncommitted changes are NOT in this build (it builds HEAD)."
fi
git -C "$here" archive HEAD | tar -x -C "$work/src"
version="$(python3 -c 'import sys,tomllib;print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$work/src/pyproject.toml")"
label="v$version+$(git -C "$here" rev-parse --short HEAD)"
echo "== building Kuulas $label"

echo "== wheels"
"$here/scripts/build_wheels.sh" "$work/wheels"
echo "== ffmpeg"
"$here/scripts/fetch_ffmpeg.sh" "$work/ffmpeg"

echo "== stage"
python3 "$here/scripts/stage_bundle.py" --src "$work/src" --out "$work/stage" \
  --wheels "$work/wheels" --label "$label"

# Briefcase fetches its template and the Python support package from GitHub; a local
# HTTP proxy in the environment may refuse that. It also keeps its cache under
# BRIEFCASE_HOME, which must exist.
unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy
export BRIEFCASE_HOME="$work/briefcase-home"
briefcase() { (cd "$work/stage" && uvx --python 3.13 --from "$BRIEFCASE" briefcase "$@" --no-input); }

echo "== briefcase create"
briefcase create macOS app
app="$work/stage/build/kuulas/macos/app/Kuulas.app"
# Before `build`, which signs the app: anything added later would break the signature.
mkdir -p "$app/Contents/Resources/bin"
cp "$work/ffmpeg/ffmpeg" "$work/ffmpeg/ffprobe" "$app/Contents/Resources/bin/"
echo "== briefcase build"
briefcase build macOS app

selftest() {  # <Kuulas.app>
  local home="$work/selftest-home"
  rm -rf "$home" && mkdir -p "$home"
  # No locale variables, as when the app is started from Finder (v26.10.19.28 crashed on start then).
  env -u LC_ALL -u LC_MESSAGES HOME="$home" "$1/Contents/MacOS/Kuulas" --selftest
}
echo "== selftest (built app)"
selftest "$app"

echo "== briefcase package"
briefcase package macOS app --adhoc-sign -p dmg
built="$(ls "$work"/stage/dist/*.dmg | head -1)"
dmg="$out/Kuulas $version.dmg"
cp "$built" "$dmg"

echo "== selftest (app inside the dmg)"
mnt="$work/mnt"
mkdir -p "$mnt"
hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$mnt" "$dmg" >/dev/null
trap 'hdiutil detach -quiet "$mnt" 2>/dev/null || true' EXIT
selftest "$mnt/Kuulas.app"
hdiutil detach -quiet "$mnt"
trap - EXIT

echo "== done"
du -sh "$app" | awk '{print "app bundle:", $1}'
ls -l "$dmg" | awk '{print "dmg:", $9, $10, $11, "(" $5 " bytes)"}'
du -h "$dmg" | awk '{print "dmg size:", $1}'
shasum -a 256 "$dmg"
echo "label: $label"
