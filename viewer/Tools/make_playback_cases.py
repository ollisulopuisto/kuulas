"""Reviewed synthetic stereo/crossfade cases, bound to the Python mixer.

Independent from the reader fixture: explicit cases exercise audible features
that the first mono golden windows did not establish. No user audio or models.
"""
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from kuulas import mixer
from kuulas.model import Bus, Clip, Media, Project, Track

ROOT = Path(__file__).resolve().parents[1] / 'Conformance'


class Source:
    def __init__(self):
        self.audio = np.array([[0.1, -0.3, 0.5, -0.7] * 32,
                               [-0.2, 0.4, -0.6, 0.8] * 32], dtype=np.float32)

    def read(self, _media, first, count):
        result = np.zeros((2, count), dtype=np.float32)
        lo, hi = max(0, first), min(self.audio.shape[1], first + count)
        if hi > lo:
            result[:, lo - first:hi - first] = self.audio[:, lo:hi]
        return result


def expected():
    source = Source()
    clip = Clip('a', 'stereo', 8, 0, 64, pan=-0.3, gain_db=-3)
    track = Track('t', 'Stereo', clips=(clip,), pan=0.2, gain_db=-2)
    base = Project(rate=48000, media=(Media('stereo', 'synthetic', 2, 128),),
                   tracks=(track,))
    cases = [
        ('stereo-balance', base),
        ('stereo-downmix', replace(base, tracks=(replace(track, mono=True),))),
        ('muted', replace(base, tracks=(replace(track, mute=True),))),
        ('solo-overrides-mute', replace(base, tracks=(
            replace(track, solo=True, mute=True),
            Track('other', 'Not solo', clips=(clip,)),))),
        ('bus-master', replace(base, tracks=(replace(track, bus='b'),),
                              buses=(Bus('b', 'Bus', gain_db=-4, pan=-0.25),),
                              master_gain_db=-5)),
        ('muted-bus', replace(base, tracks=(replace(track, bus='b'),),
                             buses=(Bus('b', 'Muted', mute=True),))),
        ('crossfade', replace(base, tracks=(replace(track, clips=(
            replace(clip, length=32, xfade_out=16),
            replace(clip, id='b', start=40, offset=32, length=32,
                    xfade_in=16))),))),
        ('muted-neighbor', replace(base, tracks=(replace(track, clips=(
            replace(clip, length=32, muted=True),
            replace(clip, id='b', start=40, offset=32, length=32))),))),
    ]
    return {'source': source.audio.tolist(), 'rate': 48000, 'cases': [
        {'name': name, 'state': state.to_dict(), 'windows': [
            {'first': first, 'samples': mixer.mix(state, source, first, count).tolist()}
            for first, count in [(0, 90), (7, 17), (31, 23), (65, 25)]]}
        for name, state in cases]}


if __name__ == '__main__':
    (ROOT / 'playback-cases.json').write_text(json.dumps(expected(), indent=2) + '\n')
