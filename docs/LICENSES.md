# Licences of what the .dmg ships

Checked 2026-10-21 against the packages a Kuulas.app build installs (podcast main
`automixer 2026.10.21.2`, Python 3.13, macOS arm64), read from each package's metadata.
Not legal advice: this lists the facts and what follows from them plainly.

Owner decision (2026-10-21): bundling GPL components (pedalboard, GPL-3) is fine. This
page records what that means and what the bundle carries for it.

## GPL and LGPL parts

| Part | Licence | How Kuulas uses it |
|---|---|---|
| pedalboard 0.9.26 (Spotify; includes JUCE and Rubber Band) | GPL-3.0 | imported **in the Kuulas process** (speechmix, the selftest) and by the bundled automixer |
| ffmpeg, ffprobe (static builds, `Contents/Resources/bin`) | GPL-3.0 | separate programs |
| soxr (python-soxr, libsoxr) | LGPL-2.1-or-later | imported, a replaceable extension module |
| libsndfile (inside soundfile, `_soundfile_data`) | LGPL-2.1 | a replaceable dylib |

Everything else is permissive: MIT, BSD (2/3-clause), Apache-2.0, PSF-2.0, MIT-0, 0BSD,
Zlib, CC0 (numpy, scipy, numba/llvmlite, fastapi, starlette, uvicorn, pydantic, lxml,
psutil, pyloudnorm, sounddevice/PortAudio, pywebview, pyobjc, websockets, python-multipart,
nhsx, silencelearn). New with the automixer: PyYAML (MIT) and automixer itself (no
licence declared, see below). Its mlx and textual requirements are dropped for the bundle
(scripts/trim_deps.py); both are MIT, as are textual's dependencies, should they return.

## What the GPL asks of the .dmg, and what it carries

- **Licence texts:** each package's own licence files stay in
  `Contents/Resources/app_packages/<package>.dist-info/licenses/` (seen in the local build
  of 2026-10-21: pedalboard's `LICENSE`, the GPL-3 text, and `NOTICE` are there).
- **The notice:** `LICENSE_TEXT` in `scripts/stage_bundle.py` names pedalboard and ffmpeg
  as GPL-3 and says where their licence texts and sources are. Briefcase uses the stage's
  `LICENSE` as metadata only; that build had the text nowhere in the app or the .dmg. It
  now also ships as `Contents/Resources/app/kuulas/LICENSE.txt` (tested at the stage
  step; not yet seen in a built app).
- **Source offer:** GPL-3 section 6(d) allows offering the source from a network
  server next to the binary. The bundle's `LICENSE` points at the public repositories:
  pedalboard (github.com/spotify/pedalboard), Kuulas (github.com/ollisulopuisto/kuulas),
  the podcast packages and the automixer (github.com/ollisulopuisto/podcast), ffmpeg
  (ffmpeg.org). A release should point at the exact commits: the build label in the app
  (`v<version>+<kuulas commit>`) gives Kuulas's, and `build_wheels.sh` prints the podcast
  commit in the build log; the release notes do not carry that commit yet.

## Open for the owner (not blockers)

1. **The bundle's own terms say "do not redistribute".** Kuulas loads pedalboard in its
   own process, so a conveyed Kuulas.app is a work combined with a GPL-3 library; GPL-3
   expects the whole to be passed on under GPL-3 terms, which a "do not redistribute"
   line contradicts. The repository has no `LICENSE` file at all. Choosing a GPL-3
   compatible licence for Kuulas (GPL-3.0-or-later is the simple one) would make the
   two agree; until then the text in `LICENSE_TEXT` is inconsistent with what it ships.
2. **speechmix and automixer declare no licence** (no `License` in their metadata, no
   `LICENSE` file in the podcast repository); nhsx and silencelearn say MIT. Both import
   pedalboard, so the same choice applies to them. A request is in
   docs/PODCAST-MAGIC.md ("Automixer in the dmg").
3. **Plug-ins are not bundled.** VST3/AU plug-ins (dxRevive and others) are the user's
   own installs, under their own commercial licences; Kuulas only finds them in
   `/Library/Audio/Plug-Ins` and `~/Library/Audio/Plug-Ins` (VST3, Components, VST).
