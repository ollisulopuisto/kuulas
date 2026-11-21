# CUDA 13 dependency experiment

Branch only, not a release or PR. Torch 2.13.0 and TorchAudio 2.11.1 with a regenerated uv.lock. Linux resolves CUDA 13.0 runtime libraries. No main or advisory-fix branch changes. Do not merge this experiment without hardware acceptance.

Use an isolated checkout on the NVIDIA Windows GPU PC inside an existing WSL2 Ubuntu environment, not the Mac. Native Windows wheels exist, but this experiment specifically targets the Linux CUDA 13 dependency graph. NVIDIA recommends a current Windows production driver and says not to install a Linux display driver inside WSL. No driver changes are performed by this branch. Verify WSL2 and nvidia-smi first.

Keep kuulas and podcast as sibling directories in a new experiment directory. Clone podcast alongside this branch because the project uses its editable path packages. With uv installed, run `uv sync --locked --extra transcribe --python 3.13`. This can download several GB into an isolated .venv. It does not update drivers or run the GUI.

Run `uv run --frozen --extra transcribe python scripts/cuda13_smoke.py --check`. PASS requires a CUDA 13 Torch build, a visible GPU, a real CUDA tensor calculation and TorchAudio's MMS_FA API. No CPU fallback is allowed.

For a minimal separate CTranslate2 transcription test, run `uv run --frozen --extra transcribe python scripts/cuda13_smoke.py /path/to/short-speech.wav` with a clear local 5-15 second clip. The first run downloads the public tiny Whisper weights. Audio stays local. PASS means nonempty text and completion without CPU fallback. This tests faster-whisper's own GPU runtime, not Torch's kernels or the full editor. Missing CUDA 12 libraries in CTranslate2, driver mismatch or missing MMS_FA are failures to report, not reasons to silently fall back. Do not install random runtime packages to conceal a failure.

Verified here: lock resolution, command help and input validation, Ruff. GPU execution, Torch/TorchAudio import, model download, speech recognition, driver compatibility, WSL2 and native Windows are UNRUN. No NVIDIA GPU is available in the execution environment.

Sources:
- https://docs.pytorch.org/audio/stable/installation.html
- https://docs.nvidia.com/cuda/wsl-user-guide/
