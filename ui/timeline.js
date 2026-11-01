// The timeline canvases. Two layers, one above the other:
//   - the waveform layer (clip bodies and waveforms) is drawn in a Web Worker
//     from peak tiles (waveform-layer.js, paint.js);
//   - this overlay draws everything that is cheap and changes often: the
//     ruler, clip outlines and names, gain lines, selection, in/out, playhead.
// The overlay redraws on requestAnimationFrame when state changed; the
// waveform layer only when something it shows changed.

import { peakTile } from "./api.js";
import { automationTargets } from "./automation-snap.js";
import { candidateBands, flagFits, flagText } from "./candidates-model.js";
import { backingSize } from "./canvas-size.js";
import {
  canStartClipDrag,
  clipDragIds,
  groupBounds,
  moveBoxes,
  moveGhosts,
  portionDragEdit,
  resolveMove,
  targetTrackRow,
} from "./clip-drag.js";
import { overLabel } from "./clip-overs.js";
import { implicitSilenceRanges } from "./clip-silence.js";
import { averageWordFrames, layoutClipWords, wordsWideEnough } from "./clip-words.js";
import { dropTarget as clipboardDropTarget, dropOutlines } from "./clipboard-drag.js";
import { DEFAULT_DRAG_MODE, dragIntent } from "./drag-mode.js";
import { createDragSnap } from "./drag-snap.js";
import { clampImplicitEdge, edgeGhost, ghostGeometry, resolveEdge } from "./edge-drag.js";
import { inactiveTracks } from "./focus-layout.js";
import { frameToTime, frameToX, xToFrame } from "./format.js";
import {
  envelopeDragChange,
  envelopeMove,
  envelopePointZone,
  envelopeToggle,
  fadeFromX,
  fadeHandleAt,
  fadeHandles,
  fadeShape,
  gainFromY,
  gainGrab,
  gainLineHit,
  gainLineVisible,
} from "./gain-drag.js";
import { gatePixelRuns } from "./gate.js";
import {
  GHOST_ALPHA,
  GHOST_MUTED_FACTOR,
  ghostColumns,
  ghostWindow,
  windowCovers,
} from "./ghost-wave.js";
import { busHues, fileMark, needsFileMark, ribbonLayout, seamKind } from "./grammar.js";
import { groupOutlines } from "./group-outline.js";
import { detectPlatform, formatNumber, t } from "./i18n.js";
import { ICONS } from "./icons.js";
import { dropGhosts, dropLabel, resolveDropTarget } from "./import-drop.js";
import { rangeDimmed } from "./intent.js";
import { clipLabel, labelFacts, siblingsOf } from "./labels.js";
import {
  clipEnd,
  dbToY,
  EDGE_PX,
  envelopeFrame,
  hitTest,
  layoutFor,
  paintOrder,
  projectEnd,
  RULER_HEIGHT,
  visibleRows,
} from "./lanes.js";
import { leftOffFlag } from "./left-off.js";
import { liveWaveformColumns } from "./live-take.js";
import { activeLoop } from "./loop-range.js";
import { flagLayout, NOTCH_PX as MARKER_NOTCH_PX } from "./markers-model.js";
import { lengthPill, markDrawing } from "./marks.js";
import { heldFromEvent, modClick } from "./modifiers.js";
import { advanceDelta, movedSpans, moveTargets, snapMove } from "./move-snap.js";
import {
  baseGainDb,
  drawDiagonalHatch,
  drawPreviewBands,
  makeWaveformJob,
  scaleFor,
  trackHues,
} from "./paint.js";
import { aboutSeconds, placeholderLabel } from "./placeholders-model.js";
import { dragRange, isDrag, touchedResult, trackRowsTouched } from "./range-drag.js";
import { scopeSpans } from "./range-scope.js";
import { rulerTicks } from "./ruler.js";
import { createRulerScrub } from "./scrub-velocity.js";
import {
  inactiveLook,
  lockSpots,
  lockTop,
  openLockSpot,
  STRETCH_EDGE_DASH,
  stretchEdges,
  TRACK_LAYERS,
} from "./silence-visuals.js";
import {
  anchorIds,
  anchorNameFor,
  formatOffset,
  homeNameFor,
  syncIndex,
  syncMark,
} from "./sync-state.js";
import { readTheme } from "./theme.js";
import { createTileStore } from "./tiles.js";
import { selectionBounds, wordAtTime } from "./transcript-model.js";
import { pickLevel, waveformColumns } from "./waveform.js";
import { createWaveformLayer } from "./waveform-layer.js";
import { wheelIntent } from "./wheel.js";

// Drawing rules: docs/design/GUI-DESIGN.md, "Waveforms and the timeline"; the silent states
// (outline = silent, padlocks, inactive lanes): docs/design/SILENCE-VISUALS.md.
const NAME_FONT_PX = 11;
const LABEL_H = 14;
const LABEL_BACKING_ALPHA = 0.85;
// The words row (WP69) sits under the label strip; it needs a lane tall enough to leave
// waveform below it. Plain words are the label colour dimmed, so they read as secondary.
const WORDS_FONT_PX = 10;
const WORDS_ROW_H = 12;
const WORDS_MIN_LANE = 52;
const WORDS_PLAIN_ALPHA = 0.7;
const WORDS_BACKING_ALPHA = 0.55;
const WORDS_SELECTED_ALPHA = 0.5;
/** The longest word that can start before the view and still reach into it (seconds). */
const WORDS_LOOKBACK_S = 10;
const POINT_RADIUS = 3;
const XFADE_ALPHA = 0.3;
const GAIN_ALPHA = 0.75;
// Opacity of a guessed in/out mark (taken from the last cut), against 1 for a chosen one.
const GUESSED_ALPHA = 0.55;
// The in/out marks are drawn at this opacity while selected clips, not the range, are what the
// next edit touches (intent.js).
const MARKS_VEILED_ALPHA = 0.35;
const PLAYHEAD_CAP = 5.5;
const SEAM_ALPHA = 0.7;
const NOTCH_PX = 4;
const MARK_FONT_PX = 10;
const BRACKET_PX = 10;
// The padlocks of the silent states: drawn 12 px on a panel-coloured chip (silence-tokens.test.js
// checks them at 3:1 on the chip, the lane and every body), 3 px in from a stretch's left.
const ICON_PX = 12;
const ICON_PAD = 3;
const ICON_CHIP_PAD = 1;
// Missing media: the warning sign, as large as the lane allows (owner: ugly is fine, clarity first).
const MISSING_SIGN_MAX = 28;
const MISSING_EDGE_PX = 2;
const CANDIDATE_STRIPE_ALPHA = 0.35;
const CANDIDATE_EDGE_PX = 1;
const CANDIDATE_EDGE_CURRENT_PX = 2;
const FLAG_EDGE_PX = 3;
const REGION_BAR_PX = 5;
const MARKER_FLAG_H = 8;
const FLAG_EDGE_CURRENT_PX = 4;
/** Ghost waveform columns built beyond the screen each side, so small moves need no rebuild. */
const GHOST_MARGIN_PX = 256;

// `playheadAt(state)` (optional): the frame to draw the playhead at now (app.js extrapolates
// it from the engine's anchors while playing); default the state's playhead.
export function createTimeline({
  stack,
  waveCanvas,
  overlayCanvas,
  getState,
  actions,
  playheadAt = (state) => state.playhead,
  liveTake = null,
}) {
  const overlay = overlayCanvas.getContext("2d");
  // Clips whose waveform clips after gain (WP57): clip id -> dB above full scale, as the
  // painter judged the visible columns. Drives the tooltip and the red gain line.
  let clipOvers = {};
  const layer = createWaveformLayer(waveCanvas, {
    onOvers(overs) {
      clipOvers = overs ?? {};
      requestOverlay();
    },
  });
  let theme = readTheme();
  let size = { width: 0, height: 0, ratio: 1 };
  let pointerFrame = null;
  let edgeSession = null; // an edge being dragged: see the pointer section
  let tweakSession = null; // a gain line or fade handle being dragged
  let hoverClipId = null; // the clip under the pointer: its fade handles show
  let altTargetClip = null; // clip targeted for direct mute with Alt held
  let lastPointerHit = null;
  let altKeyHeld = false;
  let clipSession = null; // clips being moved by their label strip: see the pointer section
  let ghostTiles = null; // main-thread peak tiles for the move ghosts' waveforms, made on first use
  let dropPreview = null; // files being dragged over: { kind, startFrame, mode, count } or null
  let clipDrop = null; // a clipboard entry dragged over: { target, entry } or null
  let rangeBand = null; // a range being dragged: { fromFrame, toFrame, tracks, alt, touched } or null
  let bands = []; // the open candidates in pixels (candidates-model.js), per redraw
  let overlayQueued = false;
  let waveQueued = false;
  let lastWaveKey = "";
  let jobId = 0;

  const refreshTheme = () => {
    theme = readTheme();
    lastWaveKey = "";
    requestWaveforms();
    requestOverlay();
  };
  const dark = matchMedia("(prefers-color-scheme: dark)");
  dark.addEventListener("change", refreshTheme);

  function measure() {
    const rect = stack.getBoundingClientRect();
    // The viewport's size, with the pixel count capped (canvas-size.js): the
    // waveform worker sizes its canvas from the same ratio.
    const backing = backingSize(rect.width, rect.height, devicePixelRatio || 1);
    size = {
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      ratio: backing.ratio,
    };
    if (overlayCanvas.width !== backing.width) overlayCanvas.width = backing.width;
    if (overlayCanvas.height !== backing.height) overlayCanvas.height = backing.height;
    lastWaveKey = "";
    actions.resized(size);
    requestWaveforms();
    requestOverlay();
  }
  const observer = new ResizeObserver(measure);
  observer.observe(stack);

  // -- the waveform layer ------------------------------------------------------

  function requestWaveforms() {
    if (waveQueued) return;
    waveQueued = true;
    requestAnimationFrame(() => {
      waveQueued = false;
      const state = getState();
      if (!state.project || size.width === 0) return;
      const job = makeWaveformJob(state, { ...size, id: 0 }, theme.palette, {
        busBands: theme.busBands,
        clipping: theme.clipping,
        silentBody: theme.silentBody,
        silentHatch: theme.silentHatch,
        preview: theme.preview,
        missingFill: theme.damagedFill,
        paletteInactive: theme.paletteInactive,
        inactive: inactiveLook(state.inactiveStyle).desaturate ? inactiveTracks(state) : null,
      });
      const key = JSON.stringify(job);
      if (key === lastWaveKey) return;
      lastWaveKey = key;
      jobId += 1;
      layer.draw({ ...job, id: jobId });
    });
  }

  // -- the overlay -------------------------------------------------------------

  function requestOverlay() {
    if (overlayQueued) return;
    overlayQueued = true;
    requestAnimationFrame(() => {
      overlayQueued = false;
      drawOverlay();
    });
  }

  function drawOverlay() {
    const state = getState();
    const { width, height, ratio } = size;
    overlay.setTransform(ratio, 0, 0, ratio, 0, 0);
    overlay.clearRect(0, 0, width, height);
    if (!state.project) return;
    const rate = state.project.rate;
    const layout = layoutFor(state);
    const hues = trackHues(state.project);
    const groups = busHues(state.project);
    bands = candidateBands(state.candidates ?? [], {
      scroll: state.scroll,
      zoom: state.zoom,
      width,
      currentId: state.candidateCurrent,
    });
    // With the scope narrowed the band and the in/out bars belong to the touched lanes only.
    const spans = scopeSpans(state, layout.rows, {
      rulerHeight: RULER_HEIGHT,
      scrollY: state.scrollY,
    });
    // Clips selected after the marks are what the next edit touches: the marks stay, veiled.
    const marksVeiled = rangeDimmed(state);
    overlay.save();
    if (marksVeiled) overlay.globalAlpha = MARKS_VEILED_ALPHA;
    drawRange(state, height, spans);
    overlay.restore();
    const dimmed = inactiveTracks(state);
    const look = inactiveLook(state.inactiveStyle);
    for (const row of visibleRows(layout, state.scrollY, height - RULER_HEIGHT)) {
      const top = RULER_HEIGHT + row.top - state.scrollY;
      if (row.kind === "gap") continue; // plain lane between groups: nothing drawn
      overlay.strokeStyle = theme.rule;
      overlay.lineWidth = 1;
      overlay.beginPath();
      overlay.moveTo(0, top + row.height - 0.5);
      overlay.lineTo(width, top + row.height - 0.5);
      overlay.stroke();
      const inactive = row.kind === "track" && dimmed.has(row.id);
      if (row.kind === "track")
        drawTrack(state, state.project.tracks[row.index], row, top, hues, inactive && look);
      // The tracks the next range operation will not touch are inactive (WP83): veiled, drawn
      // in the grey palette, or both (the view preference, silence-visuals.js inactiveLook).
      if (inactive) {
        if (look.veil > 0) drawVeil(row, top, width, look.veil);
      } else drawBusRow(state, row, top, groups, hues);
    }
    drawGroupOutlines(state, layout);
    drawRuler(state, rate);
    overlay.save();
    if (marksVeiled) overlay.globalAlpha = MARKS_VEILED_ALPHA;
    drawInOut(state, height, rate, spans);
    overlay.restore();
    drawRangeBand(state, layout);
    if (dropPreview) drawDropPreview(state, layout);
    if (clipDrop) drawClipboardDrop(state, layout);
    if (edgeSession?.dragging) {
      drawAutomationSnapMarks(state, edgeSession.snap.marks);
      drawEdgeGhost(state, layout);
    }
    if (clipSession?.dragging) drawMoveGhost(state, layout);
    drawPlayhead(state, height);
  }

  // A clip edge being dragged (WP6): a thin line at the new edge, the clip's new outline and,
  // for roll, the neighbour's. Ripple is drawn dashed with the accent line, roll solid.
  function drawEdgeGhost(state, layout) {
    const row = layout.rows.find((item) => item.id === edgeSession.trackId);
    const track = state.project.tracks.find((item) => item.id === edgeSession.trackId);
    const clip = track?.clips.find((item) => item.id === edgeSession.clipId);
    if (!(row && clip)) return;
    if (edgeSession.implicitRange) {
      const x = frameToX(edgeSession.frame, state.scroll, state.zoom);
      overlay.save();
      overlay.beginPath();
      overlay.rect(0, RULER_HEIGHT, size.width, size.height - RULER_HEIGHT);
      overlay.clip();
      overlay.strokeStyle = theme.accent;
      overlay.lineWidth = 2;
      overlay.setLineDash([4, 3]);
      overlay.beginPath();
      overlay.moveTo(x + 0.5, RULER_HEIGHT);
      overlay.lineTo(x + 0.5, size.height);
      overlay.stroke();
      overlay.restore();
      return;
    }
    const ghost = edgeGhost(state.project, track, clip, edgeSession.edge, edgeSession.frame, {
      ripple: edgeSession.ripple,
      overwrite: edgeSession.overwrite,
      alone: edgeSession.alone,
    });
    const geometry = ghostGeometry(ghost, { view: state, row });
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, RULER_HEIGHT, size.width, size.height - RULER_HEIGHT);
    overlay.clip();
    drawEdgeCovered(geometry);
    if (geometry.gap) {
      // Trim-only-this-clip: the stretch the clip gives up stays empty, hatched.
      const { x, y, w, h } = geometry.gap;
      drawHatchAt(x, y, w, h, theme.accent, 0.4);
    }
    overlay.strokeStyle = theme.accent;
    overlay.lineWidth = 1.5;
    overlay.setLineDash(ghost.ripple ? [5, 3] : []);
    for (const box of [geometry.clip, geometry.neighbour]) {
      if (box) overlay.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);
    }
    overlay.setLineDash([]);
    overlay.fillStyle = theme.accent;
    overlay.fillRect(Math.round(geometry.line.x) - 1, geometry.line.y, 2, geometry.line.h);
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    overlay.fillStyle = theme.ink;
    const hint = t(
      ghost.ripple
        ? "ui.edge.hint_ripple"
        : ghost.alone
          ? "ui.edge.hint_alone"
          : edgeSession.overwrite
            ? "ui.edge.hint_roll"
            : "ui.edge.hint_roll_alone",
    );
    overlay.fillText(hint, Math.max(4, geometry.line.x + 6), geometry.line.y + 3);
    overlay.restore();
  }

  // What an overwriting edge drag will do to the clips under it: the stretch it covers is
  // hatched, a clip covered whole is dimmed and struck through (it goes), a clip covered at
  // its edge has just the lost part dimmed (it is trimmed).
  function drawEdgeCovered(geometry) {
    if (!geometry.region) return;
    overlay.fillStyle = theme.ink;
    overlay.globalAlpha = 0.35;
    for (const item of geometry.covered) {
      if (item.removed) {
        overlay.fillRect(item.x, item.y, item.w, item.h);
      } else {
        const lostX = item.kept.x === item.x ? item.kept.x + item.kept.w : item.x;
        const lostW = item.w - item.kept.w;
        overlay.fillRect(lostX, item.y, lostW, item.h);
      }
    }
    overlay.globalAlpha = 1;
    drawHatchAt(
      geometry.region.x,
      geometry.region.y,
      geometry.region.w,
      geometry.region.h,
      theme.accent,
      0.4,
    );
    overlay.strokeStyle = theme.ink;
    overlay.lineWidth = 1.5;
    for (const item of geometry.covered) {
      if (!item.removed) continue;
      overlay.beginPath();
      overlay.moveTo(item.x, item.y);
      overlay.lineTo(item.x + item.w, item.y + item.h);
      overlay.moveTo(item.x + item.w, item.y);
      overlay.lineTo(item.x, item.y + item.h);
      overlay.stroke();
    }
  }

  // The tiles behind the ghosts' waveforms. The worker's own cache is out of reach, so the
  // main thread keeps a small one; the browser's HTTP cache (tiles never change) makes the
  // second fetch of a tile a local read. A tile arriving drops the ghosts built without it.
  function ghostStore() {
    ghostTiles ??= createTileStore({
      fetchTile: peakTile,
      onChange() {
        for (const entry of clipSession?.waves?.values() ?? [])
          if (entry.pending) entry.stale = true;
        requestOverlay();
      },
    });
    return ghostTiles;
  }

  // One ghost's waveform columns: built for the visible part of the clip (plus a margin) and
  // kept for the drag, so the pointer moving only translates them. Rebuilt when the zoom or
  // the gain changes, the view slides past the built part, or missing tiles have arrived.
  function ghostWave(state, clip, dest, box) {
    const need = ghostWindow(box.x, box.w, size.width, 0);
    if (!need) return null;
    const waves = clipSession.waves;
    const gainDb = baseGainDb(clip, dest);
    let entry = waves.get(clip.id);
    if (
      !entry ||
      entry.stale ||
      entry.zoom !== state.zoom ||
      entry.gainDb !== gainDb ||
      !windowCovers(entry, need)
    ) {
      const built = ghostWindow(box.x, box.w, size.width, GHOST_MARGIN_PX);
      const level = pickLevel(state.zoom);
      const store = ghostStore();
      const result = ghostColumns({
        lookup: (tile) => store.lookup(clip.media, level, tile),
        offset: clip.offset,
        length: clip.length,
        zoom: state.zoom,
        gainDb,
        envelope: clip.envelope,
        first: built.first,
        count: built.count,
      });
      store.want(result.missing.map((tile) => ({ media: clip.media, level: result.level, tile })));
      entry = {
        zoom: state.zoom,
        gainDb,
        first: result.first,
        count: result.data.length / 2,
        data: result.data,
        pending: result.missing.length > 0,
        stale: false,
      };
      waves.set(clip.id, entry);
    }
    return entry;
  }

  // The moved clip's waveform inside its ghost box, in the destination track's colour, half
  // see-through. One rect per pixel column, only the visible ones, in a single path.
  function drawGhostWave(state, entry, box, track, colours, muted) {
    const bars = waveformColumns(
      entry.data,
      state.waveformMode,
      scaleFor(track.kind, state.waveformScale),
      box.h,
      state.waveformGain ?? 1,
    );
    const x0 = Math.round(box.x) + entry.first;
    overlay.save();
    overlay.beginPath();
    overlay.rect(box.x, box.y, box.w, box.h);
    overlay.clip();
    overlay.globalAlpha = GHOST_ALPHA * (muted ? GHOST_MUTED_FACTOR : 1);
    overlay.fillStyle = colours.wave;
    overlay.beginPath();
    for (let column = 0; column < entry.count; column += 1) {
      const top = bars[2 * column];
      const bottom = bars[2 * column + 1];
      if (bottom > top) overlay.rect(x0 + column, box.y + top, 1, bottom - top);
    }
    overlay.fill();
    overlay.restore();
  }

  // Shared ticks along the lane tops show the temporary automation snap targets.
  function drawAutomationSnapMarks(state, frames) {
    overlay.save();
    overlay.fillStyle = theme.accent;
    overlay.globalAlpha = 0.7;
    for (const frame of frames) {
      const x = frameToX(frame, state.scroll, state.zoom);
      if (x < 0 || x > size.width) continue;
      overlay.fillRect(Math.round(x), RULER_HEIGHT, 1, 10);
    }
    overlay.restore();
  }

  // Clips being moved (WP6): dashed accent outlines at the new place, on the new track, with
  // each clip's own waveform inside (WP63) so waveforms can be lined up by eye.
  function drawMoveGhost(state, layout) {
    const ghosts = moveGhosts(state.project, clipSession.ids, clipSession.move);
    if (clipSession.autoOn) drawAutomationSnapMarks(state, clipSession.auto);
    if (clipSession.snapAt !== null) {
      // The snap line: a thin accent line where the moved edge landed.
      const x = frameToX(clipSession.snapAt, state.scroll, state.zoom);
      overlay.save();
      overlay.fillStyle = theme.accent;
      overlay.fillRect(Math.round(x), RULER_HEIGHT, 1, size.height - RULER_HEIGHT);
      overlay.restore();
    }
    const byClip = new Map(ghosts.map((ghost) => [ghost.clipId, ghost]));
    const hues = trackHues(state.project);
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, RULER_HEIGHT, size.width, size.height - RULER_HEIGHT);
    overlay.clip();
    clipSession.waves ??= new Map();
    const clips = new Map();
    for (const track of state.project.tracks)
      for (const clip of track.clips) if (byClip.has(clip.id)) clips.set(clip.id, clip);
    const boxes = moveBoxes(ghosts, { view: state, layout });
    for (const box of boxes) {
      const ghost = byClip.get(box.clipId);
      const clip = clips.get(box.clipId);
      const dest = state.project.tracks.find((track) => track.id === ghost.trackId);
      if (!(clip && dest)) continue;
      const entry = ghostWave(state, clip, dest, box);
      if (!entry) continue;
      const colours = theme.palette[(hues.get(dest.id) ?? 0) % theme.palette.length];
      drawGhostWave(state, entry, box, dest, colours, clip.muted);
    }
    overlay.strokeStyle = theme.accent;
    overlay.lineWidth = 1.5;
    overlay.setLineDash([5, 3]);
    for (const box of boxes) {
      overlay.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);
    }
    // Several clips (a group): one outline round the whole of them.
    const bounds = groupBounds(boxes);
    if (bounds) {
      overlay.setLineDash([]);
      overlay.lineWidth = 1;
      overlay.strokeRect(bounds.x - 1.5, bounds.y - 1.5, bounds.w + 3, bounds.h + 3);
    }
    overlay.restore();
  }

  // A clipboard entry dragged over the timeline (clipboard-drag.js): the target track's band
  // tinted, an outline per clip where the drop puts it (dashed), and the drop line in the accent
  // colour (solid when it snapped).
  function drawClipboardDrop(state, layout) {
    drawAutomationSnapMarks(state, clipDrop.target.autoMarks);
    const { outlines, rows } = dropOutlines(clipDrop.entry, clipDrop.target, {
      layout,
      view: state,
    });
    overlay.save();
    overlay.fillStyle = theme.accent;
    overlay.globalAlpha = 0.08;
    for (const row of rows) overlay.fillRect(0, row.y, size.width, row.h);
    overlay.globalAlpha = 1;
    overlay.setLineDash([5, 4]);
    overlay.strokeStyle = theme.accent;
    overlay.lineWidth = 1.5;
    for (const box of outlines) overlay.strokeRect(box.x + 0.5, box.y + 2.5, box.w, box.h - 5);
    overlay.setLineDash(clipDrop.target.snapAt === null ? [3, 3] : []);
    const x = frameToX(clipDrop.target.at, state.scroll, state.zoom);
    overlay.beginPath();
    overlay.moveTo(x + 0.5, RULER_HEIGHT);
    overlay.lineTo(x + 0.5, size.height);
    overlay.stroke();
    overlay.restore();
  }

  // Files dragged over the timeline: ghost clips (dashed) and an insertion line in the
  // accent colour, with a label of what will happen (GUI-DESIGN.md §23).
  function drawDropPreview(state, layout) {
    const { line, ghosts, label } = dropGhosts(dropPreview, {
      layout,
      view: state,
      size: { width: size.width, height: size.height },
    });
    overlay.fillStyle = theme.accent;
    if (line.orientation === "horizontal") overlay.fillRect(0, line.y - 1, size.width, 2);
    else overlay.fillRect(line.x - 1, RULER_HEIGHT, 2, size.height - RULER_HEIGHT);
    overlay.save();
    overlay.setLineDash([5, 4]);
    overlay.strokeStyle = theme.muted;
    overlay.lineWidth = 1.5;
    overlay.fillStyle = theme.panel;
    for (const ghost of ghosts) {
      overlay.fillRect(ghost.x, ghost.y, ghost.w, ghost.h);
      overlay.strokeRect(ghost.x + 0.5, ghost.y + 0.5, ghost.w, ghost.h);
    }
    overlay.restore();
    const { key, params } = dropLabel(dropPreview);
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    overlay.fillStyle = theme.ink;
    overlay.fillText(t(key, params), label.x, label.y);
  }

  // The active channel (owner, 2026-10-18: hard to tell which one is active; then: the tint made
  // empty spots hard to see, then: the top and bottom lines too). Just a wide solid bar at its left
  // edge, and the other lanes are veiled more strongly so the active one stands out.
  function drawVeil(row, top, width, alpha) {
    overlay.save();
    overlay.fillStyle = theme.panel;
    overlay.globalAlpha = alpha;
    overlay.fillRect(0, top, width, row.height);
    overlay.restore();
  }

  function drawRange(state, height, spans) {
    const { range } = markDrawing(state);
    if (range === null) return;
    const x1 = frameToX(range.start, state.scroll, state.zoom);
    const x2 = frameToX(range.end, state.scroll, state.zoom);
    overlay.fillStyle = theme.range;
    const bands = spans ?? [{ top: RULER_HEIGHT, height: height - RULER_HEIGHT }];
    for (const span of bands) overlay.fillRect(x1, span.top, x2 - x1, span.height);
    // A solid edge at each end, so what is inside the range and what is outside read at
    // a glance, also over a loud waveform (owner, 2026-10-23: more contrast).
    overlay.fillStyle = theme.accent;
    for (const span of bands) {
      overlay.fillRect(Math.round(x1) - 1, span.top, 2, span.height);
      overlay.fillRect(Math.round(x2) - 1, span.top, 2, span.height);
    }
  }

  // The band in the ruler too (drawn after the ruler, under the flags), and the length as a
  // small accent-outlined pill centred on it; it hides the time labels under it, as the other
  // ruler flags do. No pill when the band is too narrow (marks.js lengthPill); no dashes.
  function drawRangeInRuler(state, rate) {
    const { range } = markDrawing(state);
    if (range === null) return;
    const x1 = frameToX(range.start, state.scroll, state.zoom);
    const x2 = frameToX(range.end, state.scroll, state.zoom);
    overlay.fillStyle = theme.range;
    overlay.fillRect(x1, 0, x2 - x1, RULER_HEIGHT - 1);
    overlay.save();
    overlay.font = `600 ${MARK_FONT_PX + 1}px ${theme.mono}`;
    const label = frameToTime(range.end - range.start, rate);
    const pill = lengthPill({
      range,
      scroll: state.scroll,
      zoom: state.zoom,
      width: size.width,
      textWidth: overlay.measureText(label).width,
    });
    if (pill) {
      const top = 3;
      const h = RULER_HEIGHT - 8;
      overlay.beginPath();
      overlay.roundRect(Math.round(pill.x) + 0.5, top + 0.5, pill.width, h, h / 2);
      overlay.fillStyle = theme.panel;
      overlay.fill();
      overlay.strokeStyle = theme.accent;
      overlay.lineWidth = 1;
      overlay.stroke();
      overlay.fillStyle = theme.accentText;
      overlay.textAlign = "center";
      overlay.textBaseline = "middle";
      overlay.fillText(label, pill.center, top + 1 + h / 2);
    }
    overlay.restore();
  }

  // The range being dragged (WP6): the selection tint over the lanes it covers.
  function drawRangeBand(state, layout) {
    if (!rangeBand) return;
    const x1 = frameToX(rangeBand.fromFrame, state.scroll, state.zoom);
    const x2 = frameToX(rangeBand.toFrame, state.scroll, state.zoom);
    overlay.fillStyle = theme.range;
    for (const row of layout.rows) {
      if (!rangeBand.tracks.includes(row.id)) continue;
      const top = RULER_HEIGHT + row.top - state.scrollY;
      overlay.fillRect(Math.min(x1, x2), top, Math.abs(x2 - x1), row.height);
    }
    overlay.save();
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    overlay.fillStyle = theme.ink;
    const hint = t(rangeBand.alt ? "ui.range.hint_alt" : "ui.range.hint");
    overlay.fillText(hint, Math.max(4, Math.min(x1, x2) + 4), RULER_HEIGHT + 3);
    overlay.restore();
  }

  // In and out: 1 px accent edges with a flag in the ruler, pointing inwards.
  // A lone mark is drawn too, so pressing O or I shows something at once.
  // One 1 px bar at x: the whole height, or only on the lanes in scope (the ruler flag stays).
  // A guessed mark (taken from the last cut, marks.js placeMark) is a dashed, lighter bar.
  function drawBar(x, spans, height, guessed = false) {
    if (guessed) {
      overlay.save();
      overlay.globalAlpha = GUESSED_ALPHA;
      overlay.strokeStyle = theme.accent;
      overlay.lineWidth = 1;
      overlay.setLineDash([4, 3]);
      overlay.beginPath();
      if (spans === null) {
        overlay.moveTo(x + 0.5, 0);
        overlay.lineTo(x + 0.5, height);
      } else {
        for (const span of spans) {
          overlay.moveTo(x + 0.5, span.top);
          overlay.lineTo(x + 0.5, span.top + span.height);
        }
      }
      overlay.stroke();
      overlay.restore();
      return;
    }
    if (spans === null) overlay.fillRect(x, 0, 1, height);
    else for (const span of spans) overlay.fillRect(x, span.top, 1, span.height);
  }

  function drawFlag(x, direction, guessed) {
    overlay.save();
    overlay.fillStyle = theme.accent;
    overlay.globalAlpha = guessed ? GUESSED_ALPHA : 1;
    overlay.beginPath();
    overlay.moveTo(x, 0);
    overlay.lineTo(x + 8 * direction, 0);
    overlay.lineTo(x, 8);
    overlay.fill();
    if (guessed) {
      // An outline instead of a solid flag: a guess reads differently from a chosen mark.
      overlay.globalAlpha = 1;
      overlay.strokeStyle = theme.accent;
      overlay.lineWidth = 1;
      overlay.setLineDash([2, 2]);
      overlay.stroke();
    }
    overlay.restore();
  }

  function drawInOut(state, height, rate, spans) {
    const { inFrame, outFrame, guessed } = markDrawing(state);
    drawRangeInRuler(state, rate);
    overlay.fillStyle = theme.accent;
    if (inFrame !== null) {
      const x1 = frameToX(inFrame, state.scroll, state.zoom);
      drawBar(Math.round(x1), spans, height, guessed.in);
      drawFlag(x1, 1, guessed.in);
    }
    if (outFrame !== null) {
      const x2 = frameToX(outFrame, state.scroll, state.zoom);
      drawBar(Math.round(x2) - 1, spans, height, guessed.out);
      drawFlag(x2, -1, guessed.out);
    }
  }

  // One lane, layer by layer in the order silence-visuals.js TRACK_LAYERS gives: the silent-state
  // overlays (preview edges, padlocks) first, then every clip's chrome (border, name, gain line,
  // fade handles, selection) above them, so an edge inside a closed stretch is always visible
  // and grabbable. The waveform layer (outline-only silent stretches, the body tone) is a
  // canvas under this whole overlay.
  function drawTrack(state, track, row, top, hues, inactive) {
    const { width } = size;
    const palette = inactive?.desaturate ? theme.paletteInactive : theme.palette;
    const colours = palette[(hues.get(track.id) ?? 0) % palette.length];
    // Rows under the ruler must not paint over it.
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, RULER_HEIGHT, width, size.height - RULER_HEIGHT);
    overlay.clip();
    const painters = {
      preview: () => drawSilencePreview(state, track, top, row.height),
      stretchEdges: () => {
        if (state.showGates !== false) drawStretchEdges(state, track, top, row.height);
      },
      locks: () => {
        if (state.showGates !== false) drawGateLocks(state, track, row, top);
      },
      clips: () => {
        drawClips(state, track, row, top, colours);
        drawLiveTake(state, track, row, top, colours);
      },
      placeholders: () => drawPlaceholders(state, track, row, top),
      collateral: () => {
        if (state.collateral?.tracks.includes(track.id)) drawCollateral(state, track, row, top);
      },
      candidates: () => drawCandidates(track.id, top, row.height),
      seams: () => drawSeams(state, track, top, row.height),
      automation: () => drawAutomation(state, track, top, row.height),
      previewLabel: () => drawPreviewLabel(state, track, top, row.height),
    };
    for (const layer of TRACK_LAYERS) painters[layer]();
    overlay.restore();
  }

  // The take that records now, drawn on the lane it goes to as it comes in (live-take.js): a
  // mirrored bar per pixel in the track's wave colour, and a red head where it is now. The
  // take's clips land here when it stops; this is only the picture until then.
  function drawLiveTake(state, track, row, top, colours) {
    if (!liveTake?.active) return;
    const lane = liveTake.lanes().find((entry) => entry.trackId === track.id);
    if (!lane) return;
    const cols = liveTake.columns(lane.index, {
      scroll: state.scroll,
      zoom: state.zoom,
      width: size.width,
    });
    const y = top + 2;
    const h = row.height - 4;
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, y, size.width, h);
    overlay.clip();
    overlay.fillStyle = colours.wave;
    overlay.globalAlpha = 0.9;
    const bars = liveWaveformColumns(cols, {
      mode: state.waveformMode,
      scale: scaleFor(track.kind, state.waveformScale),
      height: h,
      gain: state.waveformGain ?? 1,
    });
    for (let x = 0; x < cols.length; x += 1) {
      const top = bars[2 * x];
      const bottom = bars[2 * x + 1];
      if (bottom > top) overlay.fillRect(x, y + top, 1, bottom - top);
    }
    const head = frameToX(liveTake.headFrame, state.scroll, state.zoom);
    if (head >= 0 && head < size.width) {
      overlay.globalAlpha = 1;
      overlay.fillStyle = theme.clipping;
      overlay.fillRect(head, y, 2, h);
    }
    overlay.restore();
  }

  // Each clip's chrome: border, crossfades, name (with the open padlock), words, gain line, fade
  // handles, sibling marks, the selection outline; for missing media the error sign. No hatch:
  // a muted clip shows as an outline-only waveform (the waveform layer).
  function drawClips(state, track, row, top, colours) {
    const { width } = size;
    const marked = needsFileMark(track);
    const siblings = siblingsOf(state.project, state.selection);
    const wordsView = clipWordsView(state);
    for (const clip of paintOrder(track.clips)) {
      const left = frameToX(clip.start, state.scroll, state.zoom);
      const right = frameToX(clipEnd(clip), state.scroll, state.zoom);
      if (right < 0 || left > width) continue;
      const y = top + 2;
      const h = row.height - 4;
      const w = Math.max(1, right - left);
      const selected = state.selection.has(clip.id) || !!rangeBand?.touched?.has(clip.id);
      const missing = state.missingMedia?.has(clip.media);
      overlay.strokeStyle = theme.clipEdge;
      overlay.lineWidth = 1;
      overlay.strokeRect(left + 0.5, y + 0.5, w - 1, h - 1);
      if (missing) drawMissingMedia(left, y, w, h);
      if (clip.xfade_in) drawCrossfade(left, y, h, clip.xfade_in / state.zoom, colours.ink);
      if (clip.xfade_out) drawCrossfade(right, y, h, clip.xfade_out / state.zoom, colours.ink);
      if (row.height >= 36) drawName(state, clip, left, y, w, colours, marked);
      if (wordsView && row.height >= WORDS_MIN_LANE)
        drawClipWords(state, track, clip, wordsView, { left, y, w }, colours);
      // The gain line only where it says something: not 0 dB, an envelope, or selected.
      if (row.height >= 40 && gainLineVisible(clip, selected || Object.hasOwn(clipOvers, clip.id)))
        drawGain(state, clip, left, right, top, row.height);
      if (row.height >= 40 && (selected || clip.id === hoverClipId))
        drawFadeHandles(clip, { left, right, zoom: state.zoom }, { top, y, h });
      if (siblings.has(clip.id)) drawSiblingMarks(left, y, w, h);
      if (altTargetClip?.id === clip.id) {
        overlay.save();
        overlay.fillStyle = theme.accent;
        overlay.globalAlpha = 0.15;
        overlay.fillRect(left, y, w, h);
        overlay.strokeStyle = theme.accent;
        overlay.lineWidth = 2;
        overlay.setLineDash([4, 3]);
        overlay.strokeRect(left + 1, y + 1, w - 2, h - 2);
        overlay.restore();
      } else if (selected) {
        overlay.strokeStyle = theme.selection;
        overlay.lineWidth = 2;
        overlay.strokeRect(left + 1, y + 1, w - 2, h - 2);
      }
    }
  }

  // Missing media (owner, 2026-10-21): no waveform (the waveform layer fills the body with
  // --signal-damaged-fill and draws nothing else), a 2 px outline and a big warning sign in
  // --signal-damaged, and the words "File missing" when they fit. Unlike a silent clip (an
  // outline-only waveform in the track colour) it has no waveform at all.
  function drawMissingMedia(left, y, w, h) {
    overlay.save();
    overlay.beginPath();
    overlay.rect(left, y, w, h);
    overlay.clip();
    overlay.strokeStyle = theme.damaged;
    overlay.lineWidth = MISSING_EDGE_PX;
    overlay.strokeRect(left + 1, y + 1, w - 2, h - 2);
    const sign = Math.min(MISSING_SIGN_MAX, h - 8, w - 8);
    if (sign >= 10) {
      const visibleLeft = Math.max(left, 0);
      const visibleRight = Math.min(left + w, size.width);
      const x = Math.max(visibleLeft + 4, (visibleLeft + visibleRight) / 2 - sign / 2);
      const signY = y + (h - sign) / 2;
      drawIcon("alert", x, signY, sign, theme.damaged, 2);
      const label = t("ui.media.missing_clip");
      overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
      overlay.textBaseline = "middle";
      const textX = x + sign + 6;
      if (textX + overlay.measureText(label).width < visibleRight - 4) {
        overlay.fillStyle = theme.damaged;
        overlay.fillText(label, textX, y + h / 2);
      }
    }
    overlay.restore();
  }

  // An icon of icons.js (24 px grid, stroke paths) drawn at `px` on the canvas: the same shapes
  // as the buttons', so the timeline and the panels speak one icon language.
  const iconPaths = new Map();
  function drawIcon(name, x, y, px, colour, stroke = 2.4) {
    let path = iconPaths.get(name);
    if (!path) {
      path = new Path2D(ICONS[name]);
      iconPaths.set(name, path);
    }
    overlay.save();
    overlay.translate(x, y);
    overlay.scale(px / 24, px / 24);
    overlay.strokeStyle = colour;
    overlay.lineWidth = stroke;
    overlay.lineCap = "round";
    overlay.lineJoin = "round";
    overlay.stroke(path);
    overlay.restore();
  }

  // A padlock on a small chip of the panel colour, so it reads on a filled or an outline-only
  // waveform alike.
  function drawPadlock(name, x, y, colour) {
    overlay.save();
    overlay.fillStyle = theme.panel;
    overlay.beginPath();
    overlay.roundRect(
      x - ICON_CHIP_PAD,
      y - ICON_CHIP_PAD,
      ICON_PX + 2 * ICON_CHIP_PAD,
      ICON_PX + 2 * ICON_CHIP_PAD,
      3,
    );
    overlay.fill();
    overlay.restore();
    drawIcon(name, x, y, ICON_PX, colour);
  }

  // Narration placeholders (WP43): the `placeholder` signal of grammar.js: a dashed 1 px
  // outline, no waveform, the script text in italics inside (clipped to the width) and, when
  // the room is there, "about 6 s" while the length is still the text's estimate.
  function drawPlaceholders(state, track, row, top) {
    const all = state.project.placeholders;
    if (!all?.length) return;
    const rate = state.project.rate;
    const y = top + 2;
    const h = row.height - 4;
    for (const ph of all) {
      if (ph.track !== track.id) continue;
      const left = frameToX(ph.start, state.scroll, state.zoom);
      const right = frameToX(ph.start + ph.length, state.scroll, state.zoom);
      if (right < 0 || left > size.width) continue;
      const w = Math.max(1, right - left);
      overlay.save();
      overlay.beginPath();
      overlay.rect(left, y, w, h);
      overlay.clip();
      overlay.fillStyle = theme.panel;
      overlay.globalAlpha = 0.5;
      overlay.fillRect(left, y, w, h);
      overlay.globalAlpha = 1;
      overlay.setLineDash([5, 3]);
      overlay.strokeStyle = theme.placeholder;
      overlay.lineWidth = 1;
      overlay.strokeRect(left + 0.5, y + 0.5, w - 1, h - 1);
      overlay.setLineDash([]);
      if (row.height >= 36) {
        overlay.font = `italic ${NAME_FONT_PX}px ${theme.font}`;
        overlay.textBaseline = "top";
        const estimate = ph.estimated
          ? t("ui.placeholders.about", { seconds: aboutSeconds(ph.length, rate) })
          : "";
        const label = placeholderLabel({
          text: ph.text,
          estimate,
          width: w,
          measure: (text) => overlay.measureText(text).width,
        });
        overlay.fillStyle = theme.muted;
        overlay.fillText(label.script, left + 6, y + 5);
        if (label.estimate) {
          const used = overlay.measureText(label.script).width;
          overlay.font = `${NAME_FONT_PX}px ${theme.font}`;
          overlay.fillText(label.estimate, left + 6 + used, y + 5);
        }
      }
      if (ph.id === state.placeholderSelected) {
        overlay.strokeStyle = theme.selection;
        overlay.lineWidth = 2;
        overlay.strokeRect(left + 1, y + 1, w - 2, h - 2);
      }
      overlay.restore();
    }
  }

  // Collateral (GUI-DESIGN.md section 19): while words are selected in the transcript, the
  // stretch a cut would also take is hatched on every affected track and the clips it
  // touches are outlined dashed (the hatch and dashes are the twin of the colour).
  function drawCollateral(state, track, row, top) {
    const [from, to] = state.collateral.range;
    const x1 = frameToX(from, state.scroll, state.zoom);
    const x2 = frameToX(to, state.scroll, state.zoom);
    if (x2 < 0 || x1 > size.width) return;
    const y = top + 2;
    const h = row.height - 4;
    const w = Math.max(2, x2 - x1);
    overlay.fillStyle = theme.collateralFill;
    overlay.fillRect(x1, y, w, h);
    drawHatch(x1, y, w, h, theme.collateral);
    overlay.save();
    overlay.strokeStyle = theme.collateral;
    overlay.lineWidth = 2;
    overlay.setLineDash([4, 3]);
    for (const clip of track.clips) {
      if (clip.start >= to || clipEnd(clip) <= from) continue;
      const left = frameToX(clip.start, state.scroll, state.zoom);
      const right = frameToX(clipEnd(clip), state.scroll, state.zoom);
      overlay.strokeRect(left + 1, y + 1, Math.max(1, right - left - 2), h - 2);
    }
    overlay.restore();
  }

  // The gate (WP44): each closed stretch's waveform is outline only (the waveform layer) and
  // carries a padlock at the left of its visible part, under the name strip, never over a clip
  // border, a fade handle or a clip name (silence-visuals.js lockSpots). A stretch too narrow
  // for the icon gets none: the outline alone says silent. Runs are merged pixels (gate.js), so
  // thousands of ranges cost a few icons at most.
  // The pseudo-borders of each closed stretch (owner, 2026-10-21): it reads as its own piece,
  // but never as a clip: 1 px dashed lines in the lock colour, no handles, not draggable, and
  // left out where a real clip border is (drawn above, unchanged). silence-visuals.js
  // stretchEdges has the rules.
  function drawStretchEdges(state, track, top, rowHeight) {
    const ranges = [...(track.gate ?? []), ...track.clips.flatMap(implicitSilenceRanges)].sort(
      (a, b) => a[0] - b[0],
    );
    if (ranges.length === 0) return;
    const runs = gatePixelRuns(ranges, state.scroll, state.zoom, size.width, gateRuns);
    const clipEdges = track.clips.flatMap((clip) => [
      frameToX(clip.start, state.scroll, state.zoom),
      frameToX(clipEnd(clip), state.scroll, state.zoom),
    ]);
    const xs = stretchEdges(runs, { width: size.width, clipEdges });
    if (xs.length === 0) return;
    overlay.save();
    overlay.strokeStyle = theme.gateLock;
    overlay.lineWidth = 1;
    overlay.setLineDash(STRETCH_EDGE_DASH);
    overlay.beginPath();
    for (const x of xs) {
      overlay.moveTo(x + 0.5, top + 2);
      overlay.lineTo(x + 0.5, top + rowHeight - 2);
    }
    overlay.stroke();
    overlay.restore();
  }

  // A clip group reads as one object (owner, 2026-10-21): one 1 px rounded outline just outside
  // all its members, across tracks (group-outline.js). Drawn after every lane, so it is not cut
  // by the next lane's drawing; under the ruler.
  function drawGroupOutlines(state, layout) {
    const boxes = groupOutlines(state.project, layout.rows, {
      scroll: state.scroll,
      zoom: state.zoom,
      scrollY: state.scrollY,
      rulerHeight: RULER_HEIGHT,
    });
    if (boxes.length === 0) return;
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, RULER_HEIGHT, size.width, size.height - RULER_HEIGHT);
    overlay.clip();
    overlay.strokeStyle = theme.group;
    overlay.lineWidth = 1;
    overlay.beginPath();
    for (const box of boxes) overlay.roundRect(box.x, box.y, box.w, box.h, 4);
    overlay.stroke();
    overlay.restore();
  }

  const gateRuns = [];
  function drawGateLocks(state, track, row, top) {
    if (!track.gate?.length || row.height < 24) return;
    const runs = gatePixelRuns(track.gate, state.scroll, state.zoom, size.width, gateRuns);
    if (runs.length === 0) return;
    const blocked = [];
    for (const clip of track.clips) {
      const left = frameToX(clip.start, state.scroll, state.zoom);
      const right = frameToX(clipEnd(clip), state.scroll, state.zoom);
      if (right < -EDGE_PX || left > size.width + EDGE_PX) continue;
      blocked.push([left - EDGE_PX, left + EDGE_PX], [right - EDGE_PX, right + EDGE_PX]);
      const handles = fadeHandles(clip, { left, right, zoom: state.zoom });
      for (const side of ["in", "out"])
        blocked.push([handles[side].x - POINT_RADIUS - 2, handles[side].x + POINT_RADIUS + 2]);
    }
    // Under the name strip (and the words row), where no label can paint over it.
    const offset = lockTop(row.height, {
      label: LABEL_H,
      words: WORDS_ROW_H,
      icon: ICON_PX,
      wordsShown: Boolean(clipWordsView(state)) && row.height >= WORDS_MIN_LANE,
    });
    if (offset === null) return;
    const y = top + offset;
    for (const x of lockSpots(runs, { iconPx: ICON_PX, pad: ICON_PAD, blocked }))
      drawPadlock("lock", x, y, theme.gateLock);
  }

  // The Auto-Silence live preview (silence-panel.js): what the options WOULD close, only
  // while the panel is open. The waveform layer outlines those stretches in the preview teal;
  // here the dashed edges (paint.js drawPreviewBands) and, last of the lane, the word
  // "preview" at its left edge, so it is never read as a committed gate (outline in the track
  // colour plus a padlock). Shown even when the user hides gates: the panel is open for this.
  const previewRuns = [];
  function drawSilencePreview(state, track, top, rowHeight) {
    const ranges = state.silencePreview?.get(track.id);
    if (!ranges) return;
    const runs = gatePixelRuns(ranges, state.scroll, state.zoom, size.width, previewRuns);
    drawPreviewBands(overlay, runs, top + 2, rowHeight - 4, { edge: theme.preview });
  }

  function drawPreviewLabel(state, track, top, rowHeight) {
    if (!state.silencePreview?.get(track.id)) return;
    const y = top + 2;
    const h = rowHeight - 4;
    if (h < NAME_FONT_PX + 4) return;
    overlay.save();
    overlay.font = `${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "bottom";
    const label = t("ui.silence.lane_label");
    const w = overlay.measureText(label).width + 8;
    overlay.fillStyle = theme.panel;
    overlay.fillRect(0, y + h - NAME_FONT_PX - 4, w, NAME_FONT_PX + 4);
    overlay.fillStyle = theme.preview;
    overlay.fillText(label, 4, y + h - 2);
    overlay.restore();
  }

  // Open cut candidates (WP18): a faint fill with 1 px edges on every lane the cut would
  // touch; the current one has 2 px edges and diagonal stripes (the stripe is the twin of
  // the colour). Only the current one is striped: stripes on every band were the loudest
  // thing on screen (GUI-DESIGN.md, the table of rejected options).
  function drawCandidates(trackId, top, rowHeight) {
    const y = top + 2;
    const h = rowHeight - 4;
    for (const band of bands) {
      if (!band.tracks.includes(trackId)) continue;
      const w = band.x1 - band.x0;
      overlay.fillStyle = theme.candidateFill;
      overlay.fillRect(band.x0, y, w, h);
      if (band.current) drawHatchAt(band.x0, y, w, h, theme.candidate, CANDIDATE_STRIPE_ALPHA);
      const edge = band.current ? CANDIDATE_EDGE_CURRENT_PX : CANDIDATE_EDGE_PX;
      overlay.fillStyle = theme.candidate;
      overlay.fillRect(Math.round(band.x0), y, edge, h);
      overlay.fillRect(Math.round(band.x1) - edge, y, edge, h);
    }
  }

  function drawHatchAt(x, y, w, h, colour, alpha) {
    overlay.globalAlpha = alpha;
    drawHatch(x, y, w, h, colour);
    overlay.globalAlpha = 1;
  }

  // The ruler flag of a candidate: its length on the fill with a 3 px top edge ("cut? 2.4 s").
  // It hides the time labels under it rather than overlapping them; a band too narrow for
  // the words keeps only the edge.
  function drawCandidateFlags(state) {
    const rows = new Map((state.candidates ?? []).map((row) => [row.id, row]));
    overlay.font = `600 ${MARK_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "middle";
    for (const band of bands) {
      if (!band.flag) continue;
      const row = rows.get(band.id);
      const w = band.x1 - band.x0;
      overlay.fillStyle = theme.panel;
      overlay.fillRect(band.x0, 0, w, RULER_HEIGHT - 1);
      overlay.fillStyle = theme.candidateFill;
      overlay.fillRect(band.x0, 0, w, RULER_HEIGHT - 1);
      overlay.fillStyle = theme.candidate;
      overlay.fillRect(band.x0, 0, w, band.current ? FLAG_EDGE_CURRENT_PX : FLAG_EDGE_PX);
      const text = flagText(row, t, (value) => formatNumber(value, { digits: 1 }));
      const textWidth = overlay.measureText(text).width;
      if (!flagFits(w, textWidth)) continue;
      overlay.fillStyle = theme.ink;
      overlay.fillText(text, band.x0 + (w - textWidth) / 2, RULER_HEIGHT / 2 + 1);
    }
  }

  function drawHatch(x, y, w, h, colour) {
    drawDiagonalHatch(overlay, x, y, w, h, colour);
  }

  // A crossfade is a darker triangle pair centred on the edge: one falling, one rising.
  function drawCrossfade(edgeX, y, h, widthPx, colour) {
    const half = Math.max(2, widthPx / 2);
    overlay.fillStyle = colour;
    overlay.globalAlpha = XFADE_ALPHA;
    overlay.beginPath();
    overlay.moveTo(edgeX - half, y);
    overlay.lineTo(edgeX + half, y);
    overlay.lineTo(edgeX - half, y + h);
    overlay.closePath();
    overlay.moveTo(edgeX + half, y + h);
    overlay.lineTo(edgeX - half, y + h);
    overlay.lineTo(edgeX + half, y);
    overlay.closePath();
    overlay.fill();
    overlay.globalAlpha = 1;
  }

  // A bus row: its band, twice as strong as behind its members, so the group header
  // reads as the top of the group. Collapsed (GUI-DESIGN.md section 6): one thin strip
  // per member (ribbonLayout), in the member's own speaker hue, filled where the track
  // has a clip; muted clips are dimmer. Waveform-based activity and hover names are
  // not built yet.
  function drawBusRow(state, row, top, groups, hues) {
    const band = theme.busBands[(groups.get(row.id) ?? 1) - 1];
    if (band) {
      overlay.fillStyle = band;
      overlay.fillRect(0, top, size.width, row.height - 1);
      overlay.fillRect(0, top, size.width, row.height - 1);
    }
    if (!row.collapsed || row.memberIndexes.length === 0) return;
    const count = row.memberIndexes.length;
    const strip = Math.max(
      2,
      Math.min(ribbonLayout(count)?.strip ?? 8, Math.floor((row.height - 6) / count)),
    );
    const first = top + Math.round((row.height - count * strip) / 2);
    row.memberIndexes.forEach((index, n) => {
      const track = state.project.tracks[index];
      const colours = theme.palette[(hues.get(track.id) ?? 0) % theme.palette.length];
      overlay.fillStyle = colours?.wave ?? theme.muted;
      for (const clip of track.clips) {
        const left = frameToX(clip.start, state.scroll, state.zoom);
        const right = frameToX(clipEnd(clip), state.scroll, state.zoom);
        if (right < 0 || left > size.width) continue;
        overlay.globalAlpha = clip.muted ? 0.3 : 0.85;
        overlay.fillRect(left, first + n * strip, Math.max(1, right - left), strip - 1);
      }
    });
    overlay.globalAlpha = 1;
  }

  // Where two clips meet (grammar.js seamKind): a hairline for a clean split,
  // a notch top and bottom for a jump cut. A change of file needs neither:
  // the zebra tone and the outlines already show it.
  function drawSeams(state, track, top, rowHeight) {
    const clips = [...track.clips].sort((a, b) => a.start - b.start);
    overlay.fillStyle = theme.seam;
    for (let i = 1; i < clips.length; i += 1) {
      const kind = seamKind(clips[i - 1], clips[i]);
      if (kind !== "split" && kind !== "jump") continue;
      const x = Math.round(frameToX(clips[i].start, state.scroll, state.zoom));
      if (x < 0 || x > size.width) continue;
      const y = top + 2;
      const h = rowHeight - 4;
      if (kind === "split") {
        overlay.globalAlpha = SEAM_ALPHA;
        overlay.fillRect(x, y, 1, h);
        overlay.globalAlpha = 1;
      } else {
        overlay.beginPath();
        overlay.moveTo(x - NOTCH_PX, y);
        overlay.lineTo(x + NOTCH_PX, y);
        overlay.lineTo(x, y + NOTCH_PX + 1);
        overlay.moveTo(x - NOTCH_PX, y + h);
        overlay.lineTo(x + NOTCH_PX, y + h);
        overlay.lineTo(x, y + h - NOTCH_PX - 1);
        overlay.fill();
      }
    }
  }

  // Sync states (R51, WP19a). The server's list of drifting and free clips, indexed once per
  // list.
  let syncFrom = null;
  let syncRows = new Map();
  function syncRowsOf(state) {
    if (state.syncClips !== syncFrom) {
      syncFrom = state.syncClips;
      syncRows = syncIndex(state.syncClips);
    }
    return syncRows;
  }
  let anchorsFrom = null;
  let anchorSet = new Set();
  function anchorsOf(state) {
    if (state.syncAnchors !== anchorsFrom) {
      anchorsFrom = state.syncAnchors;
      anchorSet = anchorIds(state.syncAnchors);
    }
    return anchorSet;
  }

  // Sync drift is quiet by default; when enabled it is a tint and a compact shape, not a number.
  function drawSyncBadge(state, clip, left, y, w) {
    const mark = syncMark(syncRowsOf(state).get(clip.id), state.showSyncDrift === true);
    if (!mark || w < 24) return;
    const free = mark.kind === "free";
    const right = Math.min(left + w, size.width) - 6 - (clip.group ? 16 : 0);
    const colour = theme[mark.tint];
    overlay.save();
    overlay.fillStyle = colour;
    overlay.globalAlpha = 0.12;
    overlay.fillRect(
      Math.max(0, left),
      y + 2,
      Math.min(left + w, size.width) - Math.max(0, left),
      LABEL_H,
    );
    overlay.globalAlpha = 1;
    const x = right - (free ? 14 : 6);
    overlay.strokeStyle = colour;
    overlay.fillStyle = colour;
    overlay.lineWidth = 1.5;
    if (free) {
      // Two rings that do not touch: an unlinked chain.
      overlay.beginPath();
      overlay.roundRect(x, y + 5, 6, 5, 2.5);
      overlay.roundRect(x + 8, y + 5, 6, 5, 2.5);
      overlay.stroke();
    } else {
      overlay.beginPath();
      overlay.arc(x + 3, y + 7.5, 2.5, 0, Math.PI * 2);
      overlay.fill();
    }
    overlay.restore();
  }

  // The anchor of a sync group (its main recording's pieces) wears a small "anchor" tag, so the
  // user sees what the others are kept in sync with. Text as well as the mark; right end of the
  // label strip, where the drift badge of the others sits.
  function drawAnchorTag(state, clip, left, y, w, colours) {
    if (!anchorsOf(state).has(clip.id) || w < 24) return;
    const right = Math.min(left + w, size.width) - 6 - (clip.group ? 16 : 0);
    overlay.save();
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    const text = t("ui.sync.anchor_tag");
    const wide = w >= 40 + overlay.measureText(text).width + 16;
    const textWidth = wide ? overlay.measureText(text).width + 3 : 0;
    const x = right - textWidth - 9;
    overlay.fillStyle = colours.fill;
    overlay.globalAlpha = LABEL_BACKING_ALPHA;
    overlay.fillRect(x - 3, y + 2, textWidth + 9 + 6, LABEL_H);
    overlay.globalAlpha = 1;
    overlay.fillStyle = theme.selection;
    overlay.beginPath();
    overlay.moveTo(x + 3.5, y + 4);
    overlay.lineTo(x + 7, y + 8);
    overlay.lineTo(x + 3.5, y + 12);
    overlay.lineTo(x, y + 8);
    overlay.closePath();
    overlay.fill();
    if (wide) overlay.fillText(text, x + 10, y + 3);
    overlay.restore();
  }

  // A grouped clip (clip.group) wears a thin link mark, two joined rings, at the right
  // end of its label strip. Groups have no colour in this version.
  function drawGroupBadge(left, y, w, colours) {
    if (w < 24) return;
    const x = Math.min(left + w, size.width) - 16;
    overlay.save();
    overlay.strokeStyle = colours.label;
    overlay.lineWidth = 1.5;
    overlay.beginPath();
    overlay.roundRect(x, y + 5, 7, 5, 2.5);
    overlay.roundRect(x + 4, y + 5, 7, 5, 2.5);
    overlay.stroke();
    overlay.restore();
  }

  // The clip's name on a backing of its body colour, so bars never cross the
  // text; before it, the file mark when the track holds more than one file.
  // The label says what the clip is, by the width there is (labels.js):
  // nothing, the person, "Olli 3", "Olli 3 · 1:20–3:20", then the first words.
  function drawName(state, clip, left, y, w, colours, marked) {
    if (clip.group) drawGroupBadge(left, y, w, colours);
    drawSyncBadge(state, clip, left, y, w);
    drawAnchorTag(state, clip, left, y, w, colours);
    const media = state.project.media.find((item) => item.id === clip.media);
    if (!media || w < 30) return;
    let x = Math.max(left, 0) + 5;
    if (marked) x = drawFileMark(fileMark(media.sha256), x, y, colours.ink);
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    const visible = Math.min(left + w, size.width) - x;
    const text = clipLabel(labelFacts(state.project, clip, labelWords(state)), visible, {
      measure: (value) => overlay.measureText(value).width,
    });
    if (!text) return;
    const textWidth = overlay.measureText(text).width;
    overlay.save();
    overlay.beginPath();
    overlay.rect(left, y, w - 4, LABEL_H + 4);
    overlay.clip();
    overlay.fillStyle = colours.fill;
    overlay.globalAlpha = LABEL_BACKING_ALPHA;
    overlay.fillRect(x - 3, y + 2, textWidth + 6, LABEL_H);
    overlay.globalAlpha = 1;
    overlay.fillStyle = colours.label;
    overlay.fillText(text, x, y + 3);
    overlay.restore();
    // A clip that keeps the mic open: the open padlock after its name (the pair of the gate's
    // closed one), clear of the right edge zone and the badges there.
    // A muted clip carries a crossed-out speaker in the same place, so it is told apart from a
    // stretch Auto-Silence closed (owner, 2026-10-24: they looked alike).
    const stateIcon = clip.muted ? "mute" : clip.ungated ? "unlock" : null;
    if (stateIcon) {
      const badges = clip.group || syncRowsOf(state).has(clip.id) ? 40 : 0;
      const spot = openLockSpot({
        after: x + textWidth + 3,
        limit: Math.min(left + w, size.width) - EDGE_PX - badges,
        iconPx: ICON_PX,
        gap: 4,
      });
      if (spot !== null)
        drawPadlock(stateIcon, spot, y + 3, stateIcon === "mute" ? colours.label : theme.gateOpen);
    }
  }

  // Words in the clips (WP69, clip-words.js). Nothing is looked up when the option is off, there
  // are no words, or the zoom is too wide for the average word to be readable; the average is
  // measured once per words list.
  let averageFrom = null;
  let averageFrames = 0;
  function clipWordsView(state) {
    const words = state.words;
    if (state.showClipWords === false || !words?.length) return null;
    if (words !== averageFrom) {
      averageFrom = words;
      averageFrames = averageWordFrames(words);
    }
    if (!wordsWideEnough(averageFrames, state.zoom)) return null;
    return {
      words,
      current: wordAtTime(words, state.playhead ?? 0),
      selected: selectionBounds(state.transcriptSelection),
      lookback: WORDS_LOOKBACK_S * (state.project?.rate ?? 48000),
    };
  }

  function drawClipWords(state, track, clip, view, box, colours) {
    const { left, y, w } = box;
    overlay.font = `${WORDS_FONT_PX}px ${theme.font}`;
    const items = layoutClipWords({
      words: view.words,
      trackId: track.id,
      clip,
      scroll: state.scroll,
      zoom: state.zoom,
      viewWidth: size.width,
      lookback: view.lookback,
      measure: (text) => overlay.measureText(text).width,
      current: view.current,
      selected: view.selected,
    });
    if (items.length === 0) return;
    const rowY = y + LABEL_H + 4;
    overlay.save();
    overlay.beginPath();
    overlay.rect(left + 1, rowY, w - 2, WORDS_ROW_H);
    overlay.clip();
    const base = 1; // a muted clip is outline-only, never dimmed (SILENCE-VISUALS.md)
    overlay.textBaseline = "top";
    overlay.fillStyle = colours.fill;
    overlay.globalAlpha = base * WORDS_BACKING_ALPHA;
    overlay.fillRect(left + 1, rowY, w - 2, WORDS_ROW_H);
    overlay.fillStyle = theme.selection;
    overlay.globalAlpha = base * WORDS_SELECTED_ALPHA;
    for (const item of items) {
      if (item.mark === "selected") overlay.fillRect(item.x, rowY, item.w, WORDS_ROW_H);
    }
    for (const item of items) {
      const bright = item.mark !== "plain";
      overlay.fillStyle = bright ? theme.ink : colours.label;
      overlay.globalAlpha = base * (bright ? 1 : WORDS_PLAIN_ALPHA);
      overlay.fillText(item.text, item.x, rowY + 1);
    }
    overlay.restore();
  }

  // Timeline words in the label's shape, converted once per words list.
  let wordsFrom = null;
  let wordsShaped = [];
  function labelWords(state) {
    if (state.words !== wordsFrom) {
      wordsFrom = state.words;
      wordsShaped = (state.words ?? []).map((word) => ({
        start: word.s,
        end: word.e,
        text: word.w,
      }));
    }
    return wordsShaped;
  }

  // Siblings (same recording as a selected clip, any track): small corner
  // brackets in the sibling colour; the overview marks them too.
  function drawSiblingMarks(left, y, w, h) {
    const arm = Math.min(BRACKET_PX, w / 3);
    overlay.strokeStyle = theme.sibling;
    overlay.lineWidth = 2;
    overlay.beginPath();
    overlay.moveTo(left + 1, y + arm);
    overlay.lineTo(left + 1, y + 1);
    overlay.lineTo(left + arm, y + 1);
    overlay.moveTo(left + w - arm, y + 1);
    overlay.lineTo(left + w - 1, y + 1);
    overlay.lineTo(left + w - 1, y + arm);
    overlay.moveTo(left + 1, y + h - arm);
    overlay.lineTo(left + 1, y + h - 1);
    overlay.lineTo(left + arm, y + h - 1);
    overlay.moveTo(left + w - arm, y + h - 1);
    overlay.lineTo(left + w - 1, y + h - 1);
    overlay.lineTo(left + w - 1, y + h - arm);
    overlay.stroke();
  }

  // The file mark: two characters from the content hash in a small chip.
  function drawFileMark(text, x, y, edge) {
    if (!text) return x;
    overlay.font = `600 ${MARK_FONT_PX}px ${theme.mono}`;
    overlay.textBaseline = "top";
    const w = overlay.measureText(text).width + 6;
    overlay.fillStyle = theme.fileMark;
    overlay.fillRect(x - 2, y + 3, w, LABEL_H - 2);
    overlay.strokeStyle = edge;
    overlay.lineWidth = 1;
    overlay.strokeRect(x - 1.5, y + 3.5, w - 1, LABEL_H - 3);
    overlay.fillStyle = theme.fileMarkText;
    overlay.fillText(text, x + 1, y + 4);
    return x + w + 4;
  }

  // Clip gain: a dashed line at gain_db; envelope points as dots joined by lines.
  function drawGain(state, clip, left, right, top, rowHeight) {
    const baseline = top + dbToY(clip.gain_db ?? 0, rowHeight);
    const hot = Object.hasOwn(clipOvers, clip.id);
    const lineColour = hot ? theme.clipping : theme.gain;
    overlay.strokeStyle = lineColour;
    overlay.globalAlpha = GAIN_ALPHA;
    overlay.setLineDash([4, 3]);
    overlay.lineWidth = 1;
    overlay.beginPath();
    overlay.moveTo(left, baseline);
    overlay.lineTo(right, baseline);
    overlay.stroke();
    overlay.setLineDash([]);
    const points = (clip.envelope ?? []).map(([frame, db]) => [
      frameToX(envelopeFrame(clip, frame), state.scroll, state.zoom),
      top + dbToY((clip.gain_db ?? 0) + db, rowHeight),
    ]);
    if (points.length > 0) {
      overlay.beginPath();
      for (const [i, [x, y]] of points.entries()) {
        if (i === 0) overlay.moveTo(x, y);
        else overlay.lineTo(x, y);
      }
      overlay.stroke();
      overlay.fillStyle = lineColour;
      for (const [x, y] of points) {
        overlay.beginPath();
        overlay.arc(x, y, POINT_RADIUS, 0, Math.PI * 2);
        overlay.fill();
      }
    }
    overlay.globalAlpha = 1;
  }

  // Fade handles (WP6): a dot at the end of each fade, with the fade's shape as a line from
  // the clip's bottom corner while a fade is set.
  function drawFadeHandles(clip, frame, box) {
    const handles = fadeHandles(clip, frame);
    overlay.strokeStyle = theme.gain;
    overlay.fillStyle = theme.accent;
    overlay.lineWidth = 1;
    for (const side of ["in", "out"]) {
      if (clip[`fade_${side}`] > 0) {
        const shape = fadeShape(clip, side, { ...frame, top: box.y, height: box.h });
        overlay.beginPath();
        overlay.moveTo(shape[0][0], shape[0][1]);
        overlay.lineTo(shape[1][0], shape[1][1]);
        overlay.stroke();
      }
      overlay.beginPath();
      overlay.arc(handles[side].x, box.top + handles[side].y, POINT_RADIUS + 0.5, 0, Math.PI * 2);
      overlay.fill();
    }
  }

  // Track automation (the ducking curve): a thin line in the lower third of the lane.
  function drawAutomation(state, track, top, rowHeight) {
    if (!track.automation?.length || rowHeight < 40) return;
    const bottom = top + rowHeight - 3;
    const band = rowHeight / 3 - 4;
    overlay.strokeStyle = theme.automation;
    overlay.lineWidth = 1.5;
    overlay.beginPath();
    track.automation.forEach(([frame, db], i) => {
      const x = frameToX(frame, state.scroll, state.zoom);
      const y = bottom - band * (1 - Math.max(-24, Math.min(0, db)) / -24);
      if (i === 0) overlay.moveTo(x, y);
      else overlay.lineTo(x, y);
    });
    overlay.stroke();
  }

  // The loop range (WP50): an accent band over the ruler while the loop is on.
  function drawLoop(state) {
    const loop = activeLoop(state);
    if (!loop) return;
    const x1 = frameToX(loop[0], state.scroll, state.zoom);
    const x2 = frameToX(loop[1], state.scroll, state.zoom);
    overlay.save();
    overlay.globalAlpha = 0.28;
    overlay.fillStyle = theme.accent;
    overlay.fillRect(x1, 0, x2 - x1, RULER_HEIGHT - 1);
    overlay.restore();
  }

  function drawRuler(state, rate) {
    const { width } = size;
    overlay.fillStyle = theme.panel;
    overlay.fillRect(0, 0, width, RULER_HEIGHT);
    overlay.fillStyle = theme.rule;
    overlay.fillRect(0, RULER_HEIGHT - 1, width, 1);
    drawLoop(state);
    overlay.font = `11px ${theme.mono}`;
    overlay.textBaseline = "top";
    for (const tick of rulerTicks({ scroll: state.scroll, zoom: state.zoom, width, rate })) {
      const major = tick.label !== null;
      const x = Math.round(tick.x);
      overlay.fillStyle = theme.rulerTick;
      overlay.fillRect(x, RULER_HEIGHT - (major ? 9 : 4), 1, major ? 9 : 4);
      if (major) {
        overlay.fillStyle = theme.rulerText;
        overlay.fillText(tick.label, x + 4, 5);
      }
    }
    drawCandidateFlags(state);
    drawMarkerFlags(state);
    drawLeftOffFlag(state);
  }

  // The automatic "left off" flag (left-off.js; not a project marker): a dashed pole and a
  // diamond in the accent colour, so it cannot be mistaken for a marker's note-coloured
  // pennant, and its name when there is room to the right.
  function drawLeftOffFlag(state) {
    const flag = leftOffFlag(state.leftOff, {
      scroll: state.scroll,
      zoom: state.zoom,
      width: size.width,
    });
    if (!flag) return;
    const x = Math.round(flag.x);
    const half = MARKER_FLAG_H / 2;
    const top = RULER_HEIGHT - 2 * half - 2;
    overlay.fillStyle = theme.accent;
    overlay.strokeStyle = theme.accent;
    overlay.lineWidth = 1;
    overlay.setLineDash([2, 2]);
    overlay.beginPath();
    overlay.moveTo(x + 0.5, 0);
    overlay.lineTo(x + 0.5, top);
    overlay.stroke();
    overlay.setLineDash([]);
    overlay.beginPath();
    overlay.moveTo(x, top);
    overlay.lineTo(x + half, top + half);
    overlay.lineTo(x, top + 2 * half);
    overlay.lineTo(x - half, top + half);
    overlay.closePath();
    overlay.fill();
    overlay.font = `600 ${MARK_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "middle";
    const label = t("ui.resume.flag");
    const w = overlay.measureText(label).width;
    if (x + half + 3 + w < size.width) {
      overlay.fillStyle = theme.panel;
      overlay.fillRect(x + half + 1, 1, w + 4, RULER_HEIGHT - 3);
      overlay.fillStyle = theme.accent;
      overlay.fillText(label, x + half + 3, RULER_HEIGHT / 2 + 1);
    }
  }

  // Markers, chapters and regions (WP19h) in the ruler, in the note colour: a marker is a
  // pennant on a pole, a chapter a square flag, a region a 5 px bar along the top with
  // posts at its ends. The name goes beside a flag only when it fits before the next one
  // (markers-model.js), on a panel-coloured backing so it hides the time labels under it.
  function drawMarkerFlags(state) {
    const markers = state.project?.markers;
    if (!markers?.length) return;
    overlay.font = `600 ${MARK_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "middle";
    const { flags, bars } = flagLayout(markers, {
      scroll: state.scroll,
      zoom: state.zoom,
      width: size.width,
      measure: (text) => overlay.measureText(text).width,
    });
    const middle = RULER_HEIGHT / 2 + 1;
    const backed = (x, label) => {
      const w = overlay.measureText(label).width;
      overlay.fillStyle = theme.panel;
      overlay.fillRect(x - 2, 1, w + 4, RULER_HEIGHT - 3);
      overlay.fillStyle = theme.ink;
      overlay.fillText(label, x, middle);
    };
    for (const bar of bars) {
      overlay.fillStyle = theme.note;
      overlay.globalAlpha = bar.id === state.markerSelected ? 0.9 : 0.55;
      overlay.fillRect(bar.x0, 0, bar.x1 - bar.x0, REGION_BAR_PX);
      overlay.globalAlpha = 1;
      if (bar.startsInView) overlay.fillRect(Math.round(bar.x0), 0, 2, RULER_HEIGHT - 1);
      if (bar.x1 < size.width) overlay.fillRect(Math.round(bar.x1) - 2, 0, 2, RULER_HEIGHT - 1);
      if (bar.label) backed(bar.labelX, bar.label);
    }
    for (const flag of flags) {
      const x = Math.round(flag.x);
      const picked = flag.id === state.markerSelected;
      overlay.fillStyle = theme.note;
      overlay.fillRect(x, 0, picked ? 2 : 1, RULER_HEIGHT - 1);
      overlay.beginPath();
      if (flag.kind === "chapter") {
        overlay.rect(x, 0, MARKER_NOTCH_PX, MARKER_FLAG_H);
      } else {
        overlay.moveTo(x, 0);
        overlay.lineTo(x + MARKER_NOTCH_PX, MARKER_FLAG_H / 2);
        overlay.lineTo(x, MARKER_FLAG_H);
        overlay.closePath();
      }
      overlay.fill();
      if (flag.label) backed(flag.labelX, flag.label);
    }
  }

  function drawPlayhead(state, height) {
    const x = Math.round(frameToX(playheadAt(state), state.scroll, state.zoom)) + 0.5;
    if (x < -6 || x > size.width + 6) return;
    overlay.strokeStyle = theme.playhead;
    overlay.fillStyle = theme.playhead;
    overlay.lineWidth = 1;
    overlay.beginPath();
    overlay.moveTo(x, 0);
    overlay.lineTo(x, height);
    overlay.stroke();
    // The cap: a pentagon in the ruler, so the playhead reads at a glance.
    overlay.beginPath();
    overlay.moveTo(x - PLAYHEAD_CAP, 0);
    overlay.lineTo(x + PLAYHEAD_CAP, 0);
    overlay.lineTo(x + PLAYHEAD_CAP, 6);
    overlay.lineTo(x, 11);
    overlay.lineTo(x - PLAYHEAD_CAP, 6);
    overlay.closePath();
    overlay.fill();
  }

  // -- pointer and wheel -----------------------------------------------------------

  function locate(event) {
    const rect = overlayCanvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function hitAt(event) {
    const state = getState();
    const { x, y } = locate(event);
    const layout = layoutFor(state);
    return hitTest({ layout, project: state.project, view: { ...state, width: size.width }, x, y });
  }

  // Over an implicit portion the tooltip explains M; over a
  // narration placeholder (WP43) it says it is to be recorded and that Enter edits it.
  // What the sync badge, the anchor tag and a moved clip say on hover: relative to which anchor,
  // and which track the clip came from.
  function syncTooltip(state, clip) {
    const lines = [];
    const row = syncRowsOf(state).get(clip.id);
    const anchor = anchorNameFor(state.project, state.syncAnchors, clip);
    if (anchorsOf(state).has(clip.id)) lines.push(t("ui.sync.anchor_title"));
    else if (state.showSyncDrift === true && (row?.state === "drift" || row?.state === "free")) {
      const offset = formatOffset(row.offset, state.project.rate, (v) =>
        formatNumber(v, { digits: 1 }),
      );
      if (row.state === "drift")
        lines.push(t("ui.sync.badge.drift_title_anchor", { offset, anchor }));
      else lines.push(t("ui.sync.badge.free_title_anchor", { anchor, offset }));
    }
    const track = state.project.tracks.find((tr) => tr.clips.some((c) => c.id === clip.id));
    const home = homeNameFor(state.project, clip, track?.id);
    if (home) lines.push(t("ui.sync.moved_from", { track: home }));
    return lines.join("\n");
  }

  function hoverGate(event) {
    const hit = hitAt(event);
    let text = "";
    const lost = hit.clip && getState().missingMedia?.has(hit.clip.media);
    if (hit.placeholder && !hit.clip) text = t("ui.placeholders.hover");
    else if (lost) text = t("ui.media.missing_hover");
    else if (hit.gate)
      text = t(hit.gate.closed === false ? "ui.gate.open_portion_hover" : "ui.gate.hover");
    else if (hit.clip?.ungated) text = t("ui.gate.open_hover");
    else if (hit.clip && Object.hasOwn(clipOvers, hit.clip.id))
      text = overLabel(clipOvers[hit.clip.id], t, (value) => formatNumber(value, { digits: 1 }));
    else if (hit.clip) text = syncTooltip(getState(), hit.clip);
    if (text) overlayCanvas.dataset.tip = text;
    else delete overlayCanvas.dataset.tip;
  }
  // The ruler scrub (WP26): a drag on the ruler plays the audio under the pointer at the
  // pointer's speed, tape-style (up to 2x) and as grains above. Release plays on as before.
  let rulerScrub = null;
  let rulerScrubPointer = null;
  function endRulerScrub() {
    rulerScrub?.up();
    rulerScrub = null;
    if (rulerScrubPointer !== null) overlayCanvas.releasePointerCapture?.(rulerScrubPointer);
    rulerScrubPointer = null;
  }
  window.addEventListener("pointerup", (event) => {
    if (rulerScrub && event.pointerId === rulerScrubPointer) endRulerScrub();
  });
  overlayCanvas.addEventListener("pointermove", (event) => {
    const state = getState();
    pointerFrame = Math.max(0, xToFrame(locate(event).x, state.scroll, state.zoom));
    if (rulerScrub && event.pointerId === rulerScrubPointer) {
      rulerScrub.move(Math.max(0, pointerFrame), event.timeStamp);
      return;
    }
    if (edgeSession) {
      if (event.pointerId === edgeSession.pointerId) updateEdge(event);
      return;
    }
    if (clipSession) {
      if (event.pointerId === clipSession.pointerId) updateClip(event);
      return;
    }
    if (tweakSession) {
      if (event.pointerId === tweakSession.pointerId) updateTweak(event);
      return;
    }
    if (!state.project) return;
    hoverGate(event);
    const hit = hitAt(event);
    const hovered = hit.row?.kind === "track" ? (hit.clip?.id ?? null) : null;
    if (hovered !== hoverClipId) {
      hoverClipId = hovered;
      requestOverlay();
    }
    let cursor = hit.clip && hit.edge && hit.row?.kind === "track" ? "ew-resize" : "";
    // Cmd/Ctrl over an edge: it trims only this clip, shown by a different cursor.
    if (cursor && edgeMod(event) && !event.altKey) cursor = "col-resize";
    const zone = tweakZone(hit, event, state.selection);
    if (!cursor && zone) {
      if (zone.kind === "gain") cursor = "ns-resize";
      else if (zone.kind === "envelope") cursor = "move";
      else cursor = "ew-resize";
    }
    if (!cursor && canStartClipDrag(hit)) {
      // The hand shows where a plain drag moves the clip: everywhere in move mode, only on the
      // label strip in range mode (where the rest of the clip paints a range).
      const moves =
        dragIntent({
          mode: state.dragMode ?? DEFAULT_DRAG_MODE,
          hit,
          rowY: rowYOf(event, hit),
          shift: event.shiftKey,
          alt: event.altKey,
          mod: modClick(event, detectPlatform()),
          inSelection: Boolean(hit.clip && state.selection.has(hit.clip.id)),
          selectionSize: state.selection.size,
        }) === "move";
      cursor = moves ? "grab" : "crosshair";
    }
    lastPointerHit = hit;
    altKeyHeld = event.altKey;
    const isAltMute =
      event.altKey &&
      !event.shiftKey &&
      !modClick(event, detectPlatform()) &&
      hit.clip &&
      hit.row?.kind === "track" &&
      !hit.edge &&
      !zone;
    const nextAltTarget = isAltMute ? hit.clip : null;
    if (nextAltTarget?.id !== altTargetClip?.id) {
      altTargetClip = nextAltTarget;
      actions.hint?.(
        nextAltTarget
          ? nextAltTarget.muted
            ? t("ui.hint.alt_unmute")
            : t("ui.hint.alt_mute")
          : "",
      );
      requestOverlay();
    }
    if (isAltMute) cursor = "pointer";
    if (overlayCanvas.style.cursor !== cursor) overlayCanvas.style.cursor = cursor;
  });
  overlayCanvas.addEventListener("pointerleave", () => {
    pointerFrame = null;
    lastPointerHit = null;
    if (altTargetClip !== null) {
      altTargetClip = null;
      actions.hint?.("");
      requestOverlay();
    }
    if (hoverClipId !== null && !tweakSession) {
      hoverClipId = null;
      requestOverlay();
    }
  });
  const onWindowAlt = (e) => {
    if (e.key !== "Alt") return;
    const down = e.type === "keydown";
    if (down === altKeyHeld) return;
    altKeyHeld = down;
    if (tweakSession || clipSession || edgeSession) return;
    const hit = lastPointerHit;
    const isAltMute =
      down &&
      !e.shiftKey &&
      !modClick(e, detectPlatform()) &&
      hit?.clip &&
      hit.row?.kind === "track" &&
      !hit.edge;
    const nextAltTarget = isAltMute ? hit.clip : null;
    if (nextAltTarget?.id !== altTargetClip?.id) {
      altTargetClip = nextAltTarget;
      actions.hint?.(
        nextAltTarget
          ? nextAltTarget.muted
            ? t("ui.hint.alt_unmute")
            : t("ui.hint.alt_mute")
          : "",
      );
      overlayCanvas.style.cursor = isAltMute ? "pointer" : "";
      requestOverlay();
    }
  };
  window.addEventListener?.("keydown", onWindowAlt, true);
  window.addEventListener?.("keyup", onWindowAlt, true);
  overlayCanvas.addEventListener("dblclick", (event) => {
    if (!getState().project || event.button !== 0) return;
    if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
    const hit = hitAt(event);
    const { placeholder, clip } = hit;
    // A clip whose file is missing: straight to File > Locate media… (owner, 2026-10-21).
    if (clip && hit.row?.kind === "track" && getState().missingMedia?.has(clip.media)) {
      actions.locateMedia?.();
      return;
    }
    // Near a clip's gain line (or on one of its points): add or remove an envelope point.
    // Anywhere else the double-click keeps its other meanings below.
    if (clip && hit.row?.kind === "track" && !hit.edge) {
      const state = getState();
      const change = envelopeToggle(clip, {
        timelineFrame: hit.frame,
        rowHeight: hit.row.height,
        rowY: rowYOf(event, hit),
        point: hit.point,
      });
      if (change && gainLineVisible(clip, state.selection.has(clip.id))) {
        actions.clipEnvelope({ clipId: clip.id, points: change.points });
        return;
      }
    }
    if (placeholder && !clip) actions.editPlaceholder(placeholder);
  });
  // Right-click: the browser's menu never opens; the app shows the timeline menu for what is
  // under the pointer. The press itself (button 2) is ignored by the pointerdown handler
  // below, so it starts no drag and moves nothing; the app decides what it selects.
  overlayCanvas.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    if (!getState().project || edgeSession || clipSession || tweakSession) return;
    actions.contextMenu?.(hitAt(event), event);
  });
  // Dragging a clip edge (WP6). A press on the edge zone behaves as a click (selects, sets the
  // cursor) and also arms a session; after DRAG_PX of travel it is a drag: ghost while moving,
  // Shift (any time) switches roll to ripple, Esc cancels, release sends the edit.
  function edgeTarget(session) {
    const state = getState();
    const track = state.project.tracks.find((item) => item.id === session.trackId);
    const clip = track?.clips.find((item) => item.id === session.clipId);
    return { state, track, clip };
  }

  // Cmd on a Mac, Ctrl elsewhere (the same `mod` as everywhere else).
  const edgeMod = (event) => heldFromEvent(event, detectPlatform()).mod;

  function startEdge(hit, event) {
    edgeSession = {
      clipId: hit.clip.id,
      trackId: hit.row.id,
      edge: hit.edge,
      // Plain edge trims have no snap today; only the held modifier enables it.
      snap: createDragSnap(getState().project, [hit.clip.id], getState(), {
        primaryWithoutModifier: false,
      }),
      implicitRange: hit.implicitRange ?? null,
      origin: locate(event),
      pointerId: event.pointerId,
      dragging: false,
      seekFrame: hit.frame,
      ripple: event.shiftKey,
      overwrite: !event.altKey, // Alt held: the edge stops at the neighbour; read live
      mod: edgeMod(event), // Cmd/Ctrl held: trim only this clip (unless Alt); read live
      alone: edgeMod(event) && !event.altKey,
      raw: null,
      frame: hit.implicitRange
        ? hit.implicitRange[hit.edge === "start" ? 0 : 1]
        : hit.edge === "start"
          ? hit.clip.start
          : hit.clip.start + hit.clip.length,
    };
    overlayCanvas.setPointerCapture?.(event.pointerId);
    window.addEventListener("keydown", edgeKey, true);
    window.addEventListener("keyup", edgeKey, true);
  }

  // The edge's frame under the pointer, clamped by the rules of the current mode.
  function clampEdge() {
    const { state, track, clip } = edgeTarget(edgeSession);
    if (!clip || edgeSession.raw === null) return;
    edgeSession.snap.update({ mod: edgeSession.mod, alt: !edgeSession.overwrite });
    const snapped = edgeSession.snap.snap({
      moved: [{ start: 0, end: 0 }],
      delta: edgeSession.raw,
      zoom: state.zoom,
    });
    if (edgeSession.implicitRange) {
      edgeSession.frame = clampImplicitEdge(
        clip,
        snapped.delta,
        edgeSession.implicitRange,
        edgeSession.edge,
      );
      return;
    }
    edgeSession.frame = resolveEdge(state.project, track, clip, edgeSession.edge, snapped.delta, {
      ripple: edgeSession.ripple,
      overwrite: edgeSession.overwrite,
      alone: edgeSession.alone,
    }).frame;
  }

  function updateEdge(event) {
    const session = edgeSession;
    const point = locate(event);
    session.ripple = event.shiftKey;
    session.overwrite = !event.altKey;
    session.mod = edgeMod(event);
    session.alone = session.mod && session.overwrite; // Cmd+Alt is not "alone": Alt wins
    if (!session.dragging) {
      if (!isDrag(session.origin, point)) return;
      session.dragging = true;
    }
    overlayCanvas.style.cursor = session.alone && !session.ripple ? "col-resize" : "ew-resize";
    const state = getState();
    session.raw = xToFrame(point.x, state.scroll, state.zoom);
    clampEdge();
    requestOverlay();
  }

  function endEdge(commit) {
    const session = edgeSession;
    session.snap.end();
    edgeSession = null;
    overlayCanvas.style.cursor = "";
    window.removeEventListener("keydown", edgeKey, true);
    window.removeEventListener("keyup", edgeKey, true);
    overlayCanvas.releasePointerCapture?.(session.pointerId);
    requestOverlay();
    // A press without travel only positions the cursor. Materialization requires a drag
    // or the user's mute command; clicking near a dotted boundary must not change audio.
    if (commit && !session.dragging) actions.clickSeek?.(session.seekFrame);
    if (commit && session.dragging) {
      actions.edgeDrag({
        clipId: session.clipId,
        trackId: session.trackId,
        edge: session.edge,
        frame: session.frame,
        ripple: session.ripple,
        overwrite: session.overwrite,
        alone: session.alone,
        implicitRange: session.implicitRange,
      });
    }
  }

  function edgeKey(event) {
    if (!edgeSession) return;
    if (event.key === "Escape" && event.type === "keydown") {
      event.preventDefault();
      event.stopPropagation();
      endEdge(false);
    } else if (event.key === "Shift") {
      edgeSession.ripple = event.type === "keydown";
      clampEdge();
      requestOverlay();
    } else if (event.key === "Alt") {
      edgeSession.overwrite = event.type !== "keydown";
      edgeSession.alone = edgeSession.mod && edgeSession.overwrite;
      clampEdge();
      requestOverlay();
    } else if (event.key === (detectPlatform() === "mac" ? "Meta" : "Control")) {
      edgeSession.mod = event.type === "keydown";
      edgeSession.alone = edgeSession.mod && edgeSession.overwrite;
      clampEdge();
      requestOverlay();
    }
  }

  overlayCanvas.addEventListener("pointerup", (event) => {
    if (tweakSession && event.pointerId === tweakSession.pointerId) {
      if (tweakSession.dragging) updateTweak(event);
      endTweak(false);
      return;
    }
    if (clipSession && event.pointerId === clipSession.pointerId) {
      if (clipSession.dragging || clipSession.opening) updateClip(event);
      endClip(true);
      return;
    }
    if (!edgeSession || event.pointerId !== edgeSession.pointerId) return;
    if (edgeSession.dragging) updateEdge(event);
    endEdge(true);
  });
  overlayCanvas.addEventListener("pointercancel", () => {
    if (rulerScrub) endRulerScrub();
    if (clipSession) endClip(false);
    if (tweakSession) endTweak(true);
    if (edgeSession) endEdge(false);
  });
  overlayCanvas.addEventListener("pointerdown", (event) => {
    if (!getState().project || event.button !== 0) return;
    overlayCanvas.focus();
    const hit = hitAt(event);
    const before = getState().selection; // the press may replace it; a move takes the old one
    const zone = event.shiftKey ? null : tweakZone(hit, event, before);
    // What a drag does is a preference (drag-mode.js): paint a range, or move the clip.
    const intent = dragIntent({
      mode: getState().dragMode ?? DEFAULT_DRAG_MODE,
      hit,
      rowY: hit.row ? rowYOf(event, hit) : -1,
      shift: event.shiftKey,
      alt: event.altKey,
      mod: modClick(event, detectPlatform()),
      inSelection: Boolean(hit.clip && before.has(hit.clip.id)),
      selectionSize: before.size,
    });
    const moving = !zone && intent === "move" && canStartClipDrag(hit);
    // Adjusting a clip (move, trim, gain, fade) must not drag the play cursor along: the press
    // selects, and the cursor goes there on release only when the press turned out to be a click.
    const adjusting = Boolean(
      zone || moving || (hit.clip && hit.edge && hit.row?.kind === "track"),
    );
    actions.pointerDown(hit, event, { noSeek: adjusting });
    // A press on the ruler (not on a marker flag) goes on as a scrub while the button is down.
    if (hit.area === "ruler" && !hit.marker && actions.scrub) {
      rulerScrub = createRulerScrub({
        send: (frame, velocity) => actions.scrub(frame, velocity),
        rate: getState().project.rate,
      });
      rulerScrubPointer = event.pointerId;
      rulerScrub.down(hit.frame, event.timeStamp);
      overlayCanvas.setPointerCapture?.(event.pointerId);
    }
    if (!zone && !moving && intent === "range") beginRangeDrag(event, hit);
    if (hit.clip && hit.edge && hit.row?.kind === "track") startEdge(hit, event);
    else if (zone) startTweak(hit, event, zone);
    else if (moving)
      startClip(hit, event, before, portionDragEdit(getState().project, hit, before));
  });

  // Dragging a clip's gain line, envelope point or fade handle (WP6): live edits (coalesced by
  // the app, so one undo step); Esc puts the value back. A short press is a click.
  function tweakZone(hit, event, selection) {
    if (!hit.clip || hit.row?.kind !== "track" || hit.edge) return null;
    const pointZone = envelopePointZone(hit);
    if (pointZone) return pointZone;
    const state = getState();
    const x = locate(event).x;
    const rowY = rowYOf(event, hit);
    const frame = {
      left: frameToX(hit.clip.start, state.scroll, state.zoom),
      right: frameToX(clipEnd(hit.clip), state.scroll, state.zoom),
      zoom: state.zoom,
    };
    const side = fadeHandleAt(hit.clip, frame, x, rowY, hit.row.height);
    if (side) return { kind: "fade", side };
    if (hit.point == null && gainLineVisible(hit.clip, selection?.has(hit.clip.id))) {
      if (gainLineHit(hit.clip, hit.row.height, rowY)) return { kind: "gain" };
    }
    return null;
  }

  function startTweak(hit, event, zone) {
    const clip = hit.clip;
    const origin = locate(event);
    const rowY = rowYOf(event, hit);
    const envelopePoint = zone.kind === "envelope" ? clip.envelope[zone.point] : null;
    const pointY = envelopePoint
      ? dbToY((clip.gain_db ?? 0) + envelopePoint[1], hit.row.height)
      : null;
    let start;
    let grab;
    if (zone.kind === "gain") {
      start = clip.gain_db ?? 0;
      grab = gainGrab(clip, hit.row.height, rowY);
    } else if (zone.kind === "envelope") {
      start = clip.envelope.map(([frame, db]) => [frame, db]);
      grab = {
        frames: hit.frame - envelopeFrame(clip, envelopePoint[0]),
        y: rowY - pointY,
      };
    } else {
      start = clip[`fade_${zone.side}`];
      grab = 0;
    }
    tweakSession = {
      kind: zone.kind,
      side: zone.side ?? null,
      point: zone.point ?? null,
      clipId: clip.id,
      trackId: hit.row.id,
      rowHeight: hit.row.height,
      origin,
      pointerId: event.pointerId,
      dragging: false,
      seekFrame: hit.frame,
      start,
      grab,
      value: null,
    };
    overlayCanvas.setPointerCapture?.(event.pointerId);
    window.addEventListener("keydown", tweakKey, true);
  }

  function sendTweak(session, value) {
    if (session.kind === "gain") actions.clipGain({ clipId: session.clipId, gain: value });
    else if (session.kind === "envelope") {
      const { coalesce } = envelopeDragChange(session.clipId, value);
      actions.clipEnvelope({ clipId: session.clipId, points: value, coalesce });
    } else actions.clipFade({ clipId: session.clipId, side: session.side, frames: value });
  }

  function updateTweak(event) {
    const session = tweakSession;
    const point = locate(event);
    if (!session.dragging) {
      if (!isDrag(session.origin, point)) return;
      session.dragging = true;
      overlayCanvas.style.cursor = session.kind === "gain" ? "ns-resize" : "ew-resize";
    }
    const state = getState();
    const track = state.project.tracks.find((item) => item.id === session.trackId);
    const clip = track?.clips.find((item) => item.id === session.clipId);
    if (!clip) return;
    const row = layoutFor(state).rows.find((item) => item.id === session.trackId);
    const rowY = point.y - RULER_HEIGHT + state.scrollY - (row?.top ?? 0);
    const value =
      session.kind === "gain"
        ? gainFromY(session.rowHeight, rowY, session.grab)
        : session.kind === "envelope"
          ? envelopeMove(clip, session.point, {
              timelineFrame: xToFrame(point.x, state.scroll, state.zoom),
              rowHeight: session.rowHeight,
              rowY,
              grabFrames: session.grab.frames,
              grabY: session.grab.y,
            })
          : fadeFromX(clip, session.side, {
              startFade: session.start,
              startX: session.origin.x,
              x: point.x,
              zoom: state.zoom,
            });
    if (value === session.value) return;
    session.value = value;
    sendTweak(session, value);
    requestOverlay();
  }

  function endTweak(cancel) {
    const session = tweakSession;
    tweakSession = null;
    overlayCanvas.style.cursor = "";
    window.removeEventListener("keydown", tweakKey, true);
    overlayCanvas.releasePointerCapture?.(session.pointerId);
    if (cancel && session.dragging && session.value !== null) sendTweak(session, session.start);
    if (!cancel && !session.dragging) actions.seek?.(session.seekFrame);
    requestOverlay();
  }

  function tweakKey(event) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    endTweak(true);
  }

  // Dragging clips by the label strip (WP6): as the edge drag. A press is a click until
  // DRAG_PX of travel; then the ghosts follow the pointer in time and across tracks, Esc
  // cancels, release sends one move_clips_to_track.
  function rowYOf(event, hit) {
    if (!hit.row) return -1;
    return locate(event).y - RULER_HEIGHT + getState().scrollY - hit.row.top;
  }

  // `portion` (clip-drag.js portionDragEdit): the press was on an implicit portion. Past DRAG_PX
  // it is opened as a clip, and the drag goes on with that clip alone; a click changes nothing.
  function startClip(hit, event, before, portion = null) {
    clipSession = clipSessionFor(hit.clip.id, before, {
      fromIndex: hit.row.index,
      origin: locate(event),
      pointerId: event.pointerId,
      alone: event.altKey,
      seekFrame: hit.frame,
    });
    clipSession.portion = portion;
    overlayCanvas.setPointerCapture?.(event.pointerId);
    window.addEventListener("keydown", clipKey, true);
    window.addEventListener("keyup", clipKey, true);
  }

  function clipSessionFor(
    pressedId,
    selection,
    { fromIndex, origin, pointerId, alone, seekFrame },
  ) {
    const project = getState().project;
    const ids = clipDragIds(pressedId, selection, project);
    return {
      pressedId,
      ids,
      fromIndex,
      origin,
      pointerId,
      dragging: false,
      alone,
      seekFrame,
      move: { delta: 0, direction: 0 },
      // Snapping and fine movement (move-snap.js): where the pointer's travel stands, the clips'
      // spans before the move, and the frames worth snapping to (fixed for the whole drag).
      pos: { delta: 0, lastX: origin.x },
      spans: movedSpans(project, ids),
      targets: moveTargets(project, ids, getState()),
      snapAt: null,
      // Cmd (Ctrl off the Mac) held during the drag adds the volume automation (automation-snap.js):
      // the level changes and the closed stretches' edges. Read live; the frames are fixed here.
      auto: automationTargets(project, ids),
      withAuto: null,
      autoOn: false,
    };
  }

  // The portion's drag waits for the server's answer (one round trip, under 50 ms by the
  // budget). The pointer's latest event is kept meanwhile; with the answer the session is
  // rebuilt round the new clip and caught up to it, or, if the button went up first, the
  // move is sent from where it let go. Esc or a cancel in the wait leaves the clip unmoved.
  function openPortion(session, event) {
    session.opening = true;
    session.latest = event;
    actions.openPortion?.(session.portion, (id) => {
      const live = clipSession === session;
      if (!live && session.ended !== "commit") return;
      const held = getState().project?.tracks?.some((track) =>
        track.clips.some((clip) => clip.id === id),
      );
      if (!id || !held) {
        if (live) endClip(false);
        return;
      }
      const next = clipSessionFor(id, new Set([id]), session);
      next.dragging = true;
      next.coalesce = session.portion.coalesce;
      const other = clipSession; // a newer press, when the button went up before the answer
      clipSession = next;
      updateClip(session.latest);
      if (live) {
        overlayCanvas.style.cursor = "grabbing";
        return;
      }
      clipSession = other;
      sendMove(next);
    });
  }

  function updateClip(event) {
    const session = clipSession;
    const point = locate(event);
    if (session.opening) {
      session.latest = event;
      return;
    }
    if (!session.dragging) {
      if (!isDrag(session.origin, point)) return;
      if (session.portion) {
        openPortion(session, event);
        return;
      }
      session.dragging = true;
      overlayCanvas.style.cursor = "grabbing";
    }
    const state = getState();
    session.alone = event.altKey; // Alt held when it lets go: this clip moves alone (R51)
    const row = targetTrackRow(layoutFor(state), point.y - RULER_HEIGHT + state.scrollY);
    // Shift: fine adjust (a tenth of the travel). Alt: no snapping. Otherwise the edges snap
    // to other clips' edges, the playhead and the marks within 8 px.
    session.pos = advanceDelta(session.pos, point.x, { fine: event.shiftKey, zoom: state.zoom });
    let deltaFrames = session.pos.delta;
    session.snapAt = null;
    session.autoOn = modClick(event, detectPlatform());
    if (session.autoOn && session.withAuto === null) {
      session.withAuto = [...new Set([...session.targets, ...session.auto])].sort((a, b) => a - b);
    }
    if (!event.altKey) {
      const snapped = snapMove({
        moved: session.spans,
        delta: deltaFrames,
        targets: session.autoOn ? session.withAuto : session.targets,
        zoom: state.zoom,
      });
      deltaFrames = snapped.delta;
      session.snapAt = snapped.at;
    }
    session.move = resolveMove(state.project, session.ids, {
      deltaFrames,
      fromIndex: session.fromIndex,
      toIndex: row?.index ?? session.fromIndex,
    });
    requestOverlay();
  }

  function endClip(commit) {
    const session = clipSession;
    clipSession = null;
    overlayCanvas.style.cursor = "";
    window.removeEventListener("keydown", clipKey, true);
    window.removeEventListener("keyup", clipKey, true);
    overlayCanvas.releasePointerCapture?.(session.pointerId);
    requestOverlay();
    // Still waiting for the portion to open: its answer finishes the drag (openPortion).
    if (session.opening) {
      session.ended = commit ? "commit" : "cancel";
      return;
    }
    if (commit && !session.dragging) actions.clickSeek?.(session.seekFrame);
    if (commit && session.dragging) sendMove(session);
  }

  function sendMove(session) {
    actions.clipDrag({
      ids: session.ids,
      move: session.move,
      alone: session.alone,
      pressedId: session.pressedId,
      coalesce: session.coalesce ?? null,
    });
  }

  function clipKey(event) {
    // The modifier of the automation snap going down or up shows or hides its marks at once.
    if (event.key === (detectPlatform() === "mac" ? "Meta" : "Control")) {
      if (clipSession?.dragging) {
        clipSession.autoOn = event.type === "keydown";
        requestOverlay();
      }
      return;
    }
    if (event.type !== "keydown" || event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    endClip(false);
  }

  // Press, move, lift in a lane selects a time range (WP6). Until the pointer has moved
  // DRAG_PX it is the plain click pointerDown already handled; Esc cancels.
  function beginRangeDrag(event, hit) {
    const from = locate(event);
    const contentY = (y) => y - RULER_HEIGHT + getState().scrollY;
    let dragging = false;
    let alt = event.altKey;
    let last = null; // the latest { frame, tracks } while dragging
    const current = (e) => {
      const at = locate(e);
      const state = getState();
      return {
        at,
        frame: xToFrame(at.x, state.scroll, state.zoom),
        tracks: trackRowsTouched(layoutFor(state), contentY(from.y), contentY(at.y)),
      };
    };
    // Alt holds the clips the range touches; the exact range otherwise (decided afresh each time).
    const outcome = (now) => {
      const project = getState().project;
      const range = dragRange(hit.frame, now.frame, projectEnd(project));
      const touched = alt && range ? touchedResult(project, range, now.tracks) : null;
      return { range, touched };
    };
    const show = () => {
      if (!last) return;
      rangeBand = {
        fromFrame: hit.frame,
        toFrame: last.frame,
        tracks: last.tracks,
        alt,
        touched: outcome(last).touched?.selection ?? null,
      };
      requestOverlay();
    };
    const end = () => {
      overlayCanvas.removeEventListener("pointermove", move);
      overlayCanvas.removeEventListener("pointerup", up);
      overlayCanvas.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("keyup", altKey, true);
      rangeBand = null;
      requestOverlay();
    };
    const move = (e) => {
      const now = current(e);
      alt = e.altKey;
      if (!dragging && !isDrag(from, now.at)) return;
      dragging = true;
      last = now;
      show();
    };
    const up = (e) => {
      const now = current(e);
      // Not `alt = e.altKey`: the release event does not always carry the modifier (the owner's
      // alt-drag preview showed the clips and the selection vanished on release), so the
      // state tracked from the moves and the Alt key events decides.
      end();
      if (!dragging) {
        if (
          alt &&
          !e.shiftKey &&
          !modClick(e, detectPlatform()) &&
          hit.clip &&
          hit.row?.kind === "track"
        ) {
          actions.toggleClipMute?.(hit.clip.id, hit);
        }
        return;
      }
      const { range, touched } = outcome(now);
      if (!range) return;
      const base = { tracks: now.tracks, trackId: hit.row.id };
      actions.rangeDragged(touched ? { ...base, ...touched } : { ...base, ...range });
    };
    // Alt pressed or released mid-drag changes the preview without a mouse move.
    const altKey = (e) => {
      if (e.key !== "Alt" || e.altKey === alt) return;
      alt = e.altKey;
      show();
    };
    const cancel = () => end();
    const key = (e) => {
      if (e.key === "Alt") return altKey(e);
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      end();
    };
    overlayCanvas.addEventListener("pointermove", move);
    overlayCanvas.addEventListener("pointerup", up);
    overlayCanvas.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key, true);
    window.addEventListener("keyup", altKey, true);
    try {
      overlayCanvas.setPointerCapture(event.pointerId);
    } catch {
      // No capture (synthetic events): the drag still works while the pointer stays over the canvas.
    }
  }
  overlayCanvas.addEventListener(
    "wheel",
    (event) => {
      const state = getState();
      event.preventDefault();
      const layout = layoutFor(state);
      const lanesFit = layout.height <= size.height - RULER_HEIGHT;
      actions.wheel(
        wheelIntent(event, { lanesFit, mode: state.wheelMode }),
        locate(event).x,
        event,
      );
    },
    { passive: false },
  );

  measure();
  return {
    redraw: requestOverlay,
    redrawWaveforms: requestWaveforms,
    refreshTheme,
    size: () => size,
    pointerFrame: () => pointerFrame,
    // Files dragged over: what a drop at this pointer would do (null: the pointer is
    // not over the timeline), and the preview drawn for it (null clears it).
    dropTarget(event, count) {
      const state = getState();
      const rect = overlayCanvas.getBoundingClientRect();
      const { x, y } = locate(event);
      if (!state.project || x < 0 || y < 0 || x > rect.width || y > rect.height) return null;
      return resolveDropTarget(
        { x, y, alt: event.altKey },
        { layout: layoutFor(state), project: state.project, view: state, count },
      );
    },
    setDropPreview(preview) {
      dropPreview = preview;
      requestOverlay();
    },
    // A clipboard entry dragged over: where a drop at this pointer would paste it (null: not on
    // a track lane), and its outlines (null clears them). clipboard-drag.js.
    clipboardDropTarget(event, entry) {
      const state = getState();
      const rect = overlayCanvas.getBoundingClientRect();
      const { x, y } = locate(event);
      if (!state.project || x < 0 || y < 0 || x > rect.width || y > rect.height) return null;
      const { playhead, inPoint, outPoint } = state;
      return clipboardDropTarget(
        { x, y, alt: event.altKey, mod: edgeMod(event) },
        {
          layout: layoutFor(state),
          project: state.project,
          view: state,
          entry,
          marks: { playhead, inPoint, outPoint },
        },
      );
    },
    setClipboardDropPreview(preview) {
      if (preview === clipDrop) return;
      clipDrop = preview;
      requestOverlay();
    },
    layerMode: layer.mode,
    destroy() {
      observer.disconnect();
      dark.removeEventListener("change", refreshTheme);
    },
  };
}
