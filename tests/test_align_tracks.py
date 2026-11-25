"""Track-unit analysis preserves the user's file order and spacing."""
from dataclasses import replace

import numpy as np
import pytest
from test_align_job import Store, setup

from kuulas.align_tracks import analyze_tracks, gap_options
from kuulas.memory import MemoryBudget
from kuulas.model import Clip, Media, Project, Track


def test_multiclip_track_agrees_on_one_shift(tmp_path):
    p,store=setup(tmp_path)
    candidate=p.tracks[1].clips[0]
    clips=(replace(candidate,length=25*p.rate),
           replace(candidate,id='b2',start=30*p.rate,offset=30*p.rate,
                   length=25*p.rate))
    p=replace(p,tracks=(p.tracks[0],replace(p.tracks[1],clips=clips)))
    result=analyze_tracks(p,store,['below','top'],'sound')
    row=result['tracks'][0]
    assert row['track']=='below'
    assert row['status']=='proposal'
    assert row['delta']==pytest.approx(3.,abs=.005)
    assert row['method']=='sound'
    assert p.tracks[1].clips==clips


def test_disagreeing_pieces_are_not_a_whole_track_proposal(tmp_path):
    p,store=setup(tmp_path)
    candidate=p.tracks[1].clips[0]
    clips=(replace(candidate,length=25*p.rate),
           replace(candidate,id='b2',start=32*p.rate,offset=30*p.rate,
                   length=25*p.rate))
    p=replace(p,tracks=(p.tracks[0],replace(p.tracks[1],clips=clips)))
    row=analyze_tracks(p,store,['top','below'],'sound')['tracks'][0]
    assert row['status']=='pieces_disagree'


def test_gaps_silence_and_constant_activity_do_not_manufacture_alignment():
    for mask in [np.zeros(2000,bool),np.ones(2000,bool)]:
        assert gap_options(mask,mask,np.ones(2000,bool),np.ones(2000,bool))==[]


def test_gaps_returns_bounded_alternatives_with_shared_coverage():
    rng=np.random.default_rng(12)
    ref=np.repeat(rng.random(150)>.5,50)
    cand=np.concatenate([np.zeros(100,bool),~ref[:-100]])
    opts=gap_options(ref,cand,np.ones(ref.size,bool),np.ones(cand.size,bool))
    assert opts
    assert opts[0]['delta']==pytest.approx(-2.,abs=.1)
    assert all(x['coverage']>=.65 for x in opts)
    assert len(opts)<=3


def test_unmatched_piece_prevents_whole_track_suggestion(tmp_path):
    p,store=setup(tmp_path)
    candidate=p.tracks[1].clips[0]
    clips=(replace(candidate,length=25*p.rate),
           replace(candidate,id='tiny',start=50*p.rate,offset=50*p.rate,
                   length=p.rate))
    p=replace(p,tracks=(p.tracks[0],replace(p.tracks[1],clips=clips)))
    row=analyze_tracks(p,store,['top','below'],'sound')['tracks'][0]
    assert row['status']=='pieces_unverified'


@pytest.mark.parametrize("method", ["gaps", "auto"])
def test_remote_tracks_without_bleed_produce_manual_gap_choices(tmp_path, method):

    rate=8000
    rng=np.random.default_rng(2026)
    blocks=rng.integers(25,150,100)
    activity=np.concatenate([np.full(n,bool(i%2)) for i,n in enumerate(blocks)])
    delayed=np.r_[np.zeros(40,bool),~activity[:-40]]
    ref=np.repeat(np.where(activity,.2,.001),160)
    guest=np.repeat(np.where(delayed,.2,.001),160)
    audio={'r':(ref*rng.normal(size=ref.size))[None,:].astype(np.float32),
           'g':(guest*rng.normal(size=guest.size))[None,:].astype(np.float32)}
    store=Store(tmp_path,audio)
    p=Project(rate=rate,media=tuple(Media(k,k,1,v.shape[1]) for k,v in audio.items()),
              tracks=(Track('r','Reference',clips=(Clip('r1','r',rate,0,ref.size),)),
                      Track('g','Remote',clips=(Clip('g1','g',0,0,guest.size),))))
    row=analyze_tracks(p,store,['r','g'],method)['tracks'][0]
    assert row['status']=='ambiguous'
    assert row['options'][0]['delta']==pytest.approx(.2,abs=.1)
    assert row['options'][0]['auditions']


def test_offline_reference_is_identified_as_the_reference(tmp_path):
    p,store=setup(tmp_path)
    (tmp_path/'ref').unlink()
    result=analyze_tracks(p,store,['top','below'],'auto')
    assert result['anchor_status']=='offline'
    assert result['tracks'][0]['status']=='reference_offline'
    assert store.reads==[]


def test_source_envelopes_cached_across_reference_pieces_and_calculations(tmp_path):
    p,store=setup(tmp_path)
    store.cache_root=tmp_path/'cache'
    store.budget=MemoryBudget(limit_bytes=1024*1024)
    store.cache_identity=lambda mid:mid
    clip=p.tracks[0].clips[0]
    p=replace(p,tracks=(replace(p.tracks[0],clips=(replace(clip,length=25*p.rate),
        replace(clip,id='a2',start=30*p.rate,offset=30*p.rate,length=25*p.rate))),
        p.tracks[1]))
    analyze_tracks(p,store,['top','below'],'auto')
    reads=len(store.reads)
    assert sum(n for key,_,n in store.reads if key=='candidate')<=58*p.rate
    analyze_tracks(p,store,['top','below'],'auto')
    assert len(store.reads)==reads



def test_sync_envelope_disk_cache_reopens_and_checks_source_identity(tmp_path):
    p,store=setup(tmp_path)
    store.cache_root=tmp_path/'cache'
    store.budget=MemoryBudget(limit_bytes=1024*1024)
    version=['first']
    store.cache_identity=lambda mid:mid+version[0]
    original=analyze_tracks(p,store,['top','below'],'sound')
    reads=len(store.reads)
    store.budget=MemoryBudget(limit_bytes=1024*1024)
    assert analyze_tracks(p,store,['top','below'],'sound')==original
    assert len(store.reads)==reads
    assert store.budget.stats()['sync-envelope']['disk_hits']>0
    version[0]='changed'
    analyze_tracks(p,store,['top','below'],'sound')
    assert len(store.reads)>reads
    reads=len(store.reads)
    (tmp_path/'candidate').unlink()
    result=analyze_tracks(p,store,['top','below'],'sound')
    assert result['tracks'][0]['status']=='offline'
    assert len(store.reads)==reads


def test_sync_corrupt_envelope_cache_recomputes(tmp_path):
    p,store=setup(tmp_path)
    store.cache_root=tmp_path/'cache'
    store.budget=MemoryBudget(limit_bytes=1024*1024)
    store.cache_identity=lambda mid:mid
    analyze_tracks(p,store,['top','below'],'sound')
    for path in store.cache_root.rglob('*.npy'):
        path.write_bytes(b'broken cache')
    store.budget=MemoryBudget(limit_bytes=1024*1024)
    reads=len(store.reads)
    result=analyze_tracks(p,store,['top','below'],'sound')
    assert result['tracks'][0]['status']=='proposal'
    assert len(store.reads)>reads
    assert store.budget.used<=store.budget.limit


def _two_session_project(tmp_path):
    """One reference and a guest track with two pieces that lie at different offsets from
    it, as two separately recorded sets of files do. Pieces are long enough for the
    measurement to find three independent points (10 s apart) in each."""
    rate=8000
    levels=np.random.default_rng(4).uniform(.05,.8,150*1000)
    ref=np.repeat(levels,8)[None,:].astype(np.float32)
    candidate=ref[:,rate*2:]
    store=Store(tmp_path,{"ref":ref,"candidate":candidate})
    project=Project(
        rate=rate,
        media=(Media("ref","ref",1,ref.shape[1]),
               Media("candidate","candidate",1,candidate.shape[1])),
        tracks=(Track("top","Top",clips=(Clip("a","ref",rate,0,ref.shape[1]),)),
                Track("below","Below",clips=(
                    Clip("b1","candidate",0,0,60*rate),
                    # Its source lies 80 s into the file; it sits 82 s into the
                    # timeline, so it is 2 s nearer the reference than the first piece.
                    Clip("b2","candidate",82*rate,80*rate,60*rate)))))
    return project,store


def test_only_the_chosen_pieces_are_measured(tmp_path):
    p,store=_two_session_project(tmp_path)
    assert analyze_tracks(p,store,['top','below'],'sound')['tracks'][0]['status']==(
        'pieces_disagree')
    first=analyze_tracks(p,store,['top','below'],'sound',clip_ids=['a','b1'])['tracks'][0]
    assert first['status']=='proposal'
    assert first['delta']==pytest.approx(3.,abs=.005)
    second=analyze_tracks(p,store,['top','below'],'sound',clip_ids=['a','b2'])['tracks'][0]
    assert second['status']=='proposal'
    assert second['delta']==pytest.approx(1.,abs=.005)


def test_reference_pieces_outside_the_choice_are_ignored(tmp_path):
    p,store=_two_session_project(tmp_path)
    anchor=p.tracks[0].clips[0]
    rate=p.rate
    pieces=(replace(anchor,id='a1',length=70*rate),
            # The same recording again, placed 100 s later: the guest matches it too, at
            # another offset, so with both reference pieces the answer is not unique.
            replace(anchor,id='a2',start=anchor.start+100*rate,offset=0,length=70*rate))
    p=replace(p,tracks=(replace(p.tracks[0],clips=pieces),p.tracks[1]))
    assert analyze_tracks(p,store,['top','below'],'sound',
                          clip_ids=['a1','a2','b1'])['tracks'][0]['status']!='proposal'
    row=analyze_tracks(p,store,['top','below'],'sound',clip_ids=['a1','b1'])['tracks'][0]
    assert row['status']=='proposal'
    assert row['delta']==pytest.approx(3.,abs=.005)


def test_a_track_with_none_of_the_chosen_pieces_is_refused(tmp_path):
    from kuulas.align_errors import SyncError  # noqa: PLC0415
    p,store=_two_session_project(tmp_path)
    with pytest.raises(SyncError):
        analyze_tracks(p,store,['top','below'],'sound',clip_ids=['a'])
