"""The HTTP API (WP3): the browser UI's only way to the session and the engine.

``create_app(session, engine)`` is a thin skin. The server converts nothing
(frames stay frames), decides nothing and keeps no state of its own: every edit
is one ``Session`` call that has committed to the history before the response
is written (ground rule 8), and the answer is the whole project, so the UI
cannot drift from it.

Errors are ``messages.error_body`` (key, params, text in the session's
language): 400 for an edit that makes no sense, 404 for an id that does not
exist, 500 for the rest. The language follows ``Accept-Language`` and falls
back to the OS default. ``messages`` keeps its language process-wide, which is
right for one user at one browser, so a request sets it when it arrives.

``WS /api/live`` replaces polling: the server pushes, the UI keeps one
connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
import math
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, File, Form, Request, UploadFile, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool
from starlette.websockets import WebSocketDisconnect

from . import (
    automix,
    automix_remote,
    bgjobs,
    clipboard_browse,
    colab_signin,
    colab_transcribe,
    export,
    export_formats,
    export_names,
    logsetup,
    messages,
    music_report,
    new_project,
    offload,
    plugins,
    priority,
    project_stats,
    render_listen,
    series_actions,
    transcribe,
    ui_prefs,
)
from . import (
    profiler as profiler_module,
)
from .build_info import build_label
from .candidates import UnknownCandidateError
from .hand_adjusted import balance_cap, hand_adjusted
from .history import HistoryError
from .media import ImportResult, MediaError
from .messages import KuulasError, error_body, t
from .ops import EditError
from .paths import find_ui_dir
from .peaks import PeakError
from .playplan import PlaybackRequestError, check_loop, check_skip
from .record_session import RecordError
from .resume import merge_view, now_iso, read_resume
from .session import (
    CLIPBOARD_EDITS,
    NarrationScriptError,
    NoSuchEntryError,
    SilenceNotMeasuredError,
    SilenceStaleError,
    SubtitlesError,
    TranscriptTextError,
)
from .view_memory import ViewMemory, ViewMemoryError

log = logging.getLogger("kuulas.server")

#: The ``ui/`` folder (repo, wheel or app bundle: ``paths.find_ui_dir``); served at
#: ``/`` when it has an index.html.
UI_DIR = find_ui_dir(__file__)
#: How often the live channel looks at the engine while playing: often enough
#: to notice a run ending by itself or a skip run restarting within a frame or
#: two. What it sends is far less: anchors (below).
LIVE_TICK_S = 1 / 30
#: While playing, a correction anchor goes out this often. The browser draws the
#: playhead from the last anchor every animation frame (ui/playhead-clock.js), so
#: the cursor moves with the screen, not with this period, and a reading that came
#: late (the GIL, a busy thread) costs nothing but a slightly older anchor.
LIVE_CORRECT_S = 0.2
#: ...and while stopped, only to hear of engine notices (the engine's own period).
LIVE_IDLE_S = 0.25
#: ...and the level meter goes out about 15 times a second while playing (it is a
#: display, and a frame is a few bytes): every other tick at the display rate.
LIVE_METER_S = 1 / 15
#: Peak tiles never change (their ETag is the content's key), so the browser
#: may keep them for a year and never ask again.
TILE_CACHE = "public, max-age=31536000, immutable"


class UnknownIdError(KuulasError):
    """The id in the request names nothing (404)."""


HISTORY_PAGE = 100
HISTORY_PAGE_MAX = 500


class BadRequestError(KuulasError):
    """The request is not one the API takes (400)."""


def pick_language(header: str | None, default: str) -> str:
    """The first language of ``Accept-Language`` (best ``q`` first) that kuulas
    ships; ``default`` when the header is missing, empty or names none."""
    ranked: list[tuple[float, int, str]] = []
    for order, part in enumerate((header or "").split(",")):
        tag, *params = (x.strip() for x in part.split(";"))
        quality = 1.0
        for param in params:
            if param.startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0
        if tag and tag != "*":
            ranked.append((-quality, order, tag))
    for _, _, tag in sorted(ranked):
        primary = tag.lower().replace("_", "-").split("-")[0]
        if primary in messages.LANGUAGES:
            return primary
    return default


def request_language(header: str | None, default: str) -> str:
    """The language of one request: the user's explicit choice (View > Language)
    first, then the browser's ``Accept-Language``, then ``default``."""
    chosen = messages.language_setting()
    return chosen if chosen != messages.AUTO else pick_language(header, default)


# -- bodies --------------------------------------------------------------------


class LanguageBody(BaseModel):
    setting: str


class EditBody(BaseModel):
    op: str
    args: dict[str, Any] = {}
    label: str | None = None
    coalesce: str | None = None


class CommandBody(BaseModel):
    name: str
    args: dict[str, Any] = {}


class CopyBody(BaseModel):
    clip_ids: list[str] | None = None
    start: int | None = None
    end: int | None = None
    track_ids: list[str] | None = None
    name: str = ""


class PinBody(BaseModel):
    pinned: bool = True


class RenameBody(BaseModel):
    name: str


class ClipboardPreviewBody(BaseModel):
    #: Limit the preview to the project's level (WP82); the user's preference.
    limit: bool = True


class AdoptBody(BaseModel):
    entry: dict[str, Any]
    from_project: str = ""


class ShareBody(BaseModel):
    shared: bool


class ClearOldBody(BaseModel):
    keep: int = Field(100, ge=1)


class ViewMemoryBody(BaseModel):
    view: dict


class CutPreviewBody(BaseModel):
    words: list[dict[str, Any]] = Field(default_factory=list)


class RestoreBody(BaseModel):
    node: str | int


class ImportBody(BaseModel):
    paths: list[str]
    # "copy" is the API's word; the field has another name as BaseModel owns copy().
    copy_files: bool = Field(False, alias="copy")
    mode: str | None = None
    order: str = "given"
    track_naming: str = "file"
    start_frame: int = 0
    onto_track: str | None = None


class WordBody(BaseModel):
    media: str
    index: int
    w: str


class ProfileBody(BaseModel):
    action: str
    seconds: float = 30.0
    interval: float | None = None


class LogLevelBody(BaseModel):
    level: str


class RenderListenBody(BaseModel):
    #: true: play the rendered mix in place of the edit; false: back to the edit.
    on: StrictBool


class TransportBody(BaseModel):
    action: str
    at: int | None = None
    until: int | None = None
    # play only: frame ranges [a, b) to jump over (crossfaded), the tape
    # speed (negative is backward) and whether the pitch must be kept.
    skip: list[list[int]] | None = None
    speed: float = 1.0
    preserve_pitch: bool = True
    # play only: [start, end] in frames, played over and over (WP50).
    loop: list[int] | None = None


class TranscribeBody(BaseModel):
    media_ids: list[str]
    model: str | None = None
    language: str | None = None
    backend: str = "local"
    force: bool = False  # transcribe even recordings used only on music tracks


class RecordStartBody(BaseModel):
    device: dict[str, Any] | None = None
    # Several channels (WP12b): [{channel, track_id, name}], each onto its own track.
    # Without it, the one-channel form below.
    channels: list[dict[str, Any]] | None = None
    channel: int = 1
    track_id: str | None = None  # None or "new": a new speech track named ``name``
    name: str = ""
    at: int = 0


class RecordArmBody(BaseModel):
    # Listen for pre-roll (WP12c): the same input and channel the take will use.
    device: dict[str, Any] | None = None
    channels: list[int] | None = None  # the device channels the take will record
    channel: int = 1
    preroll_s: float = 60.0


class RecordStopBody(BaseModel):
    # The page's stop gesture (two_step, one_click, hold); without one nothing stops.
    mode: str | None = None
    held_ms: int = 0


class RecordImportBody(BaseModel):
    takes: list[str]


# -- the live channel's fan-out ------------------------------------------------


class Hub:
    """Messages from any thread to every connected live channel.

    A session change happens on a request thread, a channel lives on the event
    loop, so each channel registers its loop and queue and a message crosses
    with ``call_soon_threadsafe``.
    """

    def __init__(self) -> None:
        self._clients: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    def add(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self._clients.append((loop, queue))

    def remove(self, queue: asyncio.Queue) -> None:
        self._clients = [c for c in self._clients if c[1] is not queue]

    def publish(self, message: dict) -> None:
        for loop, queue in list(self._clients):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:  # that loop has closed: the channel is gone
                self.remove(queue)


def anchor_message(status: dict, now: float) -> dict:
    """The live channel's playhead anchor from ``engine.status()``: the heard
    ``position``, ``t`` the server's monotonic time it was heard at, ``now`` when
    this went out (both seconds; the browser maps them to its own clock with the
    ping offset, or by ``now - t`` when it has none), ``speed`` (signed, the live
    one for fast listening), ``seq`` (the engine's transport version: the browser
    and this channel drop anything older), ``end``, ``skip`` and ``loop`` (for
    extrapolating across them). A clipboard preview plays another project: its
    frames are not the timeline's, so it never says playing."""
    playing = bool(status["playing"]) and not status.get("preview")
    return {"type": "anchor", "position": int(status["position"]), "playing": playing,
            "speed": float(status.get("speed", 1.0)),
            "t": float(status.get("t", now)), "now": now, "seq": status.get("seq"),
            "end": status.get("end"), "skip": status.get("skip", []),
            "loop": status.get("loop"), "rate": status.get("rate")}


def preview_message(status: dict, now: float) -> dict:
    """The live channel's clipboard-preview anchor: the fields of
    ``anchor_message`` for the preview's own frames (0 at the excerpt's start,
    ``end`` its length), so the Clipboard chip can draw its progress. Never the
    timeline's playhead. A preview mixed into the playing timeline
    (``status["mix_preview"]``) reports in its own frames and version while the
    timeline's anchors go on unchanged. The version is the newest of the two
    counters, so an "ended" is always newer than the "start" the page holds."""
    mix = status.get("mix_preview")
    if mix:
        message = anchor_message({
            "playing": True, "position": mix["position"], "t": mix["t"],
            "seq": mix["seq"], "end": mix["end"], "speed": 1.0, "skip": [],
            "loop": None, "rate": status.get("rate")}, now)
    else:
        message = anchor_message({**status, "preview": False}, now)
    message["type"] = "preview"
    message["seq"] = newest_seq(message["seq"], status.get("preview_seq"))
    return message


def newest_seq(*seqs):
    """The largest of the transport versions given (None: unknown)."""
    known = [s for s in seqs if s is not None]
    return max(known) if known else None


def newer_seq(seq, last) -> bool:
    """Is a reading with transport version ``seq`` as new as ``last`` (None: an
    engine without versions, always)?"""
    return seq is None or last is None or seq >= last


def meter_message(levels: dict) -> dict:
    """The live channel's meter frame: peak and peak-hold per channel, dBFS. (The engine
    also measures RMS; the display has no use for it yet, so it is not sent.)"""
    return {"type": "meter",
            "meter": {key: round(float(levels[key]), 1)
                      for key in ("l", "r", "hold_l", "hold_r")}}


# -- the app -------------------------------------------------------------------


_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "testserver"})


def _local_origin(origin: str) -> bool:
    """Is the Origin header a page served by this machine's own loopback address?"""
    from urllib.parse import urlsplit  # noqa: PLC0415 - only the check needs it
    try:
        host = (urlsplit(origin).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS


def create_app(session, engine, *, language: str | None = None,
               ui_dir: str | Path = UI_DIR, tick: float = LIVE_TICK_S,
               meter_every: float = LIVE_METER_S, recorder=None,
               profiler: profiler_module.Profiler | None = None,
               correct_every: float = LIVE_CORRECT_S) -> FastAPI:
    """``session``, ``engine`` and ``recorder`` (a ``RecordSession``, or None: recording
    answers "unavailable") are borrowed: the caller closes them."""
    default_language = language or messages.default_language()
    ui = Path(ui_dir)
    app = FastAPI(title="kuulas", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.last_input = time.monotonic()
    hub = Hub()
    # The performance report (Help > Record a performance report): the process-wide
    # profiler unless a test passes its own. It reads the project and engine on its own
    # thread and never takes the session lock.
    perf_profiler = profiler or profiler_module.PROFILER
    perf_profiler.set_facts(lambda: profiler_module.session_facts(session, engine))
    # The live channels read the engine on a thread of their own, not the event
    # loop's default executor (asyncio.to_thread): a pile of other work queued
    # there must not hold the playhead up. One thread: a reading is quick.
    live_reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kuulas-live")
    # Background work yields to playback (docs/PLAYBACK-PRIORITY.md): the gate
    # reads the engine's lock-free flag; a fake engine without one never plays.
    priority.GATE.watch(lambda: bool(getattr(engine, "is_playing", False)))

    session.subscribe(lambda _state: hub.publish(
        {"type": "state_changed", "head": session.history.head}))
    if recorder is not None:
        # Levels, notices and the take's state go out on the live channel (no polling).
        recorder.set_publish(hub.publish)

    # -- plumbing ----------------------------------------------------------

    @app.middleware("http")
    async def per_request(request: Request, call_next):
        # Validate Host header against local loopback interfaces and test server
        host = (request.url.hostname or "").lower()
        if host and host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            return JSONResponse(
                error_body("error.server.bad_request", detail="Invalid Host header"),
                status_code=400,
            )
        # A page on another site (or a sandboxed one, Origin "null") must not drive the
        # server: browsers send Origin on cross-site requests. Calls without Origin (the
        # app's own same-origin reads, curl, `kuulas ctl`, tests) pass.
        origin = request.headers.get("origin")
        if origin is not None and not _local_origin(origin):
            return JSONResponse(
                error_body("error.server.bad_request", detail="Invalid Origin header"),
                status_code=403,
            )

        messages.set_language(request_language(request.headers.get("accept-language"),
                                               default_language))
        if request.url.path != "/api/jobs" and request.method != "GET":
            app.state.last_input = time.monotonic()
            priority.GATE.note_input()
        try:
            return await call_next(request)
        except Exception as e:
            log.exception(t("log.server.request_failed", method=request.method,
                            path=request.url.path))
            return JSONResponse(error_body("error.server.internal", error=str(e)),
                                status_code=500)

    def answer(error: KuulasError, status: int) -> JSONResponse:
        return JSONResponse(error_body(error.key, **error.params), status_code=status)

    @app.exception_handler(EditError)
    async def _edit_error(_request: Request, e: EditError):
        return answer(e, 400)

    @app.exception_handler(BadRequestError)
    async def _bad_request(_request: Request, e: BadRequestError):
        return answer(e, 400)

    @app.exception_handler(PlaybackRequestError)
    async def _bad_playback(_request: Request, e: PlaybackRequestError):
        return answer(e, 400)

    @app.exception_handler(SilenceNotMeasuredError)
    async def _silence_not_measured(_request: Request, e: SilenceNotMeasuredError):
        return answer(e, 409)

    @app.exception_handler(SilenceStaleError)
    async def _silence_stale(_request: Request, e: SilenceStaleError):
        return answer(e, 409)

    @app.exception_handler(NoSuchEntryError)
    async def _no_entry(_request: Request, e: NoSuchEntryError):
        return answer(e, 404)

    @app.exception_handler(UnknownCandidateError)
    async def _no_candidate(_request: Request, e: UnknownCandidateError):
        return answer(e, 404)

    @app.exception_handler(UnknownIdError)
    async def _unknown(_request: Request, e: UnknownIdError):
        return answer(e, 404)

    @app.exception_handler(PeakError)
    async def _no_tile(_request: Request, e: PeakError):
        return answer(e, 404)

    @app.exception_handler(HistoryError)
    async def _history_error(_request: Request, e: HistoryError):
        return answer(e, 404 if e.key == "error.history.no_step" else 500)

    @app.exception_handler(export.ExportError)
    async def _export_error(_request: Request, e: export.ExportError):
        client_error = e.key.startswith("error.export.bad_") or e.key in {
            "error.export.empty", "error.export.too_long_to_master",
            "error.export.master_memory",
        }
        return answer(e, 400 if client_error else 500)

    @app.exception_handler(music_report.MusicReportError)
    async def _music_report_error(_request: Request, e: music_report.MusicReportError):
        return answer(e, 400)

    @app.exception_handler(bgjobs.BackgroundJobError)
    async def _background_job_error(_request: Request, e: bgjobs.BackgroundJobError):
        return answer(e, 400)

    @app.exception_handler(profiler_module.ProfileRequestError)
    async def _profile_request(_request: Request, e: profiler_module.ProfileRequestError):
        return answer(e, 400)

    @app.exception_handler(profiler_module.ProfileBusyError)
    async def _profile_busy(_request: Request, e: profiler_module.ProfileBusyError):
        return answer(e, 409)

    @app.exception_handler(colab_transcribe.ColabError)
    async def _colab_error(_request: Request, e: colab_transcribe.ColabError):
        if e.key == "error.colab.not_signed_in":
            return answer(e, 409)
        client_error = e.key.startswith(("error.colab.bad_", "error.colab.signin_"))
        return answer(e, 400 if client_error else 500)

    @app.exception_handler(automix.AutomixError)
    async def _automix_error(_request: Request, e: automix.AutomixError):
        return answer(e, 400 if e.key.startswith("error.automix.bad_") else 500)

    @app.exception_handler(RecordError)
    async def _record_error(_request: Request, e: RecordError):
        return answer(e, e.status)

    @app.exception_handler(render_listen.RenderListenError)
    async def _render_listen_error(_request: Request, e: render_listen.RenderListenError):
        return answer(e, 409)

    @app.exception_handler(KuulasError)
    async def _other_error(_request: Request, e: KuulasError):
        if e.key.startswith(("error.paste.", "error.import_plan.", "error.chapters.",
                             "error.regions.", "error.edit_points.",
                             "error.locate.", "error.send_copy.")):
            return answer(e, 400)
        log.error(str(e))
        return answer(e, 500)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, e: RequestValidationError):
        detail = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                           for err in e.errors())
        return JSONResponse(error_body("error.server.bad_request", detail=detail),
                            status_code=400)

    def state() -> dict:
        with session.lock:
            h = session.history
            project = session.state
            return {"project": project.to_dict(), "head": h.head,
                    "can_undo": h.can_undo, "can_redo": h.can_redo,
                    "missing": session.store.missing(),
                    # The rendered mix the edit can be compared with (render_listen).
                    "render": {**render_listen.status(project),
                               "listening": engine_listening()}}

    def engine_listening() -> bool:
        # Only an engine that has the switch says so (test engines may have none, and
        # some refuse every attribute they do not define).
        return "listening" in dir(type(engine)) and bool(engine.listening)

    def state_response(extra: dict | None = None) -> JSONResponse:
        return JSONResponse({**state(), **(extra or {})})

    def require_media(media_id: str) -> None:
        try:
            session.state.media_item(media_id)
        except KeyError:
            raise UnknownIdError("error.edit.no_media", media_id=media_id) from None

    # -- the project -------------------------------------------------------

    @app.get("/api/state")
    def get_state():
        return state_response()

    @app.post("/api/edit")
    def post_edit(body: EditBody):
        if body.op in CLIPBOARD_EDITS:
            result = session.clipboard_edit(body.op, body.args, body.label)
            return state_response({"clipboard": result})
        session.edit(body.op, body.args, body.label, body.coalesce)
        return state_response()

    @app.post("/api/command")
    def post_command(body: CommandBody):
        try:
            session.command(body.name, body.args)
        except KuulasError as error:
            if error.key == "error.import.nhsx_failed":
                return answer(error, 400)
            raise
        if body.name == "import_nhsx":
            return state_response({"report": report_of(session.last_import_report)})
        if body.name == "save_backup":
            return state_response({"backup": session.last_backup.name})
        if body.name == "match_loudness":
            report = session.last_match_report
            return state_response({"match_report": {
                "matched": [{"clip_id": c, "measured": m, "gain_db": g}
                            for c, m, g in report.matched],
                "skipped": list(report.skipped)}})
        # What the UI's notice needs beside the state, by command.
        extra = {"set_music_level": lambda: {"music_level": session.last_music_level},
                 "level_blocks": lambda: {"block_level": session.last_block_level},
                 "resync": lambda: {"resync": session.last_resync},
                 "resync_from": lambda: {"resync": session.last_resync}}.get(body.name)
        return state_response(extra() if extra else None)

    # -- sync states (WP19a, R51; sync is knowledge only, WP83) ---------------------

    @app.get("/api/drift")
    def get_drift(cause: bool = False):
        """Clips in undecided drift in timeline order, with their offset in
        frames (and, with ``cause``, the history step that moved them)."""
        return JSONResponse({"drift": session.drift_list(cause)})

    @app.get("/api/sync")
    def get_sync():
        """Every drifting or free clip with its offset: what the badges draw."""
        return JSONResponse({"clips": session.sync_overview(),
                             "anchors": session.sync_anchors()})

    @app.post("/api/sync/preview")
    def post_sync_preview(body: CommandBody):
        """What resync / resync_from / send_home would move, without moving it."""
        return JSONResponse(session.sync_preview(body.name, body.args))

    @app.get("/api/partners")
    def get_partners(ids: str = ""):
        """The partners of each clip (``ids``: comma separated), for the dashed
        outline."""
        wanted = [i for i in ids.split(",") if i]
        return JSONResponse({"partners": session.partners_of(wanted)})

    @app.get("/api/sync-cause/{clip_id}")
    def get_sync_cause(clip_id: str):
        return JSONResponse({"cause": session.sync_cause(clip_id)})

    # -- the view memory (WP35) ----------------------------------------------
    # The user's view of this project (zoom, scroll, ...), kept outside the
    # project: no undo step, no change to its bytes.

    @app.get("/api/build")
    def get_build():
        """Which version and commit this is, for bug reports (build_info.py)."""
        return JSONResponse({"build": build_label()})

    @app.get("/api/profile")
    def get_profile():
        """The performance report recording: idle, running, done or failed."""
        return JSONResponse(perf_profiler.status())

    @app.post("/api/profile")
    def post_profile(body: ProfileBody):
        if body.action == "stop":
            perf_profiler.stop()
            perf_profiler.join(2.0)
            return JSONResponse(perf_profiler.status())
        if body.action != "start":
            raise BadRequestError("error.server.bad_request",
                                  detail=f"unknown action {body.action!r}")
        if body.interval is None:
            perf_profiler.start(body.seconds)
        else:
            perf_profiler.start(body.seconds, body.interval)
        return JSONResponse(perf_profiler.status(), status_code=202)

    def log_level_body() -> dict:
        return {"level": logsetup.current(), "setting": logsetup.level_setting(),
                "levels": list(logsetup.LEVELS),
                "from_environment": logsetup.parse(os.environ.get(logsetup.ENV, ""))}

    @app.get("/api/log-level")
    def get_log_level():
        """Help > Log level: the level in force, the saved choice and the options."""
        return JSONResponse(log_level_body())

    @app.post("/api/log-level")
    def post_log_level(body: LogLevelBody):
        level = logsetup.parse(body.level)
        if level is None:
            raise BadRequestError(
                "error.server.bad_request",
                detail=f"level must be one of {', '.join(logsetup.LEVELS)}")
        try:
            logsetup.save_level_setting(level)
        except OSError:
            log.warning(t("log.server.log_level_not_saved"))
        logsetup.apply(level)
        return JSONResponse(log_level_body())

    @app.get("/api/language")
    def get_language():
        """View > Language: the stored choice and the language in use now."""
        return JSONResponse({"setting": messages.language_setting(),
                             "language": messages.language()})

    @app.put("/api/language")
    def put_language(body: LanguageBody):
        try:
            messages.save_language_setting(body.setting)
        except ValueError:
            raise BadRequestError("error.server.bad_request",
                                  detail=body.setting) from None
        except OSError as e:
            raise BadRequestError("error.server.bad_request", detail=str(e)) from None
        messages.set_language(request_language(None, default_language))
        return JSONResponse({"setting": messages.language_setting(),
                             "language": messages.language()})

    @app.get("/api/view-memory")
    def get_view_memory():
        # The newer of this user's own record and the project's resume.json (the
        # position the other Mac left, through Dropbox).
        local = ViewMemory().get(session.package.manifest["id"])
        resume = read_resume(session.package.path)
        return JSONResponse({"view": merge_view(local, resume)})

    @app.put("/api/view-memory")
    def put_view_memory(body: ViewMemoryBody, now: bool = False):
        # ``now``: Mod+S and leaving the page; resume.json is then written at once
        # instead of waiting out its 5 s throttle.
        view = {**body.view, "saved_at": now_iso()}
        saved = True
        try:
            ViewMemory().put(session.package.manifest["id"], view)
        except ViewMemoryError as e:
            raise BadRequestError(e.key, **e.params) from None
        except OSError as e:
            # A convenience: say so in the log, do not fail the page.
            log.warning(t("log.view_memory.write_failed", error=str(e)))
            saved = False
        session.resume.remember(view, now=now)  # never raises
        return JSONResponse({"saved": saved})

    # -- the UI's remembered settings (user config folder, shared by all windows)

    @app.get("/api/prefs")
    def get_prefs():
        return {"prefs": ui_prefs.load()}

    @app.put("/api/prefs")
    def put_prefs(body: Annotated[dict[str, Any], Body()]):
        try:
            return {"prefs": ui_prefs.update(body.get("set"), body.get("remove"))}
        except ui_prefs.PrefsError as e:
            raise BadRequestError(e.key, **e.params) from None
        except OSError as e:
            raise BadRequestError("error.server.bad_request", detail=str(e)) from None

    # -- the clipboard (WP46) ------------------------------------------------
    # Cut and paste are edits and go through /api/edit (one undo step each);
    # copying changes no project, so it has its own route.

    @app.get("/api/clipboard")
    def get_clipboard():
        return JSONResponse({"entries": session.clipboard_list()})

    @app.get("/api/clipboard/shared")
    def get_clipboard_shared():
        return JSONResponse({"entries": session.clipboard_shared()})

    @app.get("/api/clipboard/projects")
    def get_clipboard_projects():
        return JSONResponse({"projects": session.clipboard_projects()})

    @app.get("/api/clipboard/project")
    def get_clipboard_project(path: str = ""):
        # Read-only: the other project's clipboard.json and nothing else.
        return JSONResponse(session.clipboard_project(path))

    @app.post("/api/clipboard/adopt")
    def post_clipboard_adopt(body: AdoptBody):
        entry = session.clipboard_adopt(body.entry, body.from_project)
        return JSONResponse({"entry": entry, "entries": session.clipboard_list()})

    @app.post("/api/clipboard/{entry_id}/share")
    def post_clipboard_share(entry_id: str, body: ShareBody):
        session.clipboard_share(entry_id, body.shared)
        return JSONResponse({"entries": session.clipboard_list(),
                             "shared": session.clipboard_shared()})

    @app.post("/api/clipboard/copy")
    def post_clipboard_copy(body: CopyBody):
        out = session.clipboard_copy(clip_ids=body.clip_ids, start=body.start,
                                     end=body.end, track_ids=body.track_ids,
                                     name=body.name)
        return JSONResponse({**out, "entries": session.clipboard_list()})

    @app.post("/api/clipboard/clear-old")
    def post_clipboard_clear_old(body: ClearOldBody):
        removed = session.clipboard_clear_old(body.keep)
        return JSONResponse({"removed": removed, "entries": session.clipboard_list()})

    @app.post("/api/clipboard/{entry_id}/pin")
    def post_clipboard_pin(entry_id: str, body: PinBody):
        session.clipboard_pin(entry_id, body.pinned)
        return JSONResponse({"entries": session.clipboard_list()})

    @app.post("/api/clipboard/{entry_id}/rename")
    def post_clipboard_rename(entry_id: str, body: RenameBody):
        session.clipboard_rename(entry_id, body.name)
        return JSONResponse({"entries": session.clipboard_list()})

    @app.post("/api/clipboard/{entry_id}/preview")
    def post_clipboard_preview(entry_id: str, body: ClipboardPreviewBody | None = None):
        # Plays a temporary project made from the entry; the real one is not
        # touched, nothing is committed. Playing again or Stop ends it. Unless
        # switched off it is turned down to the project's level and limited
        # (WP82); `attenuation_db` says by how much (0 or less).
        limit = True if body is None else body.limit
        project, missing, gain = session.clipboard_preview(entry_id, limit)
        seq = None
        if project is not None:
            engine.play_preview(project, limit=limit)
            # The transport version it started at: the page drops an older "ended".
            status = engine.status()
            seq = newest_seq(status.get("seq"), status.get("preview_seq"))
        return JSONResponse({"started": project is not None, "missing": missing,
                             "attenuation_db": gain, "seq": seq})

    @app.post("/api/clipboard/preview/stop")
    def post_clipboard_preview_stop():
        # The chip's Stop: ends the preview only. Mixed into the timeline it is a
        # voice that goes away and the timeline plays on.
        engine.stop_preview()
        return JSONResponse({"stopped": True})

    @app.post("/api/render-listen")
    def post_render_listen(body: RenderListenBody):
        # The A/B switch: the last automixer render plays in place of the edit, at its
        # place on the timeline, while the edit still sounds as it did then (409 and a
        # translated reason otherwise). The project is never touched.
        if body.on:
            render_listen.start(session, engine)
        else:
            render_listen.stop(engine)
        return state_response()

    @app.delete("/api/clipboard/{entry_id}")
    def delete_clipboard_entry(entry_id: str):
        session.clipboard_delete(entry_id)
        return JSONResponse({"entries": session.clipboard_list()})

    def moved_info(direction: str, info) -> dict | None:
        """What an undo or redo did, for the toast: the step it passed over and whether
        a session marker (opened / closed) lay in between."""
        if info is None:
            return None
        step = info.step or {}
        return {"direction": direction, "crossed_marker": info.marker is not None,
                "marker": info.marker,
                "step": {"id": step.get("id"), "label": step.get("label"),
                         "created": step.get("created_utc")}}

    @app.post("/api/undo")
    def post_undo():
        return state_response({"moved": moved_info("undo", session.undo())})

    @app.post("/api/redo")
    def post_redo():
        return state_response({"moved": moved_info("redo", session.redo())})

    @app.post("/api/export")
    def post_export(body: Annotated[dict[str, Any], Body()]):
        return state_response({"export": session.export(body)})

    @app.post("/api/export-tracks", status_code=202)
    def post_export_tracks(body: Annotated[dict[str, Any], Body()]):
        return JSONResponse({"jobs": session.export_tracks(body)}, status_code=202)

    @app.post("/api/export-mix", status_code=202)
    def post_export_mix(body: Annotated[dict[str, Any], Body()]):
        return JSONResponse({"jobs": session.export_mix(body)}, status_code=202)

    @app.post("/api/automix", status_code=202)
    def post_automix(body: Annotated[dict[str, Any], Body()]):
        return JSONResponse({"jobs": session.automix(body)}, status_code=202)

    # Transcription on Colab (WP78): the tool's command, folder and options.
    @app.get("/api/settings/colab")
    def get_colab_settings():
        stored = colab_transcribe.load_settings()
        return {"settings": stored, "resolved": colab_transcribe.resolve_settings(stored)}

    # Signing in to Google for Colab (interactive, so never inside a detached job).
    signin = colab_signin.SigninFlow()

    @app.get("/api/colab/signin")
    def get_colab_signin():
        return signin.status()

    @app.post("/api/colab/signin", status_code=202)
    def post_colab_signin():
        settings = colab_transcribe.resolve_settings(colab_transcribe.load_settings())
        signin.start(settings["command"], settings["cwd"])
        return JSONResponse(signin.status(), status_code=202)

    @app.post("/api/colab/signin/code")
    def post_colab_signin_code(body: Annotated[dict[str, Any], Body()]):
        code = body.get("code")
        signin.submit_code(code if isinstance(code, str) else "")
        return signin.status()

    @app.delete("/api/colab/signin")
    def delete_colab_signin():
        signin.cancel()
        return signin.status()

    @app.put("/api/settings/colab")
    def put_colab_settings(body: Annotated[dict[str, Any], Body()]):
        stored = colab_transcribe.save_settings(body)
        return {"settings": stored, "resolved": colab_transcribe.resolve_settings(stored)}

    @app.post("/api/auto-silence/preview", status_code=202)
    def post_auto_silence_preview(body: Annotated[dict[str, Any], Body()]):
        # What Auto-Silence with these options would close; changes nothing.
        return JSONResponse({"jobs": session.auto_silence_preview(body)}, status_code=202)

    # -- the Auto-Silence live preview (Track > Auto > Auto-Silence options…) ----
    # The panel measures once (a job), asks for ranges on every control change
    # (decided here in milliseconds) and plays them through the engine's
    # listening overlay, never committed until Accept. ``seq`` (the panel's,
    # rising) keeps an older answer that finishes late from replacing the
    # overlay of a newer one, or from bringing it back after Close.
    overlay_lock = threading.Lock()
    overlay_seq = [-math.inf]

    def silence_overlay(ranges: dict | None, seq: object, *, close: bool = False) -> None:
        plain = isinstance(seq, int | float) and not isinstance(seq, bool)
        number = seq if plain else None
        with overlay_lock:
            if number is not None:
                if number < overlay_seq[0] or (number == overlay_seq[0] and not close):
                    return
                overlay_seq[0] = number
            engine.set_silence_overlay(ranges)

    @app.post("/api/silence/measure")
    def post_silence_measure():
        # Ready at once when the speech audio is already measured; else the job.
        return JSONResponse(session.silence_measure())

    @app.post("/api/silence/learn", status_code=202)
    def post_silence_learn(body: Annotated[dict[str, Any], Body()]):
        """Calculate Auto-Silence values from the selected clips: a job, no commit."""
        return JSONResponse(session.silence_learn(body), status_code=202)

    @app.post("/api/silence/ranges")
    def post_silence_ranges(body: Annotated[dict[str, Any], Body()]):
        try:
            out = session.silence_preview_ranges(body)
        except SilenceNotMeasuredError:
            silence_overlay(None, body.get("seq"))
            raise
        silence_overlay({row["track_id"]: row["ranges"] for row in out["tracks"]},
                        body.get("seq"))
        return JSONResponse(out)

    @app.post("/api/silence/accept")
    def post_silence_accept(body: Annotated[dict[str, Any], Body()]):
        session.silence_accept(body)
        silence_overlay(None, body.get("seq"), close=True)
        return JSONResponse(state())

    @app.post("/api/silence/close")
    def post_silence_close(body: Annotated[dict[str, Any], Body()]):
        # Cancel / Close / Esc: the overlay goes, nothing is committed.
        silence_overlay(None, body.get("seq"), close=True)
        return JSONResponse({"closed": True})

    @app.post("/api/music-level/measure", status_code=202)
    def post_music_level_measure(body: Annotated[dict[str, Any], Body()]):
        # Set music level: measure the speech and the beds; changes nothing.
        return JSONResponse({"jobs": session.music_level_measure(body)}, status_code=202)

    @app.post("/api/duck-music/measure", status_code=202)
    def post_duck_music_measure(body: Annotated[dict[str, Any], Body()]):
        # Duck music: find speech intervals in a cancellable background job.
        return JSONResponse({"jobs": session.duck_music_measure(body)}, status_code=202)

    @app.post("/api/block-level/measure", status_code=202)
    def post_block_level_measure(body: Annotated[dict[str, Any], Body()]):
        # Level blocks: measure each speaker's blocks and loud spots; changes nothing.
        return JSONResponse({"jobs": session.block_level_measure(body)}, status_code=202)

    @app.get("/api/plugins")
    def get_plugins(refresh: bool = False):
        # The installed audio plug-ins (names only, never loaded) for the automixer
        # dialog's suggestions; the scan is cached, ?refresh=1 scans again.
        remote = automix.resolve_settings(automix.load_settings())["remote"]
        if remote["enabled"]:
            # The Mac that renders has its own plug-ins; ask it (None: ssh failed, the
            # dialog then shows a plain text field with a hint).
            try:
                found = automix_remote.list_plugins(remote)
            except automix_remote.RemoteError:
                found = None
            return {"plugins": found or [], "remote": remote["host"],
                    "remote_failed": found is None}
        return {"plugins": plugins.list_plugins(refresh=refresh)}

    @app.get("/api/automix/live")
    def get_automix_live():
        # The lines the automixer has printed so far (the newest run's, kept after it).
        return session.automix_live()

    @app.get("/api/settings/automixer")
    def get_automixer_settings():
        stored = automix.load_settings()
        # default_output_dir is for display only (run() works out the same folder itself).
        resolved = automix.resolve_settings(stored)
        tracks = session.state.to_dict()["tracks"]
        return {"settings": stored, "resolved": resolved,
                "default_output_dir": str(session.package.path.parent),
                "option_specs": automix.option_specs(),
                # What Kuulas already did that the automixer would otherwise redo.
                "done_in_kuulas": automix.done_in_kuulas(session.state),
                "balance_cap": balance_cap(tracks),
                "balance_hand_adjusted": hand_adjusted(tracks),
                # What the installed tool accepts (its --help, cached; never an error).
                "capabilities": _automix_capabilities(resolved)}

    def _automix_capabilities(resolved: dict[str, Any]) -> dict[str, bool]:
        remote = resolved["remote"]
        if not remote["enabled"]:
            return {**automix.capabilities(resolved["command"], resolved["cwd"]),
                    "keep_music_level": automix.supports_keep_music_level(
                        resolved["command"], resolved["cwd"])}
        try:  # the tool that will render is the one on the other Mac
            automix_remote.check(remote)
        except automix_remote.RemoteError:
            return {}
        wrapped = automix_remote.runner(remote, automix.run_process)
        return {**automix.remote_capabilities(remote),
                "keep_music_level": automix.supports_keep_music_level(
                    remote["command"], remote["cwd"], run_process=wrapped,
                    scope=remote["host"])}

    @app.post("/api/settings/automixer/remote-test")
    def post_automixer_remote_test(body: Annotated[dict[str, Any], Body()]):
        # Test connection: the fields of the dialog (saved or not) are checked one by
        # one; every check says ok or why not. Never hangs, never asks for a password.
        given = body.get("remote")
        stored = automix.load_settings().get("remote")
        merged = {**(stored if isinstance(stored, dict) else {}),
                  **(given if isinstance(given, dict) else {})}
        gated = {key: automix.OPTIONS[key]["flag"] for key in automix.GATED}
        return automix_remote.connection_test({**merged, "enabled": True}, gated)

    @app.put("/api/settings/automixer")
    def put_automixer_settings(body: Annotated[dict[str, Any], Body()]):
        stored = automix.save_settings(body)
        return {"settings": stored, "resolved": automix.resolve_settings(stored)}

    @app.post("/api/project/new")
    def post_new_project(body: Annotated[dict[str, Any], Body()]):
        """File > New project... in a plain browser (WP74): make the empty project at
        ``parent``/``name``.kuulas and open it in a new tab."""
        folder = new_project.create(body.get("parent"), body.get("name"))
        new_project.start_window(str(folder))
        return {"path": str(folder)}

    # -- series: settings shared across episodes (docs/design/SERIES.md) ----------

    @app.get("/api/series")
    def get_series():
        return series_actions.status(session)

    @app.post("/api/series/status")
    def post_series_status(body: Annotated[dict[str, Any], Body()]):
        """The status with the Auto-Silence options the page has now."""
        return series_actions.status(session, body.get("auto_silence"))

    @app.post("/api/series/save")
    def post_series_save(body: Annotated[dict[str, Any], Body()]):
        got = series_actions.save_defaults(session, name=body.get("name"),
                                           auto_silence=body.get("auto_silence"),
                                           series_id=body.get("series_id"))
        return state_response({"series": got})

    @app.post("/api/series/apply")
    def post_series_apply():
        got = series_actions.apply(session)
        return state_response({"series": got, "settings": got["settings"]})

    @app.post("/api/series/attach")
    def post_series_attach(body: Annotated[dict[str, Any], Body()]):
        return state_response({"series": series_actions.attach(session,
                                                               body.get("series_id"))})

    @app.post("/api/series/detach")
    def post_series_detach():
        return state_response({"series": series_actions.detach(session)})

    @app.post("/api/series/rename")
    def post_series_rename(body: Annotated[dict[str, Any], Body()]):
        return state_response({"series": series_actions.rename(session,
                                                               body.get("name"))})

    @app.post("/api/series/new-episode")
    def post_series_new_episode(body: Annotated[dict[str, Any], Body()]):
        """A new project from the series. ``open`` (a plain browser): start a tab on
        it; the desktop window opens it itself through its bridge."""
        folder = series_actions.new_episode(body.get("parent"), body.get("name"),
                                            body.get("series_id"))
        if body.get("open") is True:
            new_project.start_window(str(folder))
        return {"path": str(folder)}

    @app.post("/api/series/music/add")
    def post_series_music_add(body: Annotated[dict[str, Any], Body()]):
        return series_actions.music_add(session, body.get("clip_ids"), body.get("name"))

    @app.post("/api/series/music/clipboard")
    def post_series_music_clipboard():
        return series_actions.music_to_clipboard(session)

    # The Clipboard's series shelf (docs/design/CLIPBOARD-SHELVES.md): the series music.
    @app.get("/api/series/shelf")
    def get_series_shelf():
        return series_actions.shelf_list(session)

    @app.post("/api/series/shelf/add")
    def post_series_shelf_add(body: Annotated[dict[str, Any], Body()]):
        return series_actions.shelf_add(session, body.get("entry_id"))

    @app.post("/api/series/shelf/remove")
    def post_series_shelf_remove(body: Annotated[dict[str, Any], Body()]):
        return series_actions.shelf_remove(session, body.get("entry_id"))

    @app.post("/api/series/shelf/adopt")
    def post_series_shelf_adopt(body: Annotated[dict[str, Any], Body()]):
        entry = series_actions.shelf_adopt(session, body.get("entry_id"))
        return {"entry": entry, "entries": session.clipboard_list()}

    @app.post("/api/series/music/place")
    def post_series_music_place():
        return state_response({"placed": series_actions.music_place(session)})

    @app.post("/api/project/open")
    def post_open_project(body: Annotated[dict[str, Any], Body()]):
        """File > Open project... in a plain browser (WP74): the same path rule as the
        clipboard browser, then a new tab on it."""
        folder = clipboard_browse.project_folder(body.get("path"))
        new_project.start_window(str(folder))
        return {"path": str(folder)}

    @app.get("/api/media/status")
    def get_media_status():
        """File > Locate media… (WP39): what is missing, and what is only partly here."""
        return JSONResponse(session.media_status())

    @app.post("/api/media/locate")
    def post_locate_media(body: Annotated[dict[str, Any], Body()]):
        """Look under a folder for the missing media, by SHA-256; say what was found."""
        return JSONResponse(session.locate_media(body.get("folder")))

    @app.post("/api/media/replace-check")
    def post_replace_check(body: Annotated[dict[str, Any], Body()]):
        """Locate / Relink media on a clip, step one: import the chosen file and say
        what replacing the clip's media by it means. The edit: ``replace_clip_media``."""
        return JSONResponse(
            session.check_replace_media(body.get("media_id"), body.get("path")))

    @app.get("/api/send-copy/plan")
    def get_send_copy_plan():
        """File > Send a copy… (WP32): what each media choice would carry."""
        return JSONResponse(session.send_copy_plan())

    @app.post("/api/send-copy")
    def post_send_copy(body: Annotated[dict[str, Any], Body()]):
        """Write a copy of the project into a folder: no audio, the used parts or all."""
        media = body.get("media", "used")
        return JSONResponse(session.send_copy(body.get("folder"), media))

    @app.get("/api/export-folder")
    def get_export_folder():
        return session.export_folder_hint()

    @app.get("/api/export-settings")
    def get_export_settings():
        return session.export_settings()

    @app.get("/api/export-formats")
    def get_export_formats():
        return [{"id": f.id, "label": t(f.label_key), "ext": f.ext,
                 "lossless": f.lossless} for f in export_formats.available_formats()]

    @app.post("/api/export-regions")
    def post_export_regions(body: Annotated[dict[str, Any], Body()]):
        return JSONResponse({"jobs": session.export_regions(body)})

    @app.get("/api/chapters")
    def get_chapters(style: str = "text"):
        content = session.chapters(style)
        if style == "json":
            return Response(content=content, media_type="application/json",
                            headers={"Content-Disposition": export_names.disposition(
                                session.download_name("chapters.json"))})
        return Response(content=content, media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": export_names.disposition(
                            session.download_name("chapters.txt"))})

    @app.get("/api/loudness-curve")
    def get_loudness_curve():
        # Measured outside the session lock (Session.loudness_curve); cached by content.
        try:
            return JSONResponse(session.loudness_curve())
        except offload.SupersededError:
            # A newer request replaced it (the UI aborted this one already).
            return JSONResponse({"superseded": True}, status_code=409)

    @app.get("/api/stats")
    def get_stats(format: str = "json"):
        # WP70: the snapshot is taken under the lock, the counting is not (Session.stats).
        described = project_stats.describe(session.stats())
        if format == "text":
            return PlainTextResponse(described["text"])
        if format == "file":
            # "Save as JSON": the numbers alone, as a file.
            return JSONResponse(described["stats"], headers={
                "Content-Disposition": 'attachment; filename="statistics.json"'})
        return JSONResponse(described)

    @app.get("/api/music-report")
    def get_music_report(format: str = "json", download: bool = False):
        if format not in ("json", "csv", "html"):
            raise music_report.MusicReportError("error.music_report.bad_format",
                                                format=format)
        if format == "csv":
            content = session.music_report(format="csv")
            disposition = export_names.disposition(
                session.download_name("music-report.csv"))
            return Response(content=content, media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": disposition})
        if format == "html":
            content = session.music_report(format="html")
            if not download:
                return HTMLResponse(content=content)
            return HTMLResponse(content=content, headers={
                "Content-Disposition": export_names.disposition(
                    session.download_name("music-report.html"))})
        rows = session.music_report(format="json")
        return JSONResponse({"rows": rows})

    @app.get("/api/subtitles")
    def get_subtitles(format: str):
        if format not in ("srt", "vtt"):
            raise SubtitlesError("error.subtitles.bad_format", format=format)
        content = session.subtitles(format)
        if format == "srt":
            media_type = "application/x-subrip"
            disposition = export_names.disposition(session.download_name("subtitles.srt"))
        else:
            media_type = "text/vtt"
            disposition = export_names.disposition(session.download_name("subtitles.vtt"))
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": disposition})

    @app.get("/api/transcript-text")
    def get_transcript_text(format: str):
        if format not in ("txt", "md"):
            raise TranscriptTextError("error.transcript_text.bad_format", format=format)
        content = session.transcript_text(format)
        if format == "txt":
            media_type = "text/plain; charset=utf-8"
            disposition = export_names.disposition(
                session.download_name("transcript.txt"))
        else:
            media_type = "text/markdown; charset=utf-8"
            disposition = export_names.disposition(session.download_name("transcript.md"))
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": disposition})

    @app.get("/api/narration-script")
    def get_narration_script(format: str):
        if format not in ("txt", "md"):
            raise NarrationScriptError("error.narration_script.bad_format", format=format)
        content = session.narration_script_text(format)
        media_type = ("text/plain; charset=utf-8" if format == "txt"
                      else "text/markdown; charset=utf-8")
        return Response(content=content, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="narration-script.{format}"'})

    @app.post("/api/cut-preview")
    def post_cut_preview(body: CutPreviewBody):
        return session.cut_preview(body.words)

    @app.get("/api/source-map")
    def get_source_map(media: str):
        return session.source_map(media)

    # -- cut candidates (WP18) ------------------------------------------------
    # Detecting, deciding, applying and marking are commands (/api/command:
    # candidates_detect, candidate_set_state, candidate_apply, candidate_mark),
    # each one undo step; these two only read.

    @app.get("/api/candidates")
    def get_candidates(state: str | None = None):
        """Every candidate (or those in ``state``) with timeline frames and
        recording flicks, and the counts per state."""
        return session.candidates(state)

    @app.get("/api/candidates/{candidate_id}/preview")
    def get_candidate_preview(candidate_id: str, mode: str = "soft"):
        """"Play as if cut": ``from``, ``to`` and the frame ranges to ``skip``."""
        return session.candidate_preview(candidate_id, mode)

    @app.post("/api/restore")
    def post_restore(body: RestoreBody):
        session.restore(str(body.node))
        # The UI context of the restored step belongs to WP8; none is stored yet.
        return state_response({"context": None})

    @app.get("/api/history")
    def get_history(limit: int | None = None, before: str | None = None,
                    saved: int = 0):
        """Without ``limit`` or ``before``: every step, oldest first (the old shape).
        With them: a page, newest first, for the History panel."""
        with session.lock:
            h = session.history
            if limit is None and before is None:
                marks = h.checkpoint_map()
                nodes = [{**n, "checkpoint": marks.get(n["id"])} for n in h.nodes()]
                return JSONResponse({"nodes": nodes, "head": h.head})
            limit = HISTORY_PAGE if limit is None else limit
            if not 1 <= limit <= HISTORY_PAGE_MAX:
                raise BadRequestError("error.server.bad_request",
                                      detail=f"limit: 1..{HISTORY_PAGE_MAX}")
            rows = h.nodes_page(limit + 1, before, saved=bool(saved))
            marks = h.checkpoint_map()
            more = len(rows) > limit
            lineage = h.lineage()
            nodes = [{"id": r["id"], "parent": r["parent"], "label": r["label"],
                      "created": r["created"], "author": r["author"],
                      "op": r["op"].get("name"), "is_marker": h.is_marker(r),
                      "marker": (r["op"].get("args") or {}).get("kind")
                      if h.is_marker(r) else None,
                      "is_head": r["id"] == h.head, **lineage[r["id"]],
                      "checkpoint": marks.get(r["id"])}
                     for r in rows[:limit]]
            return JSONResponse({"nodes": nodes, "head": h.head, "more": more,
                                 "can_undo": h.can_undo, "can_redo": h.can_redo})

    @app.get("/api/jobs")
    def get_jobs():
        # Background transcription jobs (WP79) live in the project, not in this process.
        return JSONResponse({"jobs": [*session.jobs.list(), *session.background_jobs()]})

    @app.get("/api/jobs/notices")
    def get_job_notices():
        # What the background jobs did since the last call (a result added, a failure),
        # told once. Its own route: the transcript panel polls /api/jobs and must not
        # swallow them.
        return JSONResponse({"notices": session.drain_notices()})

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str):
        if session.is_background(job_id):
            session.cancel_background(job_id)
        elif any(job["id"] == job_id for job in session.jobs.list()):
            session.jobs.cancel(job_id)
        else:
            raise UnknownIdError("error.jobs.unknown", job_id=job_id)
        return JSONResponse({"jobs": [*session.jobs.list(), *session.background_jobs()]})

    @app.post("/api/jobs/restart-interrupted", status_code=202)
    def restart_interrupted_jobs():
        return JSONResponse({"restarted": session.restart_interrupted()}, status_code=202)

    @app.post("/api/jobs/{job_id}/restart", status_code=202)
    def restart_job(job_id: str):
        if not session.is_background(job_id):
            raise UnknownIdError("error.jobs.unknown", job_id=job_id)
        session.restart_background(job_id)
        return JSONResponse({"jobs": [job_id]}, status_code=202)

    @app.post("/api/transcribe", status_code=202)
    def post_transcribe(body: TranscribeBody):
        if not body.media_ids:
            raise BadRequestError("error.server.bad_request", detail="media_ids")
        if body.backend not in {"local", "colab"}:
            raise BadRequestError("error.server.bad_request", detail="backend")
        if body.backend == "colab" and not colab_signin.signed_in():
            # The sign-in is interactive; a detached worker could only hang on it.
            raise colab_transcribe.ColabError("error.colab.not_signed_in")
        if session.read_only:
            holder = session.package.locked_by or {}
            raise BadRequestError("error.history.read_only",
                                  host=holder.get("host", "?"))
        for media_id in body.media_ids:
            require_media(media_id)
        try:
            job_ids = session.transcribe(body.media_ids, body.model, body.language,
                                         body.backend, force=body.force)
        except MediaError as exc:
            return answer(exc, 400)
        return JSONResponse({"jobs": job_ids}, status_code=202)

    # -- bringing audio in -------------------------------------------------

    def report_of(results: list[ImportResult]) -> list[dict]:
        out = []
        for r in results:
            error = None
            if r.error is not None:
                error = (error_body(r.error.key, **r.error.params)
                         if isinstance(r.error, KuulasError)
                         else error_body("error.media.failed", name=r.path.name,
                                         error=str(r.error)))["error"]
            out.append({
                "path": str(r.path), "ok": r.ok,
                "media": r.media.id if r.media else None, "error": error,
                "warnings": [error_body(n.key, **n.params)["error"]
                             for n in r.warnings]})
        return out

    def imported(paths: list[str], copy: bool, *,
                 mode: str | None = None, order: str = "given",
                 track_naming: str = "file", start_frame: int = 0,
                 onto_track: str | None = None) -> JSONResponse:
        try:
            _, results = session.import_media_report(
                paths, copy=copy, mode=mode, order=order,
                track_naming=track_naming, start_frame=start_frame,
                onto_track=onto_track,
            )
        except MediaError as e:
            # Nothing came in: say why, file by file, so the UI can show each.
            return JSONResponse({**error_body(e.key, **e.params),
                                 "report": report_of(session.last_import_report)},
                                status_code=500)
        return state_response({"report": report_of(results),
                               "stereo": session.last_import_stereo})

    @app.post("/api/import")
    def post_import(body: ImportBody):
        return imported(body.paths, body.copy_files, mode=body.mode,
                        order=body.order, track_naming=body.track_naming,
                        start_frame=body.start_frame, onto_track=body.onto_track)

    @app.post("/api/upload")
    def post_upload(
        files: Annotated[list[UploadFile] | None, File()] = None,
        mode: Annotated[str | None, Form()] = None,
        order: Annotated[str, Form()] = "given",
        track_naming: Annotated[str, Form()] = "file",
        start_frame: Annotated[int, Form()] = 0,
        onto_track: Annotated[str | None, Form()] = None,
    ):
        if not files:
            raise BadRequestError("error.server.bad_request", detail="files")
        folder = session.package.path / "uploads"
        folder.mkdir(exist_ok=True)
        saved = [str(save_upload(folder, f)) for f in files]
        return imported(saved, copy=False, mode=mode, order=order,
                        track_naming=track_naming, start_frame=start_frame,
                        onto_track=onto_track)

    @app.post("/api/placeholder-take")
    def post_placeholder_take(
        file: Annotated[UploadFile, File()],
        placeholder_id: Annotated[str, Form()],
        offset: Annotated[int, Form()] = 0,
    ):
        """A browser's take (WP43): the file is saved like an upload and replaces
        the placeholder in one step. The desktop window links by path through
        ``/api/command`` ``placeholder_take`` instead."""
        folder = session.package.path / "uploads"
        folder.mkdir(exist_ok=True)
        path = save_upload(folder, file)
        session.command("placeholder_take", {"placeholder_id": placeholder_id,
                                             "path": str(path), "offset": offset})
        return state_response()

    # -- waveforms -----------------------------------------------------------

    @app.get("/api/peaks/{media_id}/{level}/{tile}")
    def get_peak_tile(media_id: str, level: int, tile: int, request: Request):
        require_media(media_id)
        body, etag = session.store.peak_tile(media_id, level, tile)
        tag = f'"{etag}"'
        headers = {"ETag": tag, "Cache-Control": TILE_CACHE}
        if etag_matches(request.headers.get("if-none-match"), tag):
            return Response(status_code=304, headers=headers)
        return Response(body, media_type="application/octet-stream", headers=headers)

    # -- words ---------------------------------------------------------------

    @app.get("/api/words")
    def get_words():
        words = session.timeline_words()
        body: dict[str, Any] = {"words": words}
        # The names of the people the words refer to, so the transcript can head a
        # paragraph with "Anna" and not an id; absent when nobody is mapped.
        used = {w["person"] for w in words if w.get("person")}
        names = {p.id: p.name for p in session.people() if p.id in used}
        if names:
            body["people"] = names
        return JSONResponse(body)

    @app.get("/api/edit-points")
    def get_edit_points(mode: str, track: str | None = None):
        """The frames Tab jumps between (WP19i): ``mode`` edges, transients or
        words, on one track or on every audible one."""
        return JSONResponse({"points": session.edit_points(mode, track)})

    @app.post("/api/transcript/{media_id}")
    def post_transcript(media_id: str, data: Annotated[Any, Body()]):
        require_media(media_id)
        try:
            words = transcribe.parse(data)
        except (AttributeError, TypeError, ValueError):
            raise EditError("error.transcript.unreadable") from None
        if not words:
            raise EditError("error.transcript.empty")
        session.set_transcript(media_id, words,
                               t("history.transcript", media_id=media_id))
        return state_response()

    @app.put("/api/word")
    def put_word(body: WordBody):
        require_media(body.media)
        session.correct_word(body.media, body.index, body.w)
        return state_response()

    # -- transport -----------------------------------------------------------

    # -- recording (WP12a): the recorder is its own program; see record_session ------

    def need_recorder():
        if recorder is None:
            raise RecordError("error.record.unavailable", status=503)
        return recorder

    @app.get("/api/record/status")
    def record_status(channels: int = 1):
        if recorder is None:
            return {"available": False, "recording": False, "state": "idle",
                    "ours": False, "pending": [], "notices": []}
        return recorder.status(channels)

    @app.get("/api/record/devices")
    def record_devices():
        return {"devices": need_recorder().devices()}

    @app.post("/api/record/start")
    def record_start(body: RecordStartBody):
        rec = need_recorder()
        # No listening while recording (owner, 2026-10-19): monitoring is the interface's.
        engine.stop()
        return rec.start(device=body.device, channels=body.channels, channel=body.channel,
                         track_id=body.track_id, name=body.name, at=body.at)

    @app.post("/api/record/arm")
    def record_arm(body: RecordArmBody):
        # Also the keepalive: the page repeats it, and the recorder lets the microphone
        # go by itself when it stops coming.
        return need_recorder().arm(device=body.device, channels=body.channels,
                                   channel=body.channel, preroll_s=body.preroll_s)

    @app.post("/api/record/disarm")
    def record_disarm():
        return need_recorder().disarm()

    @app.post("/api/record/stop")
    def record_stop(body: RecordStopBody):
        result = need_recorder().stop(body.mode, body.held_ms)
        return state_response({"record": result})

    @app.post("/api/record/import")
    def record_import(body: RecordImportBody):
        rec = need_recorder()
        imported = [r for r in (rec.import_take(take) for take in body.takes) if r]
        return state_response({"imported": imported, "pending": rec.pending()})

    @app.get("/api/transport")
    def get_transport():
        return JSONResponse(engine.status())

    @app.post("/api/transport")
    def post_transport(body: TransportBody):
        action = body.action
        if action in ("seek", "scrub") and body.at is None:
            raise BadRequestError("error.server.missing_field", field="at")
        recording = recorder is not None and recorder.recording_now()
        if action in ("play", "scrub") and recording:
            # No listening while recording (owner, 2026-10-19): the interface monitors.
            raise RecordError("error.record.no_playback", status=409)
        if action == "play":
            # Checked here too, so a bad list is a 400 whatever the engine.
            skip = check_skip(body.skip)
            loop = (None if body.loop is None
                    else check_loop(body.loop, skip, getattr(engine, "rate", 48000)))
            engine.play(body.at, body.until, rate=body.speed,
                        preserve_pitch=body.preserve_pitch, skip=skip, loop=loop)
        elif action == "rate":
            # Fast listening's stepless speed while it plays (WP26): the
            # stretcher takes it at its next hop. Not playing fast: nothing.
            engine.set_rate(body.speed)
        elif action == "stop":
            engine.stop()
        elif action == "seek":
            engine.seek(body.at)
        elif action == "scrub":
            priority.GATE.note_input(scrub=True)
            engine.scrub(body.at)
        else:
            raise BadRequestError("error.server.bad_transport", action=action)
        status = engine.status()
        # The playhead's new anchor goes out now, not at the next reading.
        hub.publish(anchor_message(status, time.monotonic()))
        return JSONResponse(status)

    # -- push ------------------------------------------------------------------

    @app.websocket("/api/live")
    async def live(ws: WebSocket):
        await ws.accept()
        messages.set_language(request_language(ws.headers.get("accept-language"),
                                               default_language))
        queue: asyncio.Queue = asyncio.Queue()
        hub.add(asyncio.get_running_loop(), queue)

        async def hear_disconnect() -> None:
            # Without reading, a client that went away is never noticed while
            # nothing is being sent. A ping is answered with a pong (its server
            # time is stamped as it goes out): the page's clock offset.
            while True:
                text = await ws.receive_text()
                with contextlib.suppress(ValueError, TypeError, AttributeError):
                    asked = json.loads(text)
                    if asked.get("type") == "ping":
                        queue.put_nowait({"type": "pong", "c": asked.get("c")})

        def clipboard_stamp() -> tuple:
            return session.clipboard.stamp(), session.shared_clipboard.stamp()

        async def push() -> None:
            await ws.send_json({"type": "hello", "head": session.history.head})
            initial_jobs = session.jobs.list()
            await ws.send_json({"type": "jobs", "jobs": initial_jobs})
            last_jobs = tuple((job["id"], job["progress"], job["state"], job["error"])
                              for job in initial_jobs)
            last_notice = 0
            last_meter, meter_on = -math.inf, False
            # The newest transport version sent (from a reading or a request),
            # what the last anchor said, and when it went out.
            last_seq, last_shape, last_anchor = None, None, -math.inf
            last_preview, last_preview_at = None, -math.inf

            async def send(message: dict) -> None:
                nonlocal last_seq
                if message.get("type") == "pong":
                    message = {**message, "s": time.monotonic()}
                elif message.get("type") == "anchor":
                    if not newer_seq(message["seq"], last_seq):
                        return  # read before a change already sent: stale
                    if message["seq"] is not None:
                        last_seq = message["seq"]
                await ws.send_json(message)

            # The project's clipboard and the shared one are files other windows
            # write too: when a stamp changes (our own writes too, which only
            # costs a re-read), say so.
            last_stamp = clipboard_stamp()
            next_poll = time.monotonic()
            while True:
                wait = max(0.0, next_poll - time.monotonic())
                with contextlib.suppress(TimeoutError):  # nothing to send yet
                    await send(await asyncio.wait_for(queue.get(), wait))
                if time.monotonic() < next_poll:
                    continue
                current_jobs = session.jobs.list()
                signature = tuple((job["id"], job["progress"], job["state"], job["error"])
                                  for job in current_jobs)
                if signature != last_jobs:
                    await ws.send_json({"type": "jobs", "jobs": current_jobs})
                    last_jobs = signature
                stamp = clipboard_stamp()
                if stamp != last_stamp:
                    last_stamp = stamp
                    await ws.send_json({"type": "clipboard_changed"})
                status = await asyncio.get_running_loop().run_in_executor(
                    live_reader, engine.status)
                session.jobs.set_interactive(
                    status["playing"] or time.monotonic() - app.state.last_input < 2)
                next_poll = time.monotonic() + (tick if status["playing"]
                                                else max(tick, LIVE_IDLE_S))
                # An anchor at once when the transport changed (or the first time),
                # else a correction every ``correct_every`` while playing. A
                # clipboard preview's frames are not the timeline's: nothing then.
                now = time.monotonic()
                anchor = anchor_message(status, now)
                shape = (anchor["playing"], anchor["seq"], anchor["speed"],
                         anchor["end"], str(anchor["loop"]), str(anchor["skip"]))
                due = anchor["playing"] and now - last_anchor >= correct_every
                if last_shape is None and not anchor["playing"]:
                    last_shape = shape  # stopped at connect: the page asks /api/transport
                if not status.get("preview") and (shape != last_shape or due):
                    last_shape, last_anchor = shape, now
                    await send(anchor)
                # The clipboard preview's own anchors (the chip's progress), and one
                # "stopped" when it ends, with the transport version it ended at.
                if status.get("preview") or status.get("mix_preview"):
                    preview = preview_message(status, now)
                    pshape = (preview["playing"], preview["seq"], preview["end"])
                    correct = now - last_preview_at >= correct_every
                    if pshape != last_preview or (preview["playing"] and correct):
                        last_preview, last_preview_at = pshape, now
                        await ws.send_json(preview)
                elif last_preview is not None:
                    last_preview = None
                    await ws.send_json({**preview_message(status, now), "playing": False})
                # The level meter: what plays now, only while playing, and one floor
                # frame when it stops so the bar and the hold tick drop.
                now = time.monotonic()
                if status["playing"] and now - last_meter >= meter_every:
                    last_meter, meter_on = now, True
                    await ws.send_json(meter_message(engine.meter()))
                elif meter_on and not status["playing"]:
                    meter_on = False
                    await ws.send_json(meter_message(engine.meter()))
                for n in status["notices"]:
                    if n["id"] > last_notice:
                        last_notice = n["id"]
                        await ws.send_json({"type": "notice", "id": n["id"],
                                            "key": n["key"], "params": n["params"],
                                            "text": n["text"]})

        tasks = [asyncio.create_task(hear_disconnect()), asyncio.create_task(push())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            hub.remove(queue)
            for task in tasks:
                # The client left, or we are leaving.
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect,
                                         RuntimeError):
                    await task

    @app.get("/api/locales/{lang}")
    def locale_catalog(lang: str):
        # The UI formats its own text from the same files Python uses.
        found = messages.catalog(lang)
        if found is None:
            raise UnknownIdError("error.api.no_language", lang=lang)
        return found

    # -- the page ------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index():
        page = ui / "index.html"
        if page.is_file():
            return FileResponse(page)
        return HTMLResponse(placeholder(session))

    if ui.is_dir():
        app.mount("/", StaticFiles(directory=ui), name="ui")
    return app


def placeholder(session) -> str:
    """The page shown until the UI (WP4) exists, in the request's language."""
    name = html.escape(session.package.path.name)
    return (
        f'<!doctype html><html lang="{messages.language()}"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f"<title>{html.escape(t('ui.placeholder.title'))}</title></head>"
        '<body style="font-family:system-ui;max-width:32rem;margin:4rem auto;'
        'padding:0 1rem"><h1>kuulas</h1>'
        f"<p>{html.escape(t('ui.placeholder.text', project=name))}</p></body></html>")


def etag_matches(header: str | None, tag: str) -> bool:
    """Does an ``If-None-Match`` header (``*``, or a list, weak or not) name ``tag``?"""
    parts = (x.strip() for x in (header or "").split(","))
    return any(x == "*" or x.removeprefix("W/") == tag for x in parts)


def save_upload(folder: Path, upload: UploadFile) -> Path:
    """Write one uploaded file into ``folder`` under a name of its own.

    Only the file name is kept (a client cannot choose a path), an existing
    file is never overwritten, and the bytes land in a ``.partial`` that is
    renamed when complete (ground rule 8).
    """
    name = Path((upload.filename or "").replace("\\", "/")).name
    if name in ("", ".", ".."):
        name = "upload"
    target = folder / name
    n = 1
    while target.exists():
        n += 1
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
    partial = target.with_name(target.name + ".partial")
    try:
        with partial.open("wb") as out:
            shutil.copyfileobj(upload.file, out)
            out.flush()
            os.fsync(out.fileno())
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return target
