#!/bin/sh
# Screenshots of the prototype, every screen in both themes (and the main
# screen in Finnish), with headless Chrome. Usage, from the repo root:
#   sh docs/design/screenshots.sh
# Needs Google Chrome (macOS path below; set CHROME to override).
set -eu
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/screenshots"
PROFILE="$(mktemp -d)"
mkdir -p "$OUT"
shot() { # name query
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
    --user-data-dir="$PROFILE" --window-size=1440,900 --force-device-scale-factor=1 \
    --virtual-time-budget=1500 --screenshot="$OUT/$1.png" \
    "file://$HERE/prototype/index.html?clean=1&$2" >/dev/null 2>&1
  echo "$OUT/$1.png"
}
for theme in light dark; do
  for screen in main transcript history candidates palette focus empty error; do
    shot "$screen-$theme" "screen=$screen&theme=$theme"
  done
  shot "main-$theme-fi" "screen=main&theme=$theme&lang=fi"
  shot "error-$theme-fi" "screen=error&theme=$theme&lang=fi"
  shot "main-$theme-compact" "screen=main&theme=$theme&density=compact"
done
rm -rf "$PROFILE"
