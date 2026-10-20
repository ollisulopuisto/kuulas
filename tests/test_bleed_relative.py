"""The bleed-compensated decision on synthetic level grids: 3 to 4 mics, a
constant bleed offset per pair, one speaker at a time, occasional laughter."""

import numpy as np
import pytest

from kuulas import bleed_relative as br

HOPS = 6000  # 2 minutes of 20 ms hops
FLOOR = 20.0
OWN = 62.0


def make(mics=4, seed=3, laughter=True):
    """``(db, valid, truth_on, offsets)``: mic i hears mic j ``offsets[i][j]``
    dB below j's own level (-8 to -16)."""
    rng = np.random.default_rng(seed)
    offsets = -rng.uniform(8, 16, (mics, mics))
    np.fill_diagonal(offsets, 0.0)
    truth = np.zeros((mics, HOPS), dtype=bool)
    pos = 0
    while pos < HOPS:
        who = int(rng.integers(mics))
        end = min(HOPS, pos + int(rng.integers(40, 200)))
        truth[who, pos:end] = True
        pos = end + int(rng.integers(5, 40))
    loud = np.zeros(mics)  # own level of each mic per hop
    own = np.full((mics, HOPS), -200.0)
    for i in range(mics):
        own[i, truth[i]] = OWN + rng.normal(0, 2.0, truth[i].sum())
    if laughter:
        for _ in range(8):
            i = int(rng.integers(mics))
            a = int(rng.integers(HOPS - 30))
            truth[i, a:a + 15] = True
            own[i, a:a + 15] = OWN + 10 + rng.normal(0, 1.0, 15)
    del loud
    db = np.zeros((mics, HOPS))
    for i in range(mics):
        power = 10 ** (FLOOR / 10) * np.ones(HOPS)
        power = power * 10 ** (rng.normal(0, 0.5, HOPS) / 10)
        for j in range(mics):
            level = own[j] if i == j else own[j] + offsets[i, j]
            power = power + 10 ** (level / 10)
        db[i] = 10 * np.log10(power)
    return db, np.ones((mics, HOPS), dtype=bool), truth, offsets


def f1(guess, truth):
    hit = (guess & truth).sum()
    p = hit / max(1, guess.sum())
    r = hit / max(1, truth.sum())
    return 2 * p * r / (p + r) if p + r else 0.0


def test_offsets_are_recovered_from_the_hand_mutes():
    db, valid, truth, offsets = make(laughter=False)
    got = br.estimate_offsets(db, valid, ~truth)
    off_diag = ~np.eye(4, dtype=bool)
    assert np.abs(got - offsets)[off_diag].max() < 1.5
    assert (np.diag(got) == 0).all()


def test_a_pair_without_evidence_gets_the_median_of_the_others():
    db, valid, truth, _ = make(mics=3, laughter=False)
    muted = ~truth
    muted[0, :] = False  # mic 0 never muted: it has no pair of its own
    got = br.estimate_offsets(db, valid, muted)
    assert np.isfinite(got).all()
    assert -20 < got[0, 1] < -4


def test_nothing_known_falls_back_to_the_measured_median():
    db, valid, _truth, _ = make(mics=3)
    got = br.estimate_offsets(db, valid, np.zeros_like(valid))
    assert got[0, 1] == br.FALLBACK_OFFSET_DB


@pytest.mark.parametrize("mics", [3, 4])
def test_the_compensated_method_finds_the_speaker_and_a_threshold_cannot(mics):
    db, valid, truth, _ = make(mics=mics)
    offsets = br.estimate_offsets(db, valid, ~truth, window=np.arange(HOPS) < HOPS // 2)
    on = br.speaking(db, valid, offsets, presence_db=12.0)
    floor = br.floors(db, valid)
    threshold = valid & (db > floor[:, None] + 12.0)
    assert f1(on, truth) > 0.9
    # Every mic hears everybody 8 to 16 dB under the speaker, far over
    # floor + 12: the absolute rule leaves nearly everything open.
    assert f1(threshold, truth) < 0.6


def test_laughter_into_one_mic_opens_that_mic():
    db, valid, truth, _ = make()
    offsets = br.estimate_offsets(db, valid, ~truth)
    on = br.speaking(db, valid, offsets, presence_db=12.0)
    assert f1(on, truth) > 0.9


def test_two_people_talking_at_once_both_stay_open():
    db, valid, truth, _ = make(mics=3, laughter=False)
    offsets = br.estimate_offsets(db, valid, ~truth)
    both = db.copy()
    # hops 100..140: mics 0 and 1 both speak at the same loudness
    for i in (0, 1):
        both[i, 100:140] = OWN
    both[2, 100:140] = OWN - 12
    on = br.speaking(both, valid, offsets, presence_db=12.0)
    assert on[0, 100:140].all()
    assert on[1, 100:140].all()
    assert not on[2, 100:140].any()


def test_hops_outside_valid_are_not_speaking():
    db, valid, truth, _ = make(mics=3)
    offsets = br.estimate_offsets(db, valid, ~truth)
    valid = valid.copy()
    valid[0, :100] = False
    assert not br.speaking(db, valid, offsets, presence_db=12.0)[0, :100].any()
