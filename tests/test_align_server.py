from fastapi.testclient import TestClient
from test_align_review import project
from test_history import register
from test_server import FakeEngine as BaseEngine

from kuulas.server import create_app
from kuulas.session import Session


class FakeEngine(BaseEngine):
    def clear_listen_source(self):
        self.calls.append(("clear_listen",))

    def set_listen_source(self, project, sources):
        self.preview_project=project
        self.calls.append(("listen",project))


def test_full_window_review_routes_lock_edits_and_cancel_without_mutation(tmp_path):
    s=Session(tmp_path/'s.kuulas')
    engine=FakeEngine(s)
    with TestClient(create_app(s,engine)) as client:
        register(s.history,'m',480000)
        s.history.commit('fixture',project())
        before=s.state
        response=client.post('/api/sync-review',json={'tracks':['a','b']})
        assert response.status_code==200
        review=response.json()
        rid=review['id']
        denied=client.post('/api/command',json={'name':'add_track','args':{}})
        assert denied.status_code==409
        assert s.state==before
        moved=client.post('/api/sync-review/move',json={
            'id':rid,'track':'b','frames':4800})
        assert moved.status_code==200
        assert moved.json()['offsets']['b1']==4800
        assert s.state==before
        assert client.post('/api/sync-review/cancel',json={'id':rid}).status_code==200
        assert s.state==before
        assert s._sync_review is None
    s.close()


def test_sync_route_rejects_wrong_id_and_bad_types(tmp_path):
    s=Session(tmp_path/'s.kuulas')
    with TestClient(create_app(s,FakeEngine(s))) as client:
        register(s.history,'m',480000)
        s.history.commit('fixture',project())
        rid=client.post('/api/sync-review',json={'tracks':['a','b']}).json()['id']
        assert client.post('/api/sync-review/move',json={
            'id':'wrong','track':'b','frames':2}).status_code==409
        assert client.post('/api/sync-review/move',json={
            'id':rid,'track':'b','frames':True}).status_code==400
        assert client.post('/api/sync-review/apply',json={'id':rid}).status_code==200
    s.close()


def test_audition_uses_proposal_not_original_and_original_comparison(tmp_path):
    s=Session(tmp_path/'s.kuulas')
    engine=FakeEngine(s)
    with TestClient(create_app(s,engine)) as client:
        register(s.history,'m',480000)
        s.history.commit('fixture',project())
        before=s.state
        rid=client.post('/api/sync-review',json={'tracks':['a','b']}).json()['id']
        client.post('/api/sync-review/move',json={'id':rid,'track':'b','frames':4800})
        played=client.post('/api/sync-review/listen',json={'id':rid,'at':0})
        assert played.status_code==200
        assert engine.preview_project.tracks[1].clips[0].start==52800
        assert s.state==before
        original=client.post('/api/sync-review/listen',
                             json={'id':rid,'at':0,'original':True})
        assert original.status_code==200
        assert engine.preview_project==before
        client.post('/api/sync-review/cancel',json={'id':rid})
    s.close()
