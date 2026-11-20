"""Snapshot-only automatic-sync job, no history or source writes."""
from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

from kuulas import offload
from kuulas.align_job import analyze, snapshot_key
from kuulas.messages import t
from kuulas.model import Clip, Media, Project, Track
from kuulas.session import Session


class Store:
    def __init__(self, root, audio):
        self.root, self.audio, self.reads = root, audio, []
        for key in audio:
            (root/key).touch()

    def transcription_path(self, key):
        return self.root/key

    def read(self, key, first, count):
        self.reads.append((key,first,count))
        return self.audio[key][:,first:first+count]


def setup(tmp_path):
    rate=8000
    rng=np.random.default_rng(4)
    levels=rng.uniform(.05,.8,60*1000)
    ref=np.repeat(levels,8)[None,:].astype(np.float32)
    candidate=ref[:,8000*2:]
    store=Store(tmp_path,{"ref":ref,"candidate":candidate})
    project=Project(rate=rate,media=(Media("ref","ref",1,ref.shape[1]),
                                   Media("candidate","candidate",1,candidate.shape[1])),
                    tracks=(Track("top","Top",clips=(Clip("a","ref",8000,0,ref.shape[1]),)),
                            Track("below","Below",clips=(Clip("b","candidate",0,0,candidate.shape[1]),))))
    return project,store


def test_job_chooses_topmost_selected_reference_and_keeps_snapshot_unchanged(tmp_path):
    project,store=setup(tmp_path)
    before=project.to_dict()
    result=analyze(project,store,["b","a"])
    assert result["reference"]=="a"
    assert result["snapshot"]==snapshot_key(project)
    candidate=result["candidates"][0]
    assert candidate["clip"]=="b"
    assert candidate["proposal"]["offset"]==pytest.approx(2.,abs=.001)
    assert candidate["timeline_delta"]==pytest.approx(3.,abs=.001)
    assert project.to_dict()==before
    assert max(n for _,_,n in store.reads)<=project.rate*10


def test_job_does_not_read_an_offline_source_as_silence(tmp_path):
    project,store=setup(tmp_path)
    (tmp_path/"candidate").unlink()
    result=analyze(project,store,["a","b"])
    assert result["candidates"][0]["status"]=="offline"
    assert not any(key=="candidate" for key,_,_ in store.reads)


def test_job_rejects_invalid_or_same_track_selection_before_reading(tmp_path):
    project,store=setup(tmp_path)
    for ids in [["a"],["a","missing"],["a","a"]]:
        with pytest.raises(ValueError,match=t("error.sync.clip_selection")):
            analyze(project,store,ids)
    assert store.reads==[]


def test_snapshot_changes_for_an_unrelated_edit_too(tmp_path):
    project,_=setup(tmp_path)
    assert snapshot_key(project)!=snapshot_key(replace(project,master_gain_db=-3))


def test_real_worker_matches_inline(tmp_path, monkeypatch):
    rng = np.random.default_rng(15)
    level = np.repeat(rng.uniform(.05, .8, 60 * 1000), 48)
    audio = (level * rng.standard_normal(level.size)).astype(np.float32)
    sf.write(tmp_path / "reference.wav", audio, 48000, subtype="FLOAT")
    sf.write(tmp_path / "candidate.wav", audio[2*48000:], 48000, subtype="FLOAT")
    session = Session(tmp_path / "Worker.kuulas")
    try:
        session.import_media([str(tmp_path / "reference.wav"),
                              str(tmp_path / "candidate.wav")])
        project = session.state
        ids = [track.clips[0].id for track in project.tracks]
        expected = analyze(project, session.store, ids)
        monkeypatch.setattr(offload, "MODE", "process")
        actual = offload.call("automatic_sync", project, session.store, ids)
        assert actual == expected
        offset = actual["candidates"][0]["proposal"]["offset"]
        assert offset == pytest.approx(2., abs=.001)
        assert session.state == project
    finally:
        session.close()


def test_multitrack_analysis_reopens_store_in_real_worker(tmp_path, monkeypatch):
    rng = np.random.default_rng(50)
    level = np.repeat(rng.uniform(.05, .8, 60 * 1000), 48)
    audio = (level * rng.standard_normal(level.size)).astype(np.float32)
    sf.write(tmp_path / 'reference.wav', audio, 48000, subtype='FLOAT')
    sf.write(tmp_path / 'candidate.wav', audio[2*48000:], 48000, subtype='FLOAT')
    session = Session(tmp_path / 'Tracks.kuulas')
    try:
        session.import_media([str(tmp_path / 'reference.wav'),
                              str(tmp_path / 'candidate.wav')])
        project = session.state
        ids = [track.id for track in project.tracks]
        monkeypatch.setattr(offload, 'MODE', 'process')
        result = offload.call('automatic_sync_tracks', project, session.store,
                              ids, 'sound')
        assert result['tracks'][0]['delta'] == pytest.approx(2., abs=.001)
        assert result['tracks'][0]['status'] == 'proposal'
        assert session.state == project
    finally:
        session.close()
