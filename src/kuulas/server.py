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
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, File, Form, Request, UploadFile, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from . import export, messages, music_report, transcribe
from .candidates import UnknownCandidateError
from .history import HistoryError
from .media import ImportResult, MediaError
from .messages import KuulasError, error_body, t
from .ops import EditError
from .peaks import PeakError
from .playplan import PlaybackRequestError, check_loop, check_skip
from .session import (
    CLIPBOARD_EDITS,
    NarrationScriptError,
    NoSuchEntryError,
    SubtitlesError,
    TranscriptTextError,
)
from .view_memory import ViewMemory, ViewMemoryError

log = logging.getLogger("kuulas.server")

#: The repository's ``ui/`` folder; served at ``/`` when it has an index.html.
UI_DIR = Path(__file__).resolve().parents[2] / "ui"
#: How often the live channel looks at the engine while playing: the display
#: rate, so the playhead moves as often as the screen can show it.
LIVE_TICK_S = 1 / 30
#: ...and while stopped, only to hear of engine notices (the engine's own period).
LIVE_IDLE_S = 0.25
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


# -- bodies --------------------------------------------------------------------


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
    group_editing: bool = False
    name: str = ""


class PinBody(BaseModel):
    pinned: bool = True


class RenameBody(BaseModel):
    name: str


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


class WordBody(BaseModel):
    media: str
    index: int
    w: str


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
    model: str = "small"
    language: str | None = None
    backend: str = "local"


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


# -- the app -------------------------------------------------------------------


def create_app(session, engine, *, language: str | None = None,
               ui_dir: str | Path = UI_DIR, tick: float = LIVE_TICK_S) -> FastAPI:
    """``session`` and ``engine`` are borrowed: the caller closes them."""
    default_language = language or messages.default_language()
    ui = Path(ui_dir)
    app = FastAPI(title="kuulas", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.last_input = time.monotonic()
    hub = Hub()

    session.subscribe(lambda _state: hub.publish(
        {"type": "state_changed", "head": session.history.head}))

    # -- plumbing ----------------------------------------------------------

    @app.middleware("http")
    async def per_request(request: Request, call_next):
        messages.set_language(pick_language(request.headers.get("accept-language"),
                                            default_language))
        if request.url.path != "/api/jobs" and request.method != "GET":
            app.state.last_input = time.monotonic()
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
        }
        return answer(e, 400 if client_error else 500)

    @app.exception_handler(music_report.MusicReportError)
    async def _music_report_error(_request: Request, e: music_report.MusicReportError):
        return answer(e, 400)

    @app.exception_handler(KuulasError)
    async def _other_error(_request: Request, e: KuulasError):
        if e.key.startswith(("error.paste.", "error.import_plan.", "error.chapters.",
                             "error.regions.")):
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
            return {"project": session.state.to_dict(), "head": h.head,
                    "can_undo": h.can_undo, "can_redo": h.can_redo,
                    "missing": session.store.missing()}

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
        if body.name == "match_loudness":
            report = session.last_match_report
            return state_response({"match_report": {
                "matched": [{"clip_id": c, "measured": m, "gain_db": g}
                            for c, m, g in report.matched],
                "skipped": list(report.skipped)}})
        return state_response()

    # -- the view memory (WP35) ----------------------------------------------
    # The user's view of this project (zoom, scroll, ...), kept outside the
    # project: no undo step, no change to its bytes.

    @app.get("/api/view-memory")
    def get_view_memory():
        return JSONResponse({"view": ViewMemory().get(session.package.manifest["id"])})

    @app.put("/api/view-memory")
    def put_view_memory(body: ViewMemoryBody):
        try:
            ViewMemory().put(session.package.manifest["id"], body.view)
        except ViewMemoryError as e:
            raise BadRequestError(e.key, **e.params) from None
        except OSError as e:
            # A convenience: say so in the log, do not fail the page.
            log.warning(t("log.view_memory.write_failed", error=str(e)))
            return JSONResponse({"saved": False})
        return JSONResponse({"saved": True})

    # -- the clipboard (WP46) ------------------------------------------------
    # Cut and paste are edits and go through /api/edit (one undo step each);
    # copying changes no project, so it has its own route.

    @app.get("/api/clipboard")
    def get_clipboard():
        return JSONResponse({"entries": session.clipboard_list()})

    @app.post("/api/clipboard/copy")
    def post_clipboard_copy(body: CopyBody):
        out = session.clipboard_copy(clip_ids=body.clip_ids, start=body.start,
                                     end=body.end, track_ids=body.track_ids,
                                     group_editing=body.group_editing,
                                     name=body.name)
        return JSONResponse({**out, "entries": session.clipboard_list()})

    @app.post("/api/clipboard/{entry_id}/pin")
    def post_clipboard_pin(entry_id: str, body: PinBody):
        session.clipboard_pin(entry_id, body.pinned)
        return JSONResponse({"entries": session.clipboard_list()})

    @app.post("/api/clipboard/{entry_id}/rename")
    def post_clipboard_rename(entry_id: str, body: RenameBody):
        session.clipboard_rename(entry_id, body.name)
        return JSONResponse({"entries": session.clipboard_list()})

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

    @app.post("/api/export-regions")
    def post_export_regions(body: Annotated[dict[str, Any], Body()]):
        return JSONResponse({"jobs": session.export_regions(body)})

    @app.get("/api/chapters")
    def get_chapters(style: str = "text"):
        content = session.chapters(style)
        if style == "json":
            return Response(content=content, media_type="application/json",
                            headers={"Content-Disposition":
                                     'attachment; filename="chapters.json"'})
        return Response(content=content, media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition":
                                 'attachment; filename="chapters.txt"'})

    @app.get("/api/loudness-curve")
    def get_loudness_curve():
        # Measured outside the session lock (Session.loudness_curve); cached by content.
        return JSONResponse(session.loudness_curve())

    @app.get("/api/music-report")
    def get_music_report(format: str = "json"):
        if format not in ("json", "csv", "html"):
            raise music_report.MusicReportError("error.music_report.bad_format",
                                                format=format)
        if format == "csv":
            content = session.music_report(format="csv")
            disposition = 'attachment; filename="music-report.csv"'
            return Response(content=content, media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": disposition})
        if format == "html":
            content = session.music_report(format="html")
            return HTMLResponse(content=content)
        rows = session.music_report(format="json")
        return JSONResponse({"rows": rows})

    @app.get("/api/subtitles")
    def get_subtitles(format: str):
        if format not in ("srt", "vtt"):
            raise SubtitlesError("error.subtitles.bad_format", format=format)
        content = session.subtitles(format)
        if format == "srt":
            media_type = "application/x-subrip"
            disposition = 'attachment; filename="subtitles.srt"'
        else:
            media_type = "text/vtt"
            disposition = 'attachment; filename="subtitles.vtt"'
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": disposition})

    @app.get("/api/transcript-text")
    def get_transcript_text(format: str):
        if format not in ("txt", "md"):
            raise TranscriptTextError("error.transcript_text.bad_format", format=format)
        content = session.transcript_text(format)
        if format == "txt":
            media_type = "text/plain; charset=utf-8"
            disposition = 'attachment; filename="transcript.txt"'
        else:
            media_type = "text/markdown; charset=utf-8"
            disposition = 'attachment; filename="transcript.md"'
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
    def get_history(limit: int | None = None, before: str | None = None):
        """Without ``limit`` or ``before``: every step, oldest first (the old shape).
        With them: a page, newest first, for the History panel."""
        with session.lock:
            h = session.history
            if limit is None and before is None:
                return JSONResponse({"nodes": h.nodes(), "head": h.head})
            limit = HISTORY_PAGE if limit is None else limit
            if not 1 <= limit <= HISTORY_PAGE_MAX:
                raise BadRequestError("error.server.bad_request",
                                      detail=f"limit: 1..{HISTORY_PAGE_MAX}")
            rows = h.nodes_page(limit + 1, before)
            more = len(rows) > limit
            side = h.sides()
            nodes = [{"id": r["id"], "parent": r["parent"], "label": r["label"],
                      "created": r["created"], "author": r["author"],
                      "op": r["op"].get("name"), "is_marker": h.is_marker(r),
                      "marker": (r["op"].get("args") or {}).get("kind")
                      if h.is_marker(r) else None,
                      "is_head": r["id"] == h.head, "side": side[r["id"]]}
                     for r in rows[:limit]]
            return JSONResponse({"nodes": nodes, "head": h.head, "more": more,
                                 "can_undo": h.can_undo, "can_redo": h.can_redo})

    @app.get("/api/jobs")
    def get_jobs():
        return JSONResponse({"jobs": session.jobs.list()})

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str):
        if not any(job["id"] == job_id for job in session.jobs.list()):
            raise UnknownIdError("error.jobs.unknown", job_id=job_id)
        session.jobs.cancel(job_id)
        return JSONResponse({"jobs": session.jobs.list()})

    @app.post("/api/transcribe", status_code=202)
    def post_transcribe(body: TranscribeBody):
        if not body.media_ids:
            raise BadRequestError("error.server.bad_request", detail="media_ids")
        if body.backend == "colab":
            raise BadRequestError("error.transcribe.colab_unavailable")
        if body.backend != "local":
            raise BadRequestError("error.server.bad_request", detail="backend")
        if session.read_only:
            holder = session.package.locked_by or {}
            raise BadRequestError("error.history.read_only",
                                  host=holder.get("host", "?"))
        for media_id in body.media_ids:
            require_media(media_id)
        try:
            job_ids = session.transcribe(body.media_ids, body.model, body.language)
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
                 track_naming: str = "file", start_frame: int = 0) -> JSONResponse:
        try:
            _, results = session.import_media_report(
                paths, copy=copy, mode=mode, order=order,
                track_naming=track_naming, start_frame=start_frame,
            )
        except MediaError as e:
            # Nothing came in: say why, file by file, so the UI can show each.
            return JSONResponse({**error_body(e.key, **e.params),
                                 "report": report_of(session.last_import_report)},
                                status_code=500)
        return state_response({"report": report_of(results)})

    @app.post("/api/import")
    def post_import(body: ImportBody):
        return imported(body.paths, body.copy_files, mode=body.mode,
                        order=body.order, track_naming=body.track_naming,
                        start_frame=body.start_frame)

    @app.post("/api/upload")
    def post_upload(
        files: Annotated[list[UploadFile] | None, File()] = None,
        mode: Annotated[str | None, Form()] = None,
        order: Annotated[str, Form()] = "given",
        track_naming: Annotated[str, Form()] = "file",
        start_frame: Annotated[int, Form()] = 0,
    ):
        if not files:
            raise BadRequestError("error.server.bad_request", detail="files")
        folder = session.package.path / "uploads"
        folder.mkdir(exist_ok=True)
        saved = [str(save_upload(folder, f)) for f in files]
        return imported(saved, copy=False, mode=mode, order=order,
                        track_naming=track_naming, start_frame=start_frame)

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

    @app.get("/api/transport")
    def get_transport():
        return JSONResponse(engine.status())

    @app.post("/api/transport")
    def post_transport(body: TransportBody):
        action = body.action
        if action in ("seek", "scrub") and body.at is None:
            raise BadRequestError("error.server.missing_field", field="at")
        if action == "play":
            # Checked here too, so a bad list is a 400 whatever the engine.
            skip = check_skip(body.skip)
            loop = (None if body.loop is None
                    else check_loop(body.loop, skip, getattr(engine, "rate", 48000)))
            engine.play(body.at, body.until, rate=body.speed,
                        preserve_pitch=body.preserve_pitch, skip=skip, loop=loop)
        elif action == "stop":
            engine.stop()
        elif action == "seek":
            engine.seek(body.at)
        elif action == "scrub":
            engine.scrub(body.at)
        else:
            raise BadRequestError("error.server.bad_transport", action=action)
        return JSONResponse(engine.status())

    # -- push ------------------------------------------------------------------

    @app.websocket("/api/live")
    async def live(ws: WebSocket):
        await ws.accept()
        messages.set_language(pick_language(ws.headers.get("accept-language"),
                                            default_language))
        queue: asyncio.Queue = asyncio.Queue()
        hub.add(asyncio.get_running_loop(), queue)

        async def hear_disconnect() -> None:
            # Without reading, a client that went away is never noticed while
            # nothing is being sent.
            while True:
                await ws.receive_text()

        async def push() -> None:
            await ws.send_json({"type": "hello", "head": session.history.head})
            initial_jobs = session.jobs.list()
            await ws.send_json({"type": "jobs", "jobs": initial_jobs})
            last_jobs = tuple((job["id"], job["progress"], job["state"], job["error"])
                              for job in initial_jobs)
            last_notice, playing, last_position = 0, False, None
            next_poll = time.monotonic()
            while True:
                wait = max(0.0, next_poll - time.monotonic())
                with contextlib.suppress(TimeoutError):  # nothing to send yet
                    await ws.send_json(await asyncio.wait_for(queue.get(), wait))
                if time.monotonic() < next_poll:
                    continue
                current_jobs = session.jobs.list()
                signature = tuple((job["id"], job["progress"], job["state"], job["error"])
                                  for job in current_jobs)
                if signature != last_jobs:
                    await ws.send_json({"type": "jobs", "jobs": current_jobs})
                    last_jobs = signature
                status = await asyncio.to_thread(engine.status)
                session.jobs.set_interactive(
                    status["playing"] or time.monotonic() - app.state.last_input < 2)
                next_poll = time.monotonic() + (tick if status["playing"]
                                                else max(tick, LIVE_IDLE_S))
                position = status["position"]
                moved = status["playing"] and position != last_position
                if moved or (playing and not status["playing"]):
                    await ws.send_json({"type": "position", "position": position,
                                        "playing": status["playing"]})
                playing, last_position = status["playing"], position
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
