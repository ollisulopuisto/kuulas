"""Experimental dependency smoke test, not Kuulas GUI acceptance.

Run --check for Torch/TorchAudio CUDA, or pass a short speech file to test
faster-whisper independently. No CPU fallback. Audio stays on this machine;
first transcription downloads the public tiny model weights.
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", nargs="?", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check and args.audio is None:
        parser.error("provide --check or a short speech file")
    if args.audio is not None and not args.audio.is_file():
        parser.error("audio file does not exist")

    # Keep Torch out of the CTranslate2 process, as the app's alignment worker does.
    if args.check:
        import torch  # noqa: PLC0415 - isolate GPU libraries from CTranslate2.
        import torchaudio  # noqa: PLC0415 - only the Torch check needs it.

        print("torch:", torch.__version__)
        print("torchaudio:", torchaudio.__version__)
        print("Torch CUDA build:", torch.version.cuda)
        if not torch.cuda.is_available():
            raise SystemExit("FAIL: Torch CUDA is unavailable; no CPU fallback")
        if not str(torch.version.cuda).startswith("13."):
            raise SystemExit("FAIL: installed Torch is not a CUDA 13 build")
        print("GPU:", torch.cuda.get_device_name(0))
        value = (torch.ones(256, device="cuda") * 2).sum().item()
        torch.cuda.synchronize()
        if value != 512:
            raise SystemExit("FAIL: unexpected CUDA tensor calculation result")
        if not hasattr(torchaudio.pipelines, "MMS_FA"):
            raise SystemExit("FAIL: TorchAudio MMS_FA alignment API is missing")
        print("PASS: Torch CUDA 13 tensor operation and TorchAudio MMS_FA API")
    else:
        from faster_whisper import WhisperModel  # noqa: PLC0415 - separate runtime.

        model = WhisperModel("tiny", device="cuda", compute_type="float16")
        segments, _info = model.transcribe(str(args.audio), beam_size=1)
        count = 0
        for segment in segments:
            if segment.text.strip():
                print(segment.text.strip())
                count += 1
        if not count:
            raise SystemExit("FAIL: no speech text, use a clear 5-15 second speech clip")
        print("PASS: faster-whisper CUDA transcription completed without CPU fallback")


if __name__ == "__main__":
    main()
