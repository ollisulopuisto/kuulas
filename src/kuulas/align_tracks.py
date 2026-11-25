"""Conservative suggestions for ordered, multi-piece participant tracks.

Sound matches compare real source spans, never zero-filled gaps. Turn matching
uses speechmix's activity decision and requires shared coverage. Its scores are
ranking heuristics, not confidence probabilities, and always need human review.
"""
from __future__ import annotations

import math
from dataclasses import asdict, replace

import numpy as np
from speechmix import grid

from . import caches, priority
from .align_job import snapshot_key
from .align_proposal import propose
from .align_review import fail
from .align_sound import measure
from .align_stream import read_envelope
from .media import streaming
from .memory import BUDGET
from .messages import KuulasError


def _correlate(a, b):
    size = 1 << (a.size+b.size-2).bit_length()
    result = np.fft.irfft(np.fft.rfft(a, size)*np.fft.rfft(b[::-1], size), size)
    return result[:a.size+b.size-1]


def gap_options(reference, candidate, ref_valid, cand_valid):
    """Up to three separated handoff alternatives on a 20 ms activity grid.

    Requiring 65% shared recorded coverage prevents the trivial answer of
    moving speakers outside the conversation. Repeated patterns remain choices.
    """
    r,c = np.asarray(reference,bool),np.asarray(candidate,bool)
    rv,cv = np.asarray(ref_valid,bool),np.asarray(cand_valid,bool)
    if (min(r.size,c.size)<1500 or r.shape!=rv.shape or c.shape!=cv.shape
            or min(np.count_nonzero(np.diff(r)),np.count_nonzero(np.diff(c)))<8):
        return []
    n,m=r.size,c.size
    coverage=_correlate(rv.astype(float),cv.astype(float))/max(1,min(rv.sum(),cv.sum()))
    overlap=_correlate((r&rv).astype(float),(c&cv).astype(float))
    active=_correlate((r&rv).astype(float),cv.astype(float))+_correlate(rv.astype(float),(c&cv).astype(float))
    # Reward a speaker ending near the other speaker beginning, in both directions.
    re=np.r_[False,r[:-1]&~r[1:]].astype(float)
    rs=np.r_[False,~r[:-1]&r[1:]].astype(float)
    ce=np.r_[False,c[:-1]&~c[1:]].astype(float)
    cs=np.r_[False,~c[:-1]&c[1:]].astype(float)
    handoff=_correlate(re,cs)+_correlate(rs,ce)
    kernel=np.ones(41)
    handoff=np.convolve(handoff,kernel,mode='same')
    score=handoff-10*overlap/np.maximum(1,active)
    eligible=(coverage>=.65)&(handoff>=5)&(active>=500)
    score[~eligible]=-np.inf
    out=[]
    for _ in range(3):
        at=int(np.argmax(score))
        if not math.isfinite(float(score[at])) or score[at]<1:
            break
        delta=(at-(m-1))*.02
        ends=np.flatnonzero(re)*.02
        starts=np.flatnonzero(cs)*.02+delta
        handoffs=[]
        for end in ends:
            pos=int(np.searchsorted(starts,end))
            near=starts[max(0,pos-1):pos+1]
            if near.size and float(np.min(np.abs(near-end)))<=.4:
                handoffs.append(float(end))
        auditions=([handoffs[0],handoffs[len(handoffs)//2],handoffs[-1]]
                   if handoffs else [])
        out.append({'delta':delta,'score':round(float(score[at]),3),
                    'auditions':auditions,
                    'coverage':round(float(coverage[at]),6),
                    'handoffs':round(float(handoff[at]))})
        score[max(0,at-50):min(n+m-1,at+51)]=-np.inf
    return out


def analyze_tracks(project, store, track_ids, method='auto', clip_ids=None):
    """``clip_ids``: measure only these pieces (two sets of files recorded separately lie
    at different offsets and cannot share one answer); None: every piece of the tracks."""
    if method not in ('auto','sound','gaps'):
        fail('method')
    tracks=[t for t in project.tracks if t.id in set(track_ids)]
    if (len(tracks)!=len(track_ids) or not 2<=len(tracks)<=32
            or any(not t.clips or len(t.clips)>64 for t in tracks)):
        fail('selection')
    if clip_ids is not None:
        chosen=set(clip_ids)
        tracks=[replace(t,clips=tuple(c for c in t.clips if c.id in chosen))
                for t in tracks]
        if any(not t.clips for t in tracks):
            fail('selection')
    if any(max(c.end for c in t.clips)-min(c.start for c in t.clips)
           >4*3600*project.rate for t in tracks):
        fail('limit')

    def source(clip):
        priority.checkpoint()
        if hasattr(store,'partial_info') and store.partial_info(clip.media):
            fail('partial')
        try:
            if not store.transcription_path(clip.media).is_file():
                fail('offline')
        except (OSError,KeyError,KuulasError) as e:
            if (isinstance(e,KuulasError)
                    and getattr(e,'key','').startswith('error.sync.')):
                raise
            fail('offline')
        media=project.media_item(clip.media)
        if clip.offset<0 or clip.length<=0 or clip.offset+clip.length>media.frames:
            fail('range')
        def compute():
            with streaming():
                return read_envelope(lambda a,n:store.read(clip.media,a,n),
                                     rate=project.rate, start=clip.offset,
                                     frames=clip.length)

        identity = (store.cache_identity(clip.media)
                    if hasattr(store, 'cache_identity') else media.sha256)
        if not identity:
            return compute()
        key = caches.key([identity], {'rate':project.rate,'start':clip.offset,
                                      'frames':clip.length}, 'sync-rms-envelope@1')
        root = getattr(store, 'cache_root', None)
        spill = caches.path(root, 'analysis', key, 'npy') if root is not None else None
        budget = getattr(store, 'budget', BUDGET)
        return budget.fetch('sync-envelope', key, compute, spill=spill)

    def activity(track):
        origin=min(c.start for c in track.clips)
        count=math.ceil((max(c.end for c in track.clips)-origin)/project.rate/.02)
        db=np.full(count,-240.,float)
        valid=np.zeros(count,bool)
        for clip in track.clips:
            env=source(clip)
            n=env.size//20
            levels=20*np.log10(np.maximum(1e-12,np.sqrt((env[:n*20].reshape(n,20)**2).mean(axis=1))))
            start=round((clip.start-origin)/project.rate/.02)
            db[start:start+n]=np.maximum(db[start:start+n],levels)
            valid[start:start+n]=True
        smoothed=grid.smooth(db)
        lane=grid.lane(track.id,[(smoothed,valid,grid.noise_floor(smoothed,valid),grid.FLOOR_MARGIN_DB,0.)])
        return lane.on,valid,origin/project.rate

    reference=tracks[0]
    rows=[]
    ref_activity=None
    anchor_status=None
    for track in tracks[1:]:
        row={'track':track.id,'status':'unmatched','method':method,'options':[]}
        active_track=reference.id
        try:
            if method!='gaps':
                if len(reference.clips)*len(track.clips)>256:
                    fail('limit')
                measurements=[]
                measured_pieces=set()
                for rc in reference.clips:
                    active_track=reference.id
                    ref=source(rc)
                    for cc in track.clips:
                        active_track=track.id
                        points=measure(ref,source(cc))
                        if points:
                            measured_pieces.add(cc.id)
                        measurements.extend(((cc.start/project.rate+t,
                                              (rc.start-cc.start)/project.rate+lag,ratio)
                                             for t,lag,ratio in points))
                fit=propose(measurements)
                if measured_pieces != {c.id for c in track.clips}:
                    row['status']='pieces_unverified'
                elif fit is not None:
                    consistent = all(abs(lag-fit.offset-fit.slope*t)<=.004
                                     for t,lag,_ in measurements)
                    fixed = abs(fit.slope)*project.length/project.rate<=.004
                    times=sorted(t+fit.offset for t,_,_ in measurements)
                    auditions=[times[0],times[len(times)//2],times[-1]]
                    row.update(method='sound',fit=asdict(fit),delta=fit.offset,
                               auditions=auditions,
                               status='proposal' if consistent and fixed
                               else 'drift_review')
                elif measurements:
                    row['status']='pieces_disagree'
            if method=='gaps' or (method=='auto' and row['status'] in
                                  ('unmatched','pieces_unverified','pieces_disagree')):
                if ref_activity is None:
                    active_track=reference.id
                    ref_activity=activity(reference)
                ref_on,ref_valid,ref_origin=ref_activity
                active_track=track.id
                on,valid,origin=activity(track)
                options=gap_options(ref_on,on,ref_valid,valid)
                for option in options:
                    option['delta']+=ref_origin-origin
                    option['auditions']=[t+ref_origin for t in option['auditions']]
                row.update(method='gaps',options=options,
                           status='ambiguous' if options else 'unmatched')
        except KuulasError as e:
            row['status']=e.key.removeprefix('error.sync.')
            if active_track==reference.id:
                anchor_status=row['status']
                row['status']='reference_'+row['status']
        rows.append(row)
    return {'snapshot':snapshot_key(project),'anchor':reference.id,
            'anchor_status':anchor_status,'tracks':rows}
