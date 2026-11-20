"""HTTP surface of the isolated full-window timing review."""
from typing import Literal

from pydantic import BaseModel, StrictInt

from .align_review import SyncError, fail
from .messages import error_body


class Begin(BaseModel):
    tracks: list[str]


class Identity(BaseModel):
    id: str


class Move(Identity):
    track: str
    frames: StrictInt
    clip: str | None = None


class Measure(Identity):
    method: Literal['auto','sound','gaps'] = 'auto'


class Listen(Identity):
    original: bool = False
    at: StrictInt = 0
    seconds: float = 6
    loop: bool = False


def install(app, session, engine):
    @app.exception_handler(SyncError)
    async def sync_error(_request, error):
        from fastapi.responses import JSONResponse  # noqa: PLC0415
        return JSONResponse(error_body(error.key, **error.params),status_code=409)

    @app.post('/api/sync-review')
    def begin(body: Begin):
        engine.stop()
        engine.clear_listen_source()
        return session.sync_begin(body.tracks)

    @app.get('/api/sync-review')
    def current():
        with session.lock:
            return None if session._sync_review is None else session._sync_review.view()

    @app.post('/api/sync-review/move')
    def move(body: Move):
        engine.stop()
        engine.clear_listen_source()
        return session.sync_move(body.id,body.track,body.frames,body.clip)

    @app.post('/api/sync-review/reset')
    def reset(body: Identity):
        engine.stop()
        engine.clear_listen_source()
        return session.sync_reset(body.id)

    @app.post('/api/sync-review/measure')
    def measure(body: Measure):
        engine.stop()
        return {'jobs':session.sync_measure(body.id,body.method)}

    @app.post('/api/sync-review/listen')
    def listen(body: Listen):
        import math  # noqa: PLC0415
        with session.lock:
            review=session._sync_get(body.id)
            project=review.project if body.original else review.preview()
        if (body.at<0 or not math.isfinite(body.seconds)
                or not .1<=body.seconds<=4*3600):
            fail('range')
        engine.stop()
        # Unlike clipboard preview, use a replacement source so seek and looping
        # remain in the proposal's timeline coordinates, without a second voice.
        engine.set_listen_source(project,{})
        end=min(project.length,body.at+round(body.seconds*project.rate))
        if end<=body.at:
            fail('range')
        engine.play(body.at,end,loop=[body.at,end] if body.loop else None)
        return {'started':True}

    @app.post('/api/sync-review/cancel')
    def cancel(body: Identity):
        engine.stop()
        engine.clear_listen_source()
        session.sync_cancel(body.id)
        return {'closed':True}

    @app.post('/api/sync-review/apply')
    def apply(body: Identity):
        engine.stop()
        engine.clear_listen_source()
        session.sync_apply(body.id)
        return {'closed':True}
