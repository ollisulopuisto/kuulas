# Local Orukeet transcription

The installed editor still called faster-whisper for local jobs although the shared
podcast transcription tool already supports local Orukeet. Local jobs now invoke
that tool with `--backend orukeet` and the converted model at
`~/.models/orukeet-mlx` (or an explicit model folder). Whisper model size values
in persisted jobs select the Orukeet default. A missing model is an actionable
translated error; it never silently selects generic Parakeet.

Development uses the adjacent podcast tool with its `parakeet` extra and a frozen
lockfile. Packaged installs use the public tool through uvx with parakeet-mlx in
an isolated environment. No transcription pipeline is copied into kuulas. Local
inference stays on this Apple-silicon Mac; no Colab login or upload is involved.
The converted model must be installed separately. The first tool-environment setup
may need network access. The legacy `transcribe` extra stays as an empty alias.

Tests first: five new adapter regressions failed against the Whisper implementation.
They cover command selection, words/times, missing model without fallback,
cancellation, process failure, and isolated MLX dependencies. Worker/import tests
now require Orukeet timing metadata instead of clearing the local timing marker;
undo-step and stale-result protection assertions remain intact.

A real inference smoke test on this Mac used only a system-generated Finnish
sentence (no user media): Orukeet returned all six words with word times.
