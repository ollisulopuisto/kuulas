"""The live take transcription (owner, 2026-11-01): while a take records, the
newest few seconds of each lane go to the speech engine and the words land in a
store the page can search DURING the take (follow-up questions: "did I say this
already"). These tests cover the pure parts: which audio to transcribe next,
how chunk words merge without duplicates, and the searchable store.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from kuulas.clock import FLICKS
from kuulas.live_transcribe import (
    MAX_LANE_FAILURES,
    LiveTranscriber,
    LiveTranscribeRunner,
    LiveTranscribeSidecar,
    LiveTranscript,
    chunk_window,
    flushed_frames,
    merge_words,
)
from kuulas_recorder.wavfile import ProgressiveWav, float_to_pcm24

RATE = 48000

flushed_levels = [0]  # the fake WAV length the scripted sidecar tests mutate


class TestChunkWindow:
    def test_nothing_flushed_nothing_to_do(self):
        assert chunk_window(flushed=0, done=0, rate=RATE) is None

    def test_waits_for_a_full_chunk(self):
        assert chunk_window(flushed=3 * RATE, done=0, rate=RATE,
                            chunk_s=5) is None

    def test_first_chunk_once_five_seconds_flushed(self):
        assert chunk_window(flushed=5 * RATE, done=0, rate=RATE,
                            chunk_s=5) == (0, 5 * RATE)

    def test_advances_by_chunks(self):
        assert chunk_window(flushed=12 * RATE, done=5 * RATE, rate=RATE, chunk_s=5) == (
            5 * RATE, 10 * RATE)

    def test_last_bit_waits_for_the_take_to_grow(self):
        # 10.4 s flushed: the second chunk has not filled yet.
        assert chunk_window(flushed=int(10.4 * RATE), done=10 * RATE,
                            rate=RATE, chunk_s=5) is None

    def test_catching_up_after_a_pause_stays_sequential(self):
        # The engine paused and 40 s flushed meanwhile: still the next chunk, in order.
        assert chunk_window(flushed=40 * RATE, done=5 * RATE, rate=RATE, chunk_s=5) == (
            5 * RATE, 10 * RATE)


class TestMergeWords:
    def test_appends_new_words(self):
        old = [{"w": "hei", "s": 100, "e": 200, "spk": ""}]
        new = [{"w": "maailma", "s": 300, "e": 400, "spk": ""}]
        # `since` is the new chunk's start: everything before it is kept as read.
        assert merge_words(old, new, since=300) == old + new

    def test_overlap_replaces_from_the_chunk_start(self):
        # A re-read of the 0.5 s context replaces old words at/after `since`.
        old = [{"w": "hei", "s": 100, "e": 200, "spk": ""},
               {"w": "huonosti", "s": 250, "e": 350, "spk": ""}]
        new = [{"w": "hyvin", "s": 250, "e": 350, "spk": ""}]
        assert merge_words(old, new, since=250) == [
            {"w": "hei", "s": 100, "e": 200, "spk": ""},
            {"w": "hyvin", "s": 250, "e": 350, "spk": ""}]

    def test_empty_new_keeps_old_before_since(self):
        old = [{"w": "hei", "s": 100, "e": 200, "spk": ""}]
        assert merge_words(old, [], since=300) == old
        assert merge_words(old, [], since=50) == []


class TestLiveTranscript:
    def test_search_finds_words_case_insensitively(self):
        live = LiveTranscript()
        live.add("track-1", [{"w": "Kuulas", "s": 10, "e": 20, "spk": ""},
                             {"w": "tallentaa", "s": 30, "e": 40, "spk": ""}], since=0)
        hits = live.search("kuulas")
        assert len(hits) == 1
        assert hits[0]["w"] == "Kuulas"
        assert hits[0]["track"] == "track-1"

    def test_search_matches_a_phrase_across_word_boundaries(self):
        live = LiveTranscript()
        live.add("t", [{"w": "tämä", "s": 10, "e": 20, "spk": ""},
                       {"w": "on", "s": 20, "e": 30, "spk": ""},
                       {"w": "testi", "s": 30, "e": 40, "spk": ""}], since=0)
        assert [h["w"] for h in live.search("on testi")] == ["on", "testi"]
        assert live.search("ei ole") == []

    def test_search_is_per_take_not_per_chunk(self):
        live = LiveTranscript()
        live.add("t", [{"w": "ensin", "s": 10, "e": 20, "spk": ""}], since=0)
        live.add("t", [{"w": "sitten", "s": 30, "e": 40, "spk": ""}], since=20)
        assert [h["w"] for h in live.search("ensin sitten")] == ["ensin", "sitten"]

    def test_replace_drops_re_read_overlap_words(self):
        live = LiveTranscript()
        live.add("t", [{"w": "huono", "s": 10, "e": 20, "spk": ""}], since=0)
        live.add("t", [{"w": "hyvä", "s": 10, "e": 20, "spk": ""}], since=10)
        assert [h["w"] for h in live.search("h")] == ["hyvä"]

    def test_tracks_do_not_mix(self):
        live = LiveTranscript()
        live.add("a", [{"w": "yksi", "s": 10, "e": 20, "spk": ""}], since=0)
        live.add("b", [{"w": "kaksi", "s": 30, "e": 40, "spk": ""}], since=0)
        assert {h["track"] for h in live.search("")} == {"a", "b"}

    def test_words_snapshot_newest_first(self):
        live = LiveTranscript()
        live.add("t", [{"w": "a", "s": 10, "e": 20, "spk": ""},
                       {"w": "b", "s": 30, "e": 40, "spk": ""}], since=0)
        assert [w["w"] for w in live.words()] == ["a", "b"]


class TestLiveTranscriber:
    """The per-lane chunk loop with a fake engine and fake audio reads."""

    def make(self, words_by_call, **kw):
        store = LiveTranscript()
        calls = []
        def engine(audio, rate):
            calls.append(len(audio))
            return words_by_call[len(calls) - 1]
        def read(start, end):
            return [0.0] * (end - start)
        live = LiveTranscriber(rate=RATE, track_id="t1", store=store,
                               engine=engine, read_frames=read, **kw)
        return live, store, calls

    def test_no_step_until_a_full_chunk(self):
        live, store, calls = self.make([])
        assert live.step(3 * RATE) is None
        assert calls == []
        assert store.words() == []

    def test_first_chunk_covers_the_first_five_seconds(self):
        live, store, calls = self.make([
            [{"word": "hei", "start": 1.0, "end": 1.5}]])
        status = live.step(6 * RATE)
        assert status == {"start": 0, "end": 5 * RATE, "words": 1}
        assert calls == [5 * RATE]  # no context before frame 0
        [w] = store.words()
        assert w["w"] == "hei"
        assert w["s"] == round(1.0 * FLICKS)

    def test_second_chunk_offsets_words_and_reads_with_context(self):
        live, store, calls = self.make(
            [[{"word": "eka", "start": 1.0, "end": 1.4}],
             [{"word": "toka", "start": 1.0, "end": 1.4}]], ctx_s=0.5)
        live.step(6 * RATE)
        status = live.step(12 * RATE)
        assert status == {"start": 5 * RATE, "end": 10 * RATE, "words": 1}
        # read from 4.5 s (0.5 s context) to 10 s
        assert calls[1] == int(5.5 * RATE)
        [_, w] = store.words()
        # word at 1.0-1.4 s inside a window that began at 4.5 s -> media time 5.5-5.9 s
        assert w["s"] == round(5.5 * FLICKS)
        assert w["e"] == round(5.9 * FLICKS)

    def test_words_ending_in_the_context_are_dropped(self):
        live, store, _ = self.make(
            [[{"word": "eka", "start": 4.0, "end": 5.0}],
             [{"word": "vanha", "start": 0.1, "end": 0.4},   # inside the 0.5 s context
              {"word": "uusi", "start": 0.6, "end": 1.0}]], ctx_s=0.5)
        live.step(6 * RATE)
        live.step(12 * RATE)
        assert [w["w"] for w in store.words()] == ["eka", "uusi"]

    def test_progress_reports_done_frames(self):
        live, _, _ = self.make([[]])
        assert live.done_frames == 0
        live.step(6 * RATE)
        assert live.done_frames == 5 * RATE


class TestFlushedFrames:
    def test_reads_the_progressive_header(self, tmp_path):

        wav = ProgressiveWav(tmp_path / "take-1.wav", RATE)
        wav.write(float_to_pcm24(np.zeros(RATE, dtype=np.float32)))
        wav.flush()
        wav.close()
        assert flushed_frames(tmp_path / "take-1.wav") == RATE

    def test_missing_file_is_zero(self, tmp_path):
        assert flushed_frames(tmp_path / "nope.wav") == 0


class TestLiveTranscribeSidecar:
    def make(self, words_by_call=None, lane_files=None):
        store = LiveTranscript()
        calls = []
        scripted = words_by_call or []
        def engine(audio, rate):
            calls.append(len(audio))
            return (scripted[len(calls) - 1]
                    if len(calls) <= len(scripted) else [])
        built = []
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take",
            lane_files=lane_files or {"t1": "take-1.wav"},
            engine_factory=lambda: built.append(1) or engine,
            store=store,
            read_frames=lambda start, end: [0.0] * (end - start),
            flushed=lambda path: flushed_levels[0])
        return sidecar, store, calls, built

    def test_waits_for_a_full_chunk_and_reports_waiting(self):
        flushed_levels[0] = 3 * RATE
        sidecar, _store, calls, _built = self.make()
        [status] = sidecar.tick()
        assert status["waiting"] is True
        assert status["done_frames"] == 0
        assert calls == []

    def test_engine_built_lazily_on_first_chunk_only(self):
        flushed_levels[0] = 3 * RATE
        sidecar, _store, _calls, built = self.make()
        sidecar.tick()
        assert built == []  # no model load while nothing is ready
        flushed_levels[0] = 6 * RATE
        [status] = sidecar.tick()
        assert built == [1]
        assert status == {"track": "t1", "start": 0, "end": 5 * RATE,
                          "words": 0, "done_frames": 5 * RATE}

    def test_engine_error_disables_the_lane_after_three_failures(self):
        flushed_levels[0] = 12 * RATE
        def bad_engine(audio, rate):
            raise RuntimeError("malli kaatui")
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=lambda: bad_engine, store=LiveTranscript(),
            read_frames=lambda s, e: [0.0] * (e - s), flushed=lambda p: 12 * RATE)
        for _ in range(MAX_LANE_FAILURES):
            [status] = sidecar.tick()
        assert status["disabled"] is True
        assert "malli kaatui" in status["error"]
        assert sidecar.tick() == []  # lane skipped from then on

    def test_two_lanes_progress_independently(self):
        flushed_levels[0] = 6 * RATE
        sidecar, _store, _calls, _built = self.make(
            lane_files={"t1": "a.wav", "t2": "b.wav"})
        statuses = sidecar.tick()
        assert {s["track"] for s in statuses} == {"t1", "t2"}
        assert all(s.get("end") == 5 * RATE for s in statuses)


class TestLiveTranscribeRunner:
    def make(self, **sidecar_kw):
        store = LiveTranscript()
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=lambda: (lambda audio, rate: []),
            store=store, read_frames=lambda s, e: [0.0] * (e - s),
            **sidecar_kw)
        published = []
        runner = LiveTranscribeRunner(sidecar, publish=published.append,
                                      min_interval_s=0.05)
        return runner, sidecar, published

    def test_poke_ticks_and_publishes(self):
        flushed = [6 * RATE]
        runner, _sidecar, published = self.make(flushed=lambda p: flushed[0])
        runner.start()
        try:
            runner.poke()
            for _ in range(100):
                if published:
                    break
                time.sleep(0.01)
            assert runner.ticks >= 1
            assert published
            assert published[0][0]["end"] == 5 * RATE
        finally:
            runner.stop()
        assert runner._thread is None

    def test_waiting_ticks_are_not_published(self):
        runner, _sidecar, published = self.make(flushed=lambda p: 3 * RATE)
        runner.start()
        try:
            runner.poke()
            time.sleep(0.3)
            assert runner.ticks >= 1
            assert published == []
        finally:
            runner.stop()

    def test_engine_errors_are_survived_and_counted(self):
        def boom(p):
            raise RuntimeError("levyvika")
        runner, sidecar, _published = self.make()
        sidecar._flushed = boom
        runner.start()
        try:
            runner.poke()
            for _ in range(100):
                if runner.errors:
                    break
                time.sleep(0.01)
            assert runner.errors >= 1
            assert runner._thread.is_alive()
        finally:
            runner.stop()


class TestFinish:
    """The take is over: the trailing partial chunk is transcribed, not lost."""

    def make(self, words_by_call):
        store = LiveTranscript()
        calls = []
        def engine(audio, rate):
            calls.append(len(audio))
            return (words_by_call[len(calls) - 1]
                    if len(calls) <= len(words_by_call) else [])
        live = LiveTranscriber(rate=RATE, track_id="t1", store=store,
                               engine=engine,
                               read_frames=lambda s, e: [0.0] * (e - s))
        return live, store

    def test_tail_after_full_chunks_is_transcribed(self):
        live, store = self.make(
            [[{"word": "eka", "start": 1.0, "end": 1.5}],
             [{"word": "loppu", "start": 1.0, "end": 1.5}]])
        live.step(6 * RATE)          # [0, 5 s)
        status = live.finish(int(6.5 * RATE))  # tail [5 s, 6.5 s)
        assert status["tail"] is True
        assert status["end"] == int(6.5 * RATE)
        assert [w["w"] for w in store.words()] == ["eka", "loppu"]
        # the tail word: 1.0 s into a window that began at 4.5 s -> 5.5 s on the clock
        assert store.words()[1]["s"] == round(5.5 * FLICKS)
        assert live.done_frames == int(6.5 * RATE)

    def test_tiny_tail_is_skipped(self):
        live, store = self.make([[{"word": "eka", "start": 1.0, "end": 1.5}]])
        live.step(6 * RATE)
        assert live.finish(int(5.1 * RATE)) is None
        assert [w["w"] for w in store.words()] == ["eka"]

    def test_sidecar_finish_transcribes_the_tail(self):
        store = LiveTranscript()
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=lambda: (lambda audio, rate: [
                {"word": "sana", "start": 1.0, "end": 1.5}]),
            store=store, read_frames=lambda s, e: [0.0] * (e - s),
            flushed=lambda p: 6 * RATE)
        sidecar.tick()            # consumes the full [0, 5 s) chunk
        statuses = sidecar.finish()  # flushes the trailing [5 s, 6 s)
        assert any(s.get("tail") for s in statuses)
        assert [w["w"] for w in store.words()] == ["sana", "sana"]
        assert store.words()[1]["s"] == round(5.5 * FLICKS)

    def test_runner_stop_flushes_everything_and_publishes(self):
        store = LiveTranscript()
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=lambda: (lambda audio, rate: [
                {"word": "loppu", "start": 0.5, "end": 1.0}]),
            store=store, read_frames=lambda s, e: [0.0] * (e - s),
            flushed=lambda p: 6 * RATE)
        published = []
        runner = LiveTranscribeRunner(sidecar, publish=published.append,
                                      min_interval_s=0.02)
        runner.start()
        runner.poke()
        runner.stop(flush=True)
        # however the words arrived (chunks or the tail flush), nothing is left
        lane = sidecar._lanes["t1"]
        assert lane["live"].done_frames == 6 * RATE
        assert store.words()
        assert published


class TestFlushBounds:
    """Owner, 2026-11-01: the flush after stop is bounded and never blocks the take."""

    def sidecar(self, engine, flushed, store=None):
        return LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=lambda: engine,
            store=store or LiveTranscript(),
            read_frames=lambda s, e: [0.0] * (e - s), flushed=flushed)

    def test_finish_drains_the_backlog_then_the_tail(self):
        # The engine fell behind during the take: 12 s flushed, nothing done.
        calls = []
        def engine(audio, rate):
            calls.append(len(audio))
            return [{"word": f"sana{len(calls)}", "start": 1.0, "end": 1.5}]
        sidecar = self.sidecar(engine, lambda p: 12 * RATE)
        statuses = sidecar.finish()
        assert not any(s.get("cancelled") for s in statuses)
        assert any(s.get("tail") for s in statuses)
        live = sidecar._lanes["t1"]["live"]
        assert live.done_frames == 12 * RATE  # nothing left behind
        words = [w["w"] for w in sidecar.store.words()]
        assert words == ["sana1", "sana2", "sana3"]

    def test_cancel_stops_the_drain_between_chunks_with_honest_coverage(self):
        cancel = threading.Event()
        calls = []
        def engine(audio, rate):
            calls.append(len(audio))
            if len(calls) == 1:
                cancel.set()  # the caller ran out of patience mid-drain
            return [{"word": "sana", "start": 1.0, "end": 1.5}]
        sidecar = self.sidecar(engine, lambda p: 17 * RATE)
        statuses = sidecar.finish(cancel=cancel)
        cancelled = [s for s in statuses if s.get("cancelled")]
        assert cancelled
        assert cancelled[0]["done_frames"] < cancelled[0]["flushed_frames"]
        assert sidecar._lanes["t1"]["live"].done_frames == 5 * RATE

    def test_stop_without_block_returns_while_the_engine_still_works(self):
        def slow(audio, rate):
            time.sleep(0.5)
            return [{"word": "myohaainen", "start": 1.0, "end": 1.5}]
        sidecar = self.sidecar(slow, lambda p: 6 * RATE)
        runner = LiveTranscribeRunner(sidecar, min_interval_s=0.02)
        runner.start()
        started = time.monotonic()
        runner.stop(flush=True, block=False)
        assert time.monotonic() - started < 0.4
        assert runner.flushing
        assert runner.wait(10)
        assert not runner.flushing
        assert sidecar._lanes["t1"]["live"].done_frames == 6 * RATE
        # the chunk the loop already took, plus the flushed tail
        assert [w["w"] for w in sidecar.store.words()] == ["myohaainen", "myohaainen"]

    def test_wait_times_out_on_a_hung_engine_and_cancel_is_safe(self):
        gate = threading.Event()  # never set

        def hung(audio, rate):
            return gate.wait() or []

        sidecar = self.sidecar(hung, lambda p: 6 * RATE)
        runner = LiveTranscribeRunner(sidecar, min_interval_s=0.02)
        runner.start()
        runner.stop(flush=True, block=False)
        assert runner.wait(0.3) is False  # the hung call runs out, unwedgeable
        runner.cancel()  # no raise, no effect on the running call
        assert runner.flushing  # honestly still busy


class TestEngineLifecycle:
    """Owner, 2026-11-01: workers never accumulate across takes."""

    def test_runner_exit_closes_the_engine(self):
        closed = []
        class Engine:
            def __call__(self, audio, rate):
                return [{"word": "x", "start": 0.0, "end": 0.5}]
            def close(self):
                closed.append(True)
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=Engine,
            read_frames=lambda s, e: [0.0] * (e - s), flushed=lambda p: 6 * RATE)
        runner = LiveTranscribeRunner(sidecar, min_interval_s=0.02)
        runner.start()
        runner.poke()
        runner.stop(flush=True)
        assert closed == [True]
        assert sidecar._engine is None

    def test_failing_factory_counts_toward_the_lane_budget(self):
        calls = []
        def factory():
            calls.append(1)
            raise RuntimeError("model missing")
        sidecar = LiveTranscribeSidecar(
            rate=RATE, folder="fake-take", lane_files={"t1": "x.wav"},
            engine_factory=factory,
            read_frames=lambda s, e: [0.0] * (e - s), flushed=lambda p: 6 * RATE)
        for _ in range(3):
            sidecar.tick()
        lane = sidecar._lanes["t1"]
        assert lane["failures"] == 3
        assert len(calls) == 3
        assert sidecar.tick() == []  # disabled lane: no more factory attempts
