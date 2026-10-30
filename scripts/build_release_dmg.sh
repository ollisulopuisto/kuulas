#!/usr/bin/env bash
# Build a committed Kuulas ref as a tester DMG with the release-pinned Podcast source.
# This wrapper keeps the two clean build worktrees separate from the user's checkouts.
set -Eeuo pipefail

readonly DEFAULT_PODCAST_COMMIT="5a179e6f16024a0e1aa6fa9d01a0edcb09cdf2fc"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly script_dir
repo="$(cd -- "$script_dir/.." && pwd -P)"
readonly repo

ref="HEAD"
podcast_repo="$repo/../podcast"
podcast_commit="$DEFAULT_PODCAST_COMMIT"
out="$PWD/dist"

usage() {
  cat <<'USAGE'
Build a clean Kuulas DMG from a committed ref and the release-pinned Podcast source.

Usage: scripts/build_release_dmg.sh [options]

Options:
  --ref REF                 Kuulas tag, branch, or commit (default: HEAD)
  --podcast-repo PATH       Podcast checkout (default: ../podcast)
  --podcast-commit SHA      Podcast commit (default: release workflow pin)
  --out PATH                DMG output directory (default: ./dist)
  -h, --help                Show this help

Requires Apple-silicon macOS, full Xcode, uv, git, and network access for build assets.
The script fetches origin/main if the pinned Podcast commit is missing locally, creates
temporary detached worktrees for both repositories, runs the normal DMG builder, and
removes its worktrees afterward. It never changes files in either checkout.

Example:
  scripts/build_release_dmg.sh --ref v26.10.30.2 --out ~/Desktop/kuulas-dmg
USAGE
}

fail() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --ref|--podcast-repo|--podcast-commit|--out)
      (($# >= 2)) || fail "missing value for $1"
      option="$1"
      value="$2"
      shift 2
      case "$option" in
        --ref) ref="$value" ;;
        --podcast-repo) podcast_repo="$value" ;;
        --podcast-commit) podcast_commit="$value" ;;
        --out) out="$value" ;;
      esac
      ;;
    -h|--help) usage; exit 0 ;;
    --) shift; (($# == 0)) || fail "unexpected positional arguments: $*" ;;
    *) fail "unknown option: $1" ;;
  esac
done

[[ "$(uname -s)" == Darwin ]] || fail "DMG builds require macOS on Apple silicon."
[[ "$(uname -m)" == arm64 ]] || fail "DMG builds require an Apple-silicon Mac."
command -v git >/dev/null 2>&1 || fail "git is required."
command -v uv >/dev/null 2>&1 || fail "uv is required; install it before building."
command -v xcodebuild >/dev/null 2>&1 || fail "full Xcode is required; Command Line Tools alone are not enough."
if ! xcode_info="$(xcodebuild -version 2>&1)"; then
  printf 'error: Xcode is not ready. Install/select full Xcode in Xcode > Settings > Locations, then retry.\n%s\n' \
    "$xcode_info" >&2
  exit 1
fi

[[ -d "$podcast_repo/.git" || -f "$podcast_repo/.git" ]] || fail "Podcast checkout not found: $podcast_repo (use --podcast-repo PATH)."
kuulas_sha="$(git -C "$repo" rev-parse --verify "$ref^{commit}" 2>/dev/null)" || \
  fail "Kuulas ref is not available locally: $ref. Fetch it, then retry."

if ! git -C "$podcast_repo" cat-file -e "$podcast_commit^{commit}" 2>/dev/null; then
  printf 'Podcast commit %s is missing locally; fetching origin/main...\n' "$podcast_commit"
  git -C "$podcast_repo" fetch origin main || \
    fail "Could not fetch origin/main from $podcast_repo. Check the remote and network, then retry."
fi
git -C "$podcast_repo" cat-file -e "$podcast_commit^{commit}" 2>/dev/null || \
  fail "Podcast commit $podcast_commit is still unavailable after fetching origin/main."

out_parent="$(dirname -- "$out")"
out_name="$(basename -- "$out")"
mkdir -p -- "$out_parent"
out="$(cd -- "$out_parent" && pwd -P)/$out_name"

tmp="$(mktemp -d "${TMPDIR:-/tmp}/kuulas-release-dmg.XXXXXX")"
kuulas_worktree="$tmp/kuulas"
podcast_worktree="$tmp/podcast"

cleanup() {
  git -C "$repo" worktree remove --force "$kuulas_worktree" >/dev/null 2>&1 || true
  git -C "$podcast_repo" worktree remove --force "$podcast_worktree" >/dev/null 2>&1 || true
  rm -rf -- "$tmp"
}
trap cleanup EXIT

printf 'Kuulas:  %s (%s)\n' "$ref" "${kuulas_sha:0:12}"
printf 'Podcast: %s (%s)\n' "$podcast_commit" "${podcast_commit:0:12}"
printf 'Output:  %s\n' "$out"
git -C "$repo" worktree add --quiet --detach "$kuulas_worktree" "$kuulas_sha"
git -C "$podcast_repo" worktree add --quiet --detach "$podcast_worktree" "$podcast_commit"
PODCAST_SRC="$podcast_worktree" "$kuulas_worktree/scripts/build_dmg.sh" --out "$out"
