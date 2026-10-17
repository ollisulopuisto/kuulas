#!/bin/sh
# Screenshots of the prototype with headless Chrome. Usage, from the repo root:
#   sh docs/design/screenshots.sh
# Needs Google Chrome (macOS path below; set CHROME to override). The real
# editor (app-*.png) is captured in a real Chrome window, not here: headless
# virtual time can capture the waveform worker's previous frame. Known headless
# artifact: screens that scroll the transcript (transcript, crosstalk) can show
# a few pixels of the top bar at the very bottom edge; the page itself is fine.
set -eu
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/screenshots"
PROFILE="$(mktemp -d)"
mkdir -p "$OUT"
shot() { # name query [width] [height]
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
    --user-data-dir="$PROFILE" --window-size="${3:-1440},${4:-900}" --force-device-scale-factor=1 \
    --virtual-time-budget=2000 --screenshot="$OUT/$1.png" \
    "file://$HERE/prototype/index.html?clean=1&$2" >/dev/null 2>&1
  echo "$OUT/$1.png"
}
for theme in light dark; do
  for screen in main transcript crosstalk history candidates recording palette compare collapsed focus import-drop import menu empty error; do
    shot "$screen-$theme" "screen=$screen&theme=$theme"
  done
  for screen in main crosstalk error collapsed; do
    shot "$screen-$theme-fi" "screen=$screen&theme=$theme&lang=fi"
  done
  for screen in main collapsed; do
    shot "$screen-$theme-compact" "screen=$screen&theme=$theme&density=compact"
  done
  shot "gallery-$theme" "screen=gallery&theme=$theme" 1440 3400
  for screen in help-timeline help-clip help-track help-search; do
    shot "$screen-$theme" "screen=$screen&theme=$theme"
  done
  shot "help-track-$theme-fi" "screen=help-track&theme=$theme&lang=fi"
  shot "welcome-$theme" "screen=welcome&theme=$theme" 1440 1100
  shot "cuts-$theme" "screen=cuts&theme=$theme" 1600 1500
  shot "cuts-$theme-fi" "screen=cuts&theme=$theme&lang=fi" 1600 1500
  shot "nested-$theme" "screen=nested&theme=$theme" 1440 1000
  shot "nested-collapsed-$theme" "screen=nested-collapsed&theme=$theme" 1440 1000
done
# Window sizes: the main screen at each width, both densities (light).
for width in 1024 1280 1440 1920 2560; do
  for density in comfortable compact; do
    shot "width-$width-$density" "screen=main&theme=light&density=$density" "$width" 900
  done
done
# Before/after of the density rework: density-before-*.png were taken from
# the prototype at main (v26.10.17.8) before this change; these are after.
shot "density-after-main-light" "screen=main&theme=light"
shot "density-after-main-dark" "screen=main&theme=dark"
rm -rf "$PROFILE"
