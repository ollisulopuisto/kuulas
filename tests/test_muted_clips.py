from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas import analysis, ops
from kuulas.model import Clip, Media, Project, Track
from kuulas.session import Session


def _make_wav(path: Path, seconds: float = 2.0, rate: int = 48000) -> Path:
    # 440 Hz tone
    t = np.arange(int(seconds * rate)) / rate
    audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(str(path), audio, rate)
    return path


def test_project_length_ignores_muted_clips():
    # Only muted clips -> length 0
    p_muted_only = Project(
        rate=48000,
        tracks=(
            Track(
                id="t1",
                name="T1",
                clips=(
                    Clip(
                        id="c1",
                        media="m1",
                        start=0,
                        length=48000,
                        offset=0,
                        muted=True,
                    ),
                ),
            ),
        ),
    )
    assert p_muted_only.length == 0

    # Unmuted clip (end=48000) followed by trailing muted clip (end=96000) -> length 48000
    p = Project(
        rate=48000,
        tracks=(
            Track(
                id="t1",
                name="T1",
                clips=(
                    Clip(
                        id="c1",
                        media="m1",
                        start=0,
                        length=48000,
                        offset=0,
                        muted=False,
                    ),
                    Clip(
                        id="c2",
                        media="m1",
                        start=48000,
                        length=48000,
                        offset=0,
                        muted=True,
                    ),
                ),
            ),
        ),
    )
    assert p.length == 48000


def test_export_with_trailing_muted_clip_has_same_length_as_without(tmp_path: Path):
    wav = _make_wav(tmp_path / "audio.wav", seconds=4.0)
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media_id = p.media[0].id

    # Track with one unmuted clip (0 to 48000 frames = 1.0 s)
    t = Track(
        id="t1",
        name="Speech",
        kind="speech",
        clips=(Clip(id="c1", media=media_id, start=0, length=48000, offset=0),),
    )
    s.history.commit("one clip", replace(p, tracks=(t,)))

    out_clean_dir = tmp_path / "out_clean"
    r_clean = s.export({"folder": str(out_clean_dir), "format": "wav", "kind": "mix"})
    info_clean = sf.info(r_clean["path"])

    # Now add a trailing muted clip from 48000 to 96000 frames (another 1.0 s)
    p2 = s.history.state
    t_muted = Track(
        id="t1",
        name="Speech",
        kind="speech",
        clips=(
            Clip(id="c1", media=media_id, start=0, length=48000, offset=0),
            Clip(
                id="c2",
                media=media_id,
                start=48000,
                length=48000,
                offset=0,
                muted=True,
            ),
        ),
    )
    s.history.commit("add trailing muted clip", replace(p2, tracks=(t_muted,)))

    out_muted_dir = tmp_path / "out_muted"
    r_muted = s.export({"folder": str(out_muted_dir), "format": "wav", "kind": "mix"})
    info_muted = sf.info(r_muted["path"])

    # Export length must be identical (no trailing silence added by muted clip)
    assert info_muted.frames == info_clean.frames


def test_ripple_delete_adjacent_to_muted_clip_creates_no_crossfade():
    # Two abutting clips cut by ripple_delete across their boundary.
    # Clip 1 (unmuted): start=0, length=48000, offset=1000
    # Clip 2 (muted): start=48000, length=48000, offset=1000, muted=True
    # Cut from 36000 to 60000.
    media = Media(id="m1", name="m1.wav", channels=1, frames=192000, sha256="a" * 64)
    c1 = Clip(id="c1", media="m1", start=0, length=48000, offset=1000)
    c2_muted = Clip(
        id="c2", media="m1", start=48000, length=48000, offset=1000, muted=True
    )
    p = Project(
        rate=48000,
        media=(media,),
        tracks=(Track(id="t1", name="T1", clips=(c1, c2_muted)),),
    )

    # Ripple cut range [36000, 60000] cuts tail of c1 and head of c2_muted
    rippled = ops.ripple_delete(p, 36000, 60000)
    track = rippled.tracks[0]
    assert len(track.clips) == 2
    left, right = track.clips[0], track.clips[1]
    assert left.id == "c1"
    assert left.start + left.length == right.start
    # Because right is muted, no crossfade must be created on either side
    assert left.xfade_out == 0
    assert right.xfade_in == 0

    # Also test when left is muted and right is unmuted
    c1_muted = Clip(
        id="c1", media="m1", start=0, length=48000, offset=1000, muted=True
    )
    c2_unmuted = Clip(id="c2", media="m1", start=48000, length=48000, offset=1000)
    p_left_muted = Project(
        rate=48000,
        media=(media,),
        tracks=(Track(id="t1", name="T1", clips=(c1_muted, c2_unmuted)),),
    )
    rippled_left = ops.ripple_delete(p_left_muted, 36000, 60000)
    left2, right2 = rippled_left.tracks[0].clips[0], rippled_left.tracks[0].clips[1]
    assert left2.xfade_out == 0
    assert right2.xfade_in == 0


def test_speech_lanes_with_trailing_muted_clip(tmp_path: Path):
    wav = _make_wav(tmp_path / "speech.wav", seconds=4.0)
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media_id = p.media[0].id

    # Unmuted clip 0 to 48000 frames (1 s), trailing muted clip 48000 to 96000 (2 s)
    t = Track(
        id="t1",
        name="Speech",
        kind="speech",
        clips=(
            Clip(id="c1", media=media_id, start=0, length=48000, offset=0),
            Clip(
                id="c2",
                media=media_id,
                start=48000,
                length=48000,
                offset=0,
                muted=True,
            ),
        ),
    )
    p = replace(p, tracks=(t,))

    # speech_lanes should measure up to p.length (48000 frames) and not measure past it
    lanes = analysis.speech_lanes(p, s.store)
    assert len(lanes.speakers) == 1
    lane = lanes.speakers[0]
    expected_hops = int(np.ceil(p.length / analysis.hop_frames(p.rate)))
    assert len(lane.on) == expected_hops
    # At 48000 Hz with 20 ms hops, hop_frames is 960. 48000 / 960 = 50 hops
    assert len(lane.on) == 50


def test_legacy_project_json_with_muted_clips_loads():
    data = {
        "rate": 48000,
        "media": [
            {
                "id": "m1",
                "name": "a.wav",
                "channels": 1,
                "frames": 48000,
                "sha256": "0" * 64,
            }
        ],
        "tracks": [
            {
                "id": "t1",
                "name": "Track 1",
                "clips": [
                    {
                        "id": "c1",
                        "media": "m1",
                        "start": 0,
                        "length": 24000,
                        "offset": 0,
                        "muted": False,
                    },
                    {
                        "id": "c2",
                        "media": "m1",
                        "start": 24000,
                        "length": 24000,
                        "offset": 0,
                        "muted": True,
                    },
                ],
            }
        ],
    }
    loaded = Project.from_json(json.dumps(data))
    assert loaded.tracks[0].clips[1].muted is True
    # Evaluates length based on unmuted clips
    assert loaded.length == 24000
