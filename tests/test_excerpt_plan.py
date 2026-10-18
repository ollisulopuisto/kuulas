"""The excerpt plan: which parts of each media file travel, plus handles.

An edit sent for review or copied into another project carries only the
stretches the edit uses, each widened by a handle on both sides. All times
are seconds.
"""

from kuulas.excerpt_plan import covers, excerpt_ranges, savings, total_seconds

# -- excerpt_ranges ---------------------------------------------------------


def test_a_used_range_is_widened_by_the_handle_on_both_sides():
    # The default handle is 2.0 s.
    assert excerpt_ranges([("m1", 10.0, 20.0)]) == {"m1": ((8.0, 22.0),)}


def test_the_handle_can_be_changed():
    assert excerpt_ranges([("m1", 10.0, 20.0)], handle=0.0) == {
        "m1": ((10.0, 20.0),)
    }
    assert excerpt_ranges([("m1", 10.0, 20.0)], handle=5.5) == {
        "m1": ((4.5, 25.5),)
    }


def test_the_widened_start_is_not_below_zero():
    assert excerpt_ranges([("m1", 1.0, 5.0)]) == {"m1": ((0.0, 7.0),)}
    assert excerpt_ranges([("m1", 0.0, 5.0)]) == {"m1": ((0.0, 7.0),)}


def test_the_widened_end_is_not_above_the_media_duration():
    plan = excerpt_ranges([("m1", 95.0, 100.0)], duration={"m1": 100.0})
    assert plan == {"m1": ((93.0, 100.0),)}


def test_a_media_the_duration_does_not_give_is_not_clamped():
    # m1 has no duration, m2 does: only m2's end is clamped, and duration
    # None clamps nothing.
    plan = excerpt_ranges(
        [("m1", 95.0, 100.0), ("m2", 95.0, 100.0)],
        duration={"m2": 100.0},
    )
    assert plan == {"m1": ((93.0, 102.0),), "m2": ((93.0, 100.0),)}
    assert excerpt_ranges([("m1", 95.0, 100.0)]) == {"m1": ((93.0, 102.0),)}


def test_a_use_past_the_media_end_is_dropped():
    # The clamp empties the widened range — its end is the media's
    # duration, its start lies past it — so nothing of this media travels
    # and the media is absent, not present with no ranges.
    plan = excerpt_ranges([("m1", 150.0, 160.0)], duration={"m1": 100.0})
    assert plan == {}


def test_overlapping_ranges_merge():
    plan = excerpt_ranges([("m1", 10.0, 20.0), ("m1", 18.0, 30.0)])
    assert plan == {"m1": ((8.0, 32.0),)}


def test_a_range_inside_another_is_swept_up():
    plan = excerpt_ranges([("m1", 10.0, 90.0), ("m1", 40.0, 50.0)])
    assert plan == {"m1": ((8.0, 92.0),)}


def test_touching_ranges_merge():
    # 20 + handle reaches 24 - handle: they meet, and meeting is one.
    plan = excerpt_ranges([("m1", 12.0, 20.0), ("m1", 24.0, 30.0)])
    assert plan == {"m1": ((10.0, 32.0),)}


def test_a_gap_stays_two_ranges():
    plan = excerpt_ranges([("m1", 10.0, 20.0), ("m1", 30.0, 40.0)])
    assert plan == {"m1": ((8.0, 22.0), (28.0, 42.0))}


def test_ranges_on_separate_media_stay_apart():
    # The two stretches overlap in time, but they are parts of different
    # files: no cross-media merge.
    plan = excerpt_ranges([("m1", 10.0, 20.0), ("m2", 15.0, 25.0)])
    assert plan == {"m1": ((8.0, 22.0),), "m2": ((13.0, 27.0),)}


def test_empty_and_reversed_ranges_are_ignored():
    # A zero-length use is dropped before the widening: it plays nothing,
    # and a handle is context around played audio, not a way to conjure a
    # stretch out of nothing. A reversed range is malformed the same way.
    plan = excerpt_ranges([
        ("m1", 5.0, 5.0),
        ("m1", 7.0, 3.0),
        ("m1", 10.0, 12.0),
    ])
    assert plan == {"m1": ((8.0, 14.0),)}


def test_the_same_uses_in_any_order_give_the_same_plan():
    a = [("m1", 10.0, 20.0), ("m2", 5.0, 8.0), ("m1", 30.0, 40.0)]
    b = [("m1", 30.0, 40.0), ("m2", 5.0, 8.0), ("m1", 10.0, 20.0)]
    assert excerpt_ranges(a) == excerpt_ranges(b)
    # The keys are sorted, so the plan also serialises the same way.
    assert list(excerpt_ranges(a)) == ["m1", "m2"]


# -- total_seconds ----------------------------------------------------------


def test_total_seconds_sums_all_ranges_of_all_media():
    plan = {"m1": ((8.0, 22.0), (28.0, 42.0)), "m2": ((100.0, 110.0),)}
    assert total_seconds(plan) == 14.0 + 14.0 + 10.0


def test_total_seconds_of_an_empty_plan_is_zero():
    assert total_seconds({}) == 0


# -- savings ----------------------------------------------------------------


def test_savings_numbers():
    duration = {"m1": 100.0, "m2": 100.0}
    # Half of m1 travels, m2 not at all: a quarter of the media carries,
    # so three quarters are saved.
    assert savings({"m1": ((0.0, 50.0),)}, duration) == 0.75
    # Everything travels: nothing saved.
    full = {"m1": ((0.0, 100.0),), "m2": ((0.0, 100.0),)}
    assert savings(full, duration) == 0.0
    # Nothing travels: all saved.
    assert savings({}, duration) == 1.0


def test_a_media_the_plan_does_not_carry_is_fully_saved():
    # m2 never travels, and its whole duration counts toward the total:
    # half of the media is saved.
    plan = {"m1": ((0.0, 100.0),)}
    assert savings(plan, {"m1": 100.0, "m2": 100.0}) == 0.5


def test_carried_seconds_are_capped_at_the_media_duration():
    # A plan built without durations can overshoot a file's end; carrying
    # a whole file twice is still carrying it once. Without the cap this
    # would say 0.25 while the caller ships all of m1.
    plan = {"m1": ((0.0, 150.0),)}
    assert savings(plan, {"m1": 100.0, "m2": 100.0}) == 0.5


def test_a_plan_media_without_a_duration_is_outside_the_accounting():
    # The total is the durations given; m2 travels but is not of it.
    plan = {"m1": ((0.0, 50.0),), "m2": ((0.0, 10.0),)}
    assert savings(plan, {"m1": 100.0}) == 0.5


def test_zero_total_duration_is_zero_savings():
    assert savings({"m1": ((0.0, 10.0),)}, {}) == 0
    assert savings({}, {"m1": 0.0}) == 0


# -- covers -----------------------------------------------------------------


def test_covers_at_the_edges():
    plan = {"m1": ((8.0, 22.0),)}
    # The whole stretch inside one range, edges included.
    assert covers(plan, "m1", 8.0, 22.0) is True
    assert covers(plan, "m1", 10.0, 20.0) is True
    # Just outside on either side: not carried.
    assert covers(plan, "m1", 7.9, 22.0) is False
    assert covers(plan, "m1", 8.0, 22.1) is False


def test_a_media_the_plan_does_not_have_covers_nothing():
    assert covers({}, "m1", 0.0, 1.0) is False
    assert covers({"m2": ((0.0, 10.0),)}, "m1", 0.0, 1.0) is False


def test_two_ranges_that_meet_do_not_cover_the_whole_stretch():
    # Each part lies in its own range, but no single range spans it all.
    # (A plan built by excerpt_ranges would have merged these two.)
    plan = {"m1": ((8.0, 22.0), (22.0, 30.0))}
    assert covers(plan, "m1", 10.0, 25.0) is False
    assert covers(plan, "m1", 10.0, 20.0) is True
