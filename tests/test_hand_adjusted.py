"""Was a speech level adjusted by hand, and the balance cap for it."""

from kuulas.hand_adjusted import balance_cap, hand_adjusted


def track(kind="speech", mute=False, gain_db=0.0, clips=None):
    return {"kind": kind, "mute": mute, "gain_db": gain_db,
            "clips": clips or []}


def clip(gain_db=0.0, muted=False, envelope=None):
    return {"gain_db": gain_db, "muted": muted, "envelope": envelope or []}


def test_empty_project_is_not_adjusted():
    assert hand_adjusted([]) is False


def test_untouched_project_is_not_adjusted():
    assert hand_adjusted([track()]) is False
    assert hand_adjusted([track(kind="music")]) is False


def test_track_gain_above_threshold_is_adjusted():
    assert hand_adjusted([track(gain_db=0.06)]) is True
    assert hand_adjusted([track(gain_db=-0.06)]) is True


def test_track_gain_at_or_below_threshold_is_not_adjusted():
    assert hand_adjusted([track(gain_db=0.05)]) is False
    assert hand_adjusted([track(gain_db=0.01)]) is False


def test_clip_gain_above_threshold_is_adjusted():
    assert hand_adjusted([track(clips=[clip(gain_db=0.06)])]) is True
    assert hand_adjusted([track(clips=[clip(gain_db=-0.06)])]) is True


def test_clip_gain_at_or_below_threshold_is_not_adjusted():
    assert hand_adjusted([track(clips=[clip(gain_db=0.05)])]) is False


def test_envelope_point_above_threshold_is_adjusted():
    assert hand_adjusted([track(clips=[clip(envelope=[[0, 0.06]])])]) is True
    assert hand_adjusted([track(clips=[clip(envelope=[[0, -0.06]])])]) is True


def test_envelope_point_at_or_below_threshold_is_not_adjusted():
    assert hand_adjusted([track(clips=[clip(envelope=[[0, 0.05]])])]) is False


def test_muted_speech_track_never_counts():
    assert hand_adjusted([track(mute=True, gain_db=1.0)]) is False
    assert hand_adjusted([track(mute=True, clips=[clip(gain_db=1.0)])]) is False
    assert hand_adjusted([track(mute=True, clips=[clip(envelope=[[0, 1.0]])])]) is False


def test_muted_clip_never_counts():
    assert hand_adjusted([track(clips=[clip(gain_db=1.0, muted=True)])]) is False
    assert hand_adjusted([track(clips=[clip(envelope=[[0, 1.0]], muted=True)])]) is False


def test_music_gain_is_ignored():
    assert hand_adjusted([track(kind="music", gain_db=1.0)]) is False
    assert hand_adjusted([track(kind="music", clips=[clip(gain_db=1.0)])]) is False
    assert hand_adjusted(
        [track(kind="music", clips=[clip(envelope=[[0, 1.0]])])]
    ) is False


def test_missing_keys_are_defaults():
    assert hand_adjusted([{}]) is False
    assert hand_adjusted([{"kind": "speech"}]) is False
    assert hand_adjusted([{"clips": [{}]}]) is False


def test_only_non_muted_speech_counts_with_mixed_project():
    tracks = [
        track(kind="music", gain_db=1.0),
        track(mute=True, gain_db=1.0),
        track(clips=[clip(gain_db=1.0, muted=True)]),
        track(clips=[clip(gain_db=0.06)]),
    ]
    assert hand_adjusted(tracks) is True


def test_balance_cap_keep_wins_over_everything():
    assert balance_cap([], keep=True) == 0.0
    assert balance_cap([track(gain_db=1.0)], keep=True) == 0.0
    assert balance_cap([track(kind="music", gain_db=100.0)], keep=True) == 0.0


def test_balance_cap_hand_adjusted_is_2_5():
    assert balance_cap([track(gain_db=0.06)]) == 2.5
    assert balance_cap([track(clips=[clip(gain_db=0.06)])]) == 2.5
    assert balance_cap([track(clips=[clip(envelope=[[0, 0.06]])])]) == 2.5


def test_balance_cap_untouched_is_6_0():
    assert balance_cap([]) == 6.0
    assert balance_cap([track()]) == 6.0
    assert balance_cap([track(kind="music")]) == 6.0


def test_inputs_are_not_mutated():
    tracks = [track(gain_db=0.06, clips=[clip(gain_db=0.06, envelope=[[0, 0.06]])])]
    before = [dict(t, clips=[dict(c) for c in t["clips"]]) for t in tracks]
    hand_adjusted(tracks)
    balance_cap(tracks)
    assert tracks == before


def test_threshold_is_strictly_greater_than_0_05():
    assert hand_adjusted([track(gain_db=0.0500001)]) is True
    assert hand_adjusted([track(gain_db=0.05)]) is False
