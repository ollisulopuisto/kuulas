"""record_take, several channels (WP12b): pure decisions, no recorder."""

from datetime import UTC, datetime

from kuulas import record_take as rt

WHEN = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


def sidecar(**more):
    segs = [{"segment": 1, "start_frame": 0, "start_flicks": 0,
             "files": {"Host": {"file": "Take 1-Host.wav", "frames": 96000},
                       "Guest": {"file": "Take 1-Guest.wav", "frames": 90000}}},
            {"segment": 2, "start_frame": 100000, "start_flicks": 0,
             "files": {"Host": {"file": "Take 1-Host~2.wav", "frames": 5000},
                       "Guest": {"file": "Take 1-Guest~2.wav", "frames": 0}}}]
    return {"format": 1, "take": "Take 1", "state": "stopped", "rate": 48000,
            "channels": [{"channel": 1, "name": "Host"}, {"channel": 3, "name": "Guest"}],
            "segments": segs, "frames": 105000, "gaps": [], "dropouts": [],
            "overflows": 0, "worker_restarts": 0, **more}


def test_each_channel_has_its_own_clips_by_device_channel_number():
    snap = sidecar()
    host = rt.clip_plan(snap, at=1000, channel=1)
    guest = rt.clip_plan(snap, at=1000, channel=3)
    assert [(p.file, p.start) for p in host] == [("Take 1-Host.wav", 1000),
                                                 ("Take 1-Host~2.wav", 101000)]
    assert [(p.file, p.start) for p in guest] == [("Take 1-Guest.wav", 1000)]


def test_a_channel_the_take_never_had_makes_no_clips():
    assert rt.clip_plan(sidecar(), at=0, channel=2) == []


def test_without_a_channel_the_first_one_is_planned_as_before():
    assert rt.clip_plan(sidecar(), at=0)[0].file == "Take 1-Host.wav"


def test_preroll_trims_every_channel_the_same():
    snap = sidecar(preroll_frames=48000)
    assert [p.offset for p in rt.clip_plan(snap, at=10000, channel=1)] == [38000, 0]
    assert [p.offset for p in rt.clip_plan(snap, at=10000, channel=3)] == [38000]


def test_channel_names_in_one_take_are_unique_even_in_another_case():
    assert rt.unique_channel_names(["Host", "host", "Guest", "Host"]) == [
        "Host", "host 2", "Guest", "Host 3"]


def test_unique_channel_names_stay_within_the_recorders_limit():
    names = rt.unique_channel_names(["a" * 40, "a" * 40])
    assert len(names[1]) <= 80
    assert names[0] != names[1]


def test_summary_lists_the_channels_that_failed():
    snap = sidecar(failed_channels=[{"name": "Guest", "at_frame": 9, "text": "x"}])
    assert rt.summary(snap)["failed_channels"] == ["Guest"]
    assert rt.summary(sidecar())["failed_channels"] == []


def test_a_plan_with_lanes_round_trips(tmp_path):
    lanes = (rt.Lane(channel=1, name="Host", track_id="t1", track_name="Host"),
             rt.Lane(channel=3, name="Guest", track_id=None, track_name="Guest"))
    plan = rt.TakePlan(take="Take 2", at=480, track_id="t1", track_name="Host",
                       channel=1, lanes=lanes)
    rt.write_plan(tmp_path, plan)
    assert rt.read_plan(tmp_path, "Take 2") == plan


def test_an_old_plan_is_one_lane():
    plan = rt.TakePlan(take="Take 2", at=0, track_id="t1", track_name="Olli", channel=2)
    assert plan.all_lanes == (rt.Lane(channel=2, name="Olli", track_id="t1",
                                      track_name="Olli"),)


def test_next_take_avoids_the_files_of_every_channel():
    # "take 2-guest.wav" is in the way on a case-insensitive disk.
    assert rt.next_take(["take 2-guest.wav"], ["Host", "Guest"], WHEN) == "Take 3"


def test_the_failed_channel_is_a_loud_notice_naming_it():
    notice = rt.event_notice({"event": "warning", "key": "channel_failed",
                              "name": "Guest"}, 48000)
    assert notice == {"key": "record.event.channel_failed", "level": "alarm",
                      "params": {"name": "Guest"}}


def test_file_names_come_from_the_recorders_one_function():
    from kuulas_recorder.names import segment_file  # noqa: PLC0415

    assert rt.segment_file is segment_file
