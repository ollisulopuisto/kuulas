"""Kuulas's warm Orukeet worker for live takes: one load, many chunks.

Standalone on purpose (only stdlib + the pinned orukeet wheel): the factory
runs this file by path in an environment that has orukeet, so it must not
import kuulas. Same JSON-lines protocol as orukeet.worker, two differences:
``transcribe`` takes the audio's sample rate and returns the engine's native
word timings (orukeet.worker resamples from files and keeps only segments),
and the audio is raw float32 instead of an encoded file.
"""

import array
import json
import os
import sys


def _resample(samples, rate):
    """swresample (av ships with the orukeet wheel) to the engine's 16 kHz."""
    if rate == 16000:
        return samples
    import av
    import numpy as np

    frame = av.AudioFrame.from_ndarray(
        np.frombuffer(samples, dtype=np.float32).reshape(1, -1),
        format="flt", layout="mono")
    frame.sample_rate = rate
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    out = [f.to_ndarray().reshape(-1)
           for f in (*resampler.resample(frame), *resampler.resample(None))]
    return array.array("f", np.concatenate(out) if out else np.zeros(0, np.float32))


def _transcribe_words(engine, samples):
    """The native recognize call, keeping the word times the engine emits.

    Uses NvidiaRecognizer internals the public worker hides behind segments;
    pinned to orukeet==0.1.1 (the factory resolves exactly that wheel).
    """
    import ctypes as c

    options = engine._options(None)
    result = c.c_void_p()
    buf = (c.c_float * len(samples)).from_buffer(samples)
    engine._check(engine.lib.nemo_speech_asr_recognize_f32(
        engine.handle, c.byref(options), buf, len(samples), 16000,
        c.byref(result)))
    data = engine._result(result)
    return [{"word": w["text"], "start": w["start"], "end": w["end"]}
            for w in data["words"]]


def main():
    # The native library's diagnostics belong on stderr; stdout is protocol.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w",
                         encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    engine = None
    try:
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                if request["op"] == "load":
                    from orukeet.nvidia import NvidiaRecognizer
                    if engine is not None:
                        engine.close()
                    engine = None
                    engine = NvidiaRecognizer(
                        request["runtime"], request["model_path"],
                        request["device"])
                    result = {"device": request["device"]}
                elif request["op"] == "transcribe":
                    if engine is None:
                        raise RuntimeError("error.live_engine.no_model")
                    samples = array.array("f")
                    with open(request["audio_path"], "rb") as stream:
                        samples.frombytes(stream.read())
                    result = {"words": _transcribe_words(
                        engine, _resample(samples, int(request["rate"])))}
                else:
                    raise ValueError("error.live_engine.unknown_operation")
                response = {"id": request["id"], "result": result}
            except Exception as exc:
                response = {"id": request.get("id"), "error": str(exc)}
            protocol.write(json.dumps(response, ensure_ascii=True) + "\n")
    finally:
        if engine is not None:
            engine.close()


if __name__ == "__main__":
    main()
