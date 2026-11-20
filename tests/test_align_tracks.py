"""Track-unit analysis preserves the user's file order and spacing."""
from dataclasses import replace

import numpy as np
import pytest
from test_align_job import setup

from kuulas.align_tracks import analyze_tracks, gap_options


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
