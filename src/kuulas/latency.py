"""The output latency numbers: what the playhead assumes and what the device says.

The engine reports the heard frame as "frames handed to the device minus
``stream.latency``" (``Engine._played``). PortAudio also tells each callback
when the block's first frame reaches the converter (``outputBufferDacTime``,
on the stream's own clock, next to ``currentTime``). That lead plus one block is
what the device really holds when the callback returns, so the two figures can
be compared: ``estimate_ms`` (what the playhead subtracts) against
``measured_ms`` (block + DAC lead, as the host API reports it).

Neither is an end-to-end measurement: the speaker's own delay (Bluetooth,
AirPlay, an AV receiver) is outside what PortAudio sees. ``docs/PLAYBACK-LATENCY.md``
says how to check by ear and with a phone video.

Measured on the owner's Mac Studio (2026-10-20, internal speakers, 48 kHz stream on a
96 kHz device, block 1024): ``stream.latency`` 34.8 ms, DAC lead 14.7 ms, block 21.3
ms, so measured 36.0 ms against the 34.8 ms estimate; callbacks every 21.3 ms with a
spread under 0.1 ms. "low" and "high" gave the same figures at a fixed block size:
on Core Audio the block size sets the buffer.
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Iterable


def callback_timing(times: Iterable[float]) -> tuple[float | None, float | None]:
    """The mean interval between callbacks and its spread (population standard
    deviation), in ms, from their monotonic times in seconds. None, None for fewer
    than three callbacks (two intervals are not a spread)."""
    stamps = list(times)
    gaps = [(b - a) * 1000 for a, b in itertools.pairwise(stamps)]
    if len(gaps) < 2:
        return None, None
    return statistics.fmean(gaps), statistics.pstdev(gaps)


def report(*, setting: str, stream_latency_s: float, blocksize: int, device_rate: int,
           callback_times: Iterable[float], dac_leads: Iterable[float]) -> dict:
    """The numbers ``Engine.status()["latency"]`` carries, ms rounded to 0.01:
    ``setting`` (the PortAudio latency asked for), ``stream_ms``, ``block_ms``,
    ``dac_lead_ms`` (mean, None when the host API gives no DAC times),
    ``callback_ms``/``jitter_ms`` (mean interval and spread, None until a few
    callbacks), ``estimate_ms`` (what the playhead subtracts) and ``measured_ms``
    (block + DAC lead; None without DAC times)."""
    leads = [x * 1000 for x in dac_leads]
    block_ms = blocksize / device_rate * 1000 if device_rate else 0.0
    lead_ms = statistics.fmean(leads) if leads else None
    interval, spread = callback_timing(callback_times)

    def ms(value: float | None) -> float | None:
        return None if value is None else round(value, 2)

    return {
        "setting": setting,
        "stream_ms": ms(stream_latency_s * 1000),
        "block_ms": ms(block_ms),
        "dac_lead_ms": ms(lead_ms),
        "callback_ms": ms(interval),
        "jitter_ms": ms(spread),
        "estimate_ms": ms(stream_latency_s * 1000),
        "measured_ms": ms(None if lead_ms is None else block_ms + lead_ms),
    }


def dac_lead(time_info) -> float | None:
    """Seconds from this callback to its first frame at the converter, from
    PortAudio's time info; None when the host API does not fill it in (zero),
    reports nonsense (negative, or over a second), or there is none (tests)."""
    try:
        lead = float(time_info.outputBufferDacTime) - float(time_info.currentTime)
        dac = float(time_info.outputBufferDacTime)
    except (AttributeError, TypeError, ValueError):
        return None
    if dac <= 0 or not 0 <= lead < 1:
        return None
    return lead
