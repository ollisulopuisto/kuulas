
## Security advisory fixes, 2026-11-21

Branch: `agent/security-advisory-fixes`. Owner: Instinct. Status: Review pending.

Patch the locked opentelemetry-api dependency without changing the editor. This removes CVE-2026-126360. The Torch advisories remain because the tested resolver path to Torch 2.13 changes Linux CUDA 12 to CUDA 13, which needs an owner decision and GPU testing. No merge or release is requested.


<details><summary>Verification and limits</summary>

- uv lock updates only opentelemetry-api 1.45.1 to 1.45.2.
- Frozen all-extras/all-groups registry audit: three records before, two Torch records after. Local/project dependencies are outside the PyPI audit.
- uv sync and Ruff pass. The full pytest run exceeded 95 seconds with failures, not a pass. Its first failure is test_automix.py::test_missing_command_is_one_clear_error: PermissionError in this environment. The same test fails on unchanged main in the same environment.
- Torch 2.13.0 + TorchAudio 2.11.1 resolves and audits with zero records, but introduces a CUDA major runtime change. It is excluded. TorchAudio 2.11 supports Torch 2.11 and later: https://docs.pytorch.org/audio/stable/installation.html
- Optional transcription, real GPU, native Mac and hardware audio checks were not run. No CI or scanner-pilot files changed.
- Own review: lock diff and hashes checked, only the intended patch retained. Devin review requested separately.

</details>
