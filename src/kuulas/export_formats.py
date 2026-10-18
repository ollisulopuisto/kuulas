"""The audio formats an export can write (WP11), and which of them this
machine's ffmpeg can actually make.

Every format is one ``Format`` in ``ALL_FORMATS``: its file extension, the
ffmpeg container and options, whether it is lossless, which options it takes
(bit depth for the PCM formats, a bitrate range for the lossy ones) and the
encoders that can write it, best first. ``available_formats()`` asks ffmpeg
(``-encoders``) once per process and keeps the formats that have an encoder.

WAV and FLAC are written in-process (soundfile) and AIFF is plain PCM, so those
three exist on every machine that has even a stripped ffmpeg; WAV and FLAC need
no ffmpeg at all.

Hardware: the only encoder here that is hardware or OS accelerated is the
macOS AudioToolbox AAC encoder ``aac_at``, preferred for M4A when listed.
Audio encoding is cheap (a one-hour programme encodes in seconds on any
encoder), so that is a convenience, not a speed need.
"""

from __future__ import annotations

import functools
import re
import subprocess
from dataclasses import dataclass, replace

#: Written by the exporter itself (soundfile), not by ffmpeg.
INTERNAL = "internal"
#: Encoders that are hardware or OS accelerated, not software.
HARDWARE_ENCODERS = frozenset({"aac_at"})


@dataclass(frozen=True)
class Format:
    id: str
    ext: str
    lossless: bool
    #: Candidate encoders, best first; ``INTERNAL`` means written in-process.
    encoders: tuple[str, ...]
    #: ffmpeg muxer (``-f``); ``None`` for the in-process formats.
    container: str | None = None
    #: Extra muxer options, e.g. the ID3 version.
    container_args: tuple[str, ...] = ()
    #: Bit depths a PCM format takes (16/24, 32 is float for WAV).
    bit_depths: tuple[int, ...] = ()
    #: PCM codec name per bit depth, e.g. ``pcm_s{bits}be`` for AIFF.
    pcm: str | None = None
    #: Other encoders that must also exist (AIFF needs all three depths).
    also: tuple[str, ...] = ()
    #: Bitrate range in kbps for a lossy format, and its default for (mono, stereo).
    kbps: tuple[int, int] | None = None
    kbps_default: tuple[int, int] = (0, 0)
    #: The encoder this machine uses; set by ``formats_for``.
    encoder: str | None = None

    @property
    def label_key(self) -> str:
        return f"export.format.{self.id}"

    @property
    def accelerated(self) -> bool:
        return self.encoder in HARDWARE_ENCODERS

    @property
    def internal(self) -> bool:
        return self.encoders == (INTERNAL,)

    def default_kbps(self, channels: int) -> int:
        return self.kbps_default[0 if channels == 1 else 1]

    def codec_args(self, bit_depth: int, kbps: int | None, channels: int) -> list[str]:
        """The ffmpeg options after ``-i``, up to the output path."""
        codec = self.pcm.format(bits=bit_depth) if self.pcm else self.encoder
        args = ["-c:a", str(codec)]
        if self.kbps:
            args += ["-b:a", f"{kbps or self.default_kbps(channels)}k"]
        if self.container:
            args += ["-f", self.container]
        return [*args, *self.container_args]


ALL_FORMATS: tuple[Format, ...] = (
    Format("wav", "wav", True, (INTERNAL,), bit_depths=(16, 24, 32)),
    Format("flac", "flac", True, (INTERNAL,), bit_depths=(16, 24)),
    Format("mp3", "mp3", False, ("libmp3lame",), container="mp3",
           container_args=("-id3v2_version", "3"), kbps=(64, 320),
           kbps_default=(128, 192)),
    Format("aiff", "aiff", True, ("pcm_s24be",), container="aiff",
           container_args=("-write_id3v2", "1", "-id3v2_version", "3"),
           bit_depths=(16, 24, 32), pcm="pcm_s{bits}be",
           also=("pcm_s16be", "pcm_s32be")),
    # The native "aac" is stable; "libfdk_aac" is only in non-redistributable builds.
    Format("m4a", "m4a", False, ("aac_at", "aac", "libfdk_aac"), container="ipod",
           kbps=(64, 320), kbps_default=(96, 160)),
    # ffmpeg's own "opus" and "vorbis" encoders are experimental and poor, so
    # only the reference libraries count.
    Format("opus", "opus", False, ("libopus",), container="ogg",
           kbps=(24, 256), kbps_default=(48, 96)),
    Format("ogg", "ogg", False, ("libvorbis",), container="ogg",
           kbps=(64, 320), kbps_default=(96, 160)),
)
DEFAULT = "wav"

_ENCODER_LINE = re.compile(r"^\s*A[.\w]{5}\s+(\S+)\s")


def parse_encoders(text: str) -> set[str]:
    """The audio encoder names in the output of ``ffmpeg -hide_banner -encoders``."""
    names: set[str] = set()
    listing = False
    for line in text.splitlines():
        if line.strip().startswith("------"):
            listing = True
        elif listing and (m := _ENCODER_LINE.match(line)):
            names.add(m.group(1))
    return names


def formats_for(encoders: set[str]) -> list[Format]:
    """The formats that can be written with ``encoders``, each with the encoder
    to use (the first candidate that exists), in registry order."""
    found = []
    for fmt in ALL_FORMATS:
        if fmt.internal:
            found.append(replace(fmt, encoder=INTERNAL))
        elif all(name in encoders for name in fmt.also):
            encoder = next((e for e in fmt.encoders if e in encoders), None)
            if encoder:
                found.append(replace(fmt, encoder=encoder))
    return found


def _installed_encoders() -> set[str]:
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],  # noqa: S607 - ffmpeg from PATH
            capture_output=True, text=True,
            timeout=20, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return parse_encoders(out)


@functools.cache
def available_formats() -> list[Format]:
    """What this machine can export; ffmpeg is asked once per process."""
    return formats_for(_installed_encoders())


def get(format_id: str) -> Format | None:
    """The available format with this id, or ``None``."""
    return next((f for f in available_formats() if f.id == format_id), None)
