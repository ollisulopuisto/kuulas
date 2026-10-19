"""record_take: the editor's pure decisions about a recorder take (WP12a part B)."""

from datetime import UTC, datetime

import pytest

from kuulas import record_take as rt

WHEN = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


def sidecar(state="stopped", segments=None, **more):
    return {
        "format": 1, "take": "Take 1", "state": state, "rate": 48000,
        "channels": [{"channel": 1, "name": "Olli"}],
        "segments": segments if segments is not None else [
            {"segment": 1, "start_frame": 0, "start_flicks": 0, "end": "stopped",
             "files": {"Olli": {"file": "Take 1-Olli.wav", "frames": 96000}}}],
        "frames": 96000, "gaps": [], "dropouts": [], "overflows": 0,
        "worker_restarts": 0, **more,
    }


# -- names ------------------------------------------------------------------------


def test_channel_name_keeps_letters_of_any_script():
    assert rt.channel_name("Äänittäjä Ö") == "Äänittäjä Ö"


def test_channel_name_drops_what_the_recorder_refuses():
    assert rt.channel_name("Olli/Guest: #1~") == "OlliGuest 1"


def test_channel_name_of_nothing_usable_is_a_fallback():
    assert rt.channel_name("  ///  ") == rt.FALLBACK_CHANNEL
    assert rt.channel_name("") == rt.FALLBACK_CHANNEL


def test_channel_name_is_cut_and_never_ends_in_space_or_dot():
    name = rt.channel_name("a" * 39 + " ." + "b" * 50)
    assert len(name) <= rt.MAX_CHANNEL
    assert not name.endswith((" ", "."))


def test_next_take_counts_past_the_takes_in_the_folder():
    assert rt.next_take(["Take 1.take.json", "Take 4-Olli.wav", "notes.txt"],
                        "Olli", WHEN) == "Take 5"


def test_next_take_starts_at_one():
    assert rt.next_take([], "Olli", WHEN) == "Take 1"


def test_next_take_never_reuses_a_file_name_in_another_case():
    # "take 2-olli.wav" is in the way on a case-insensitive disk; Take 3 is free.
    assert rt.next_take(["take 2-olli.wav"], "Olli", WHEN) == "Take 3"


def test_takes_in_lists_sidecars_only():
    assert rt.takes_in(["Take 2.take.json", "Take 2-Olli.wav",
                        "Take 1.take.json", "x.json"]) == ["Take 1", "Take 2"]


# -- when a take is ready ---------------------------------------------------------


@pytest.mark.parametrize(("state", "running", "want"), [
    ("stopped", False, "import"),
    ("interrupted", False, "import"),
    ("recording", False, "repair"),
    ("recording", True, "running"),
    ("stopped", True, "import"),
    ("weird", False, None),
])
def test_readiness(state, running, want):
    assert rt.readiness(sidecar(state), running=running) == want


# -- clips --------------------------------------------------------------------------


def test_one_segment_is_one_clip_at_the_start_frame():
    plans = rt.clip_plan(sidecar(), at=4800)
    assert plans == [rt.ClipPlan(file="Take 1-Olli.wav", start=4800, segment=1)]


def seg(n, start, file, frames):
    return {"segment": n, "start_frame": start,
            "files": {"Olli": {"file": file, "frames": frames}}}


def test_segments_land_at_their_place_on_the_take_clock():
    segs = [seg(1, 0, "a.wav", 100), seg(2, 160, "b.wav", 50)]
    plans = rt.clip_plan(sidecar(segments=segs), at=1000)
    assert [(p.file, p.start) for p in plans] == [("a.wav", 1000), ("b.wav", 1160)]


def test_empty_and_unplaced_files_make_no_clip():
    segs = [seg(1, 0, "a.wav", 0), seg(2, None, "b.wav", 9), seg(3, 20, "c.wav", 9)]
    assert [p.file for p in rt.clip_plan(sidecar(segments=segs), at=0)] == ["c.wav"]


def test_a_file_whose_frames_the_snapshot_lags_on_still_counts_when_it_exists():
    # After a crash the snapshot may say 0 frames for a file the repair filled;
    # the caller passes what is on disk.
    segs = [{"segment": 1, "start_frame": 0,
             "files": {"Olli": {"file": "a.wav", "frames": 0}}}]
    plans = rt.clip_plan(sidecar(segments=segs), at=0, on_disk={"a.wav"})
    assert [p.file for p in plans] == ["a.wav"]


def test_a_negative_start_is_refused():
    with pytest.raises(ValueError, match="at"):
        rt.clip_plan(sidecar(), at=-1)


def test_summary_names_what_went_wrong():
    s = rt.summary(sidecar("interrupted", gaps=[{"at_frame": 1, "frames": 4800,
                                                "reason": "worker_restart"}],
                           dropouts=[{"at_frame": 3, "frames": 2}], overflows=2,
                           worker_restarts=1))
    assert s == {"interrupted": True, "gaps": 1, "gap_frames": 4800, "dropouts": 1,
                 "overflows": 2, "worker_restarts": 1, "failed_channels": [],
                 "frames": 96000}


# -- the editor's plan file ---------------------------------------------------------


def test_plan_round_trip(tmp_path):
    plan = rt.TakePlan(take="Take 2", at=480, track_id="t1", track_name="Olli",
                       channel=1, device={"index": 3, "name": "Scarlett"})
    rt.write_plan(tmp_path, plan)
    assert rt.read_plan(tmp_path, "Take 2") == plan
    assert (tmp_path / "Take 2.editor.json").exists()


def test_a_missing_or_broken_plan_is_none(tmp_path):
    assert rt.read_plan(tmp_path, "Take 9") is None
    (tmp_path / "Take 9.editor.json").write_text("{not json")
    assert rt.read_plan(tmp_path, "Take 9") is None


# -- events into messages -------------------------------------------------------------


@pytest.mark.parametrize(("event", "key"), [
    ({"event": "warning", "key": "disk_low", "seconds_left": 600},
     "record.event.disk_low"),
    ({"event": "warning", "key": "input_overflow", "count": 3},
     "record.event.input_overflow"),
    ({"event": "warning", "key": "dropout", "frames": 4800}, "record.event.dropout"),
    ({"event": "device_lost", "device": {"name": "Mic"}}, "record.event.device_lost"),
    ({"event": "device_back", "device": {"name": "Mic"}}, "record.event.device_back"),
    ({"event": "gap", "frames": 9600}, "record.event.gap"),
    ({"event": "worker_restarted", "restarts": 1}, "record.event.worker_restarted"),
    ({"event": "error", "key": "disk_full"}, "record.event.disk_full"),
    ({"event": "error", "key": "worker_keeps_failing"},
     "record.event.worker_keeps_failing"),
    ({"event": "error", "key": "something_new"}, "record.event.error"),
])
def test_event_notice_keys(event, key):
    got = rt.event_notice(event, rate=48000)
    assert got is not None
    assert got["key"] == key


def test_event_notice_params_are_human_units():
    assert rt.event_notice({"event": "warning", "key": "disk_low", "seconds_left": 600},
                           rate=48000)["params"] == {"minutes": 10}
    assert rt.event_notice({"event": "gap", "frames": 24000},
                           rate=48000)["params"] == {"seconds": "0.5"}
    assert rt.event_notice({"event": "device_lost", "device": {"name": "Mic"}},
                           rate=48000)["params"] == {"device": "Mic"}


def test_level_and_started_are_not_notices():
    assert rt.event_notice({"event": "level"}, rate=48000) is None
    assert rt.event_notice({"event": "started"}, rate=48000) is None
    assert rt.event_notice({"event": "stopped"}, rate=48000) is None


def test_warnings_are_loud_and_device_lost_is_an_alarm():
    assert rt.event_notice({"event": "device_lost", "device": {}},
                           rate=48000)["level"] == "alarm"
    assert rt.event_notice({"event": "device_back", "device": {}},
                           rate=48000)["level"] == "info"
    assert rt.event_notice({"event": "warning", "key": "disk_low", "seconds_left": 60},
                           rate=48000)["level"] == "warning"


# -- error keys ------------------------------------------------------------------------


def test_recorder_error_keys_map_to_catalog_keys():
    assert rt.error_key("device_rate_mismatch") == "error.record.device_rate_mismatch"
    assert rt.error_key("timeout") == "error.record.timeout"
    assert rt.error_key("never_heard_of") == "error.record.other"


def test_every_mapped_error_key_is_in_both_catalogs():
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    root = Path(rt.__file__).parent / "locales"
    for lang in ("en", "fi"):
        catalog = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
        for key in rt.RECORDER_ERRORS:
            assert f"error.record.{key}" in catalog, (lang, key)
        for key in rt.EVENT_KEYS:
            assert key in catalog, (lang, key)


def test_the_editor_uses_only_the_recorders_client():
    """docs/RECORDER.md: the editor imports ``kuulas_recorder.client``, nothing else."""
    import ast  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    for path in sorted((Path(rt.__file__).parent).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split(".")[0] == "kuulas_recorder":
                    assert name == "kuulas_recorder.client", f"{path.name} imports {name}"


# -- pre-roll (WP12c) --------------------------------------------------------------------


def test_the_preroll_ends_where_record_was_pressed():
    plans = rt.clip_plan(sidecar(preroll_frames=48000), at=96000)
    assert plans == [rt.ClipPlan(file="Take 1-Olli.wav", start=48000, segment=1)]


def test_preroll_before_the_timeline_start_is_trimmed_from_the_clip_head():
    plans = rt.clip_plan(sidecar(preroll_frames=48000), at=10000)
    assert [(p.start, p.offset) for p in plans] == [(0, 38000)]


def test_later_segments_keep_their_place_relative_to_record():
    segs = [seg(1, 0, "a.wav", 90000), seg(2, 100000, "b.wav", 50000)]
    plans = rt.clip_plan(sidecar(segments=segs, preroll_frames=48000), at=10000)
    assert [(p.file, p.start, p.offset) for p in plans] == [
        ("a.wav", 0, 38000), ("b.wav", 62000, 0)]


def test_a_segment_wholly_inside_the_trimmed_head_makes_no_clip():
    segs = [seg(1, 0, "a.wav", 20000), seg(2, 25000, "b.wav", 60000)]
    plans = rt.clip_plan(sidecar(segments=segs, preroll_frames=48000), at=0)
    assert [(p.file, p.start, p.offset) for p in plans] == [("b.wav", 0, 23000)]


def test_a_take_without_preroll_is_placed_as_before():
    assert rt.clip_plan(sidecar(preroll_frames=0), at=500)[0].start == 500
    assert rt.clip_plan(sidecar(), at=500)[0].offset == 0


def test_a_lost_listener_is_a_notice_a_chosen_disarm_is_not():
    lost = rt.event_notice({"event": "disarmed", "reason": "device_lost"}, rate=48000)
    assert lost["key"] == "record.event.disarmed"
    assert lost["level"] == "warning"
    own = {"event": "disarmed", "reason": "disarmed"}
    assert rt.event_notice(own, rate=48000) is None
    assert rt.event_notice({"event": "armed"}, rate=48000) is None
