// The timeline canvases. Two layers, one above the other:
//   - the waveform layer (clip bodies and waveforms) is drawn in a Web Worker
//     from peak tiles (waveform-layer.js, paint.js);
//   - this overlay draws everything that is cheap and changes often: the
//     ruler, clip outlines and names, gain lines, selection, in/out, playhead.
// The overlay redraws on requestAnimationFrame when state changed; the
// waveform layer only when something it shows changed.
import { candidateBands, flagFits, flagText } from "./candidates-model.js";
import { edgeGhost, ghostGeometry, isDrag, resolveEdge } from "./edge-drag.js";
import { frameToX, xToFrame } from "./format.js";
import { gateLabelFits, gatePixelRuns } from "./gate.js";
import { busHues, fileMark, needsFileMark, seamKind } from "./grammar.js";
import { formatNumber, t } from "./i18n.js";
import { dropGhosts, dropLabel, resolveDropTarget } from "./import-drop.js";
import { clipLabel, labelFacts, siblingsOf } from "./labels.js";
import {
  clipEnd,
  dbToY,
  envelopeFrame,
  hitTest,
  layoutFor,
  projectEnd,
  RULER_HEIGHT,
  visibleRows,
} from "./lanes.js";
import { activeLoop } from "./loop-range.js";
import { flagLayout, NOTCH_PX as MARKER_NOTCH_PX } from "./markers-model.js";
import { markDrawing } from "./marks.js";
import { makeWaveformJob, trackHues } from "./paint.js";
import { aboutSeconds, placeholderLabel } from "./placeholders-model.js";
import { canStartRangeDrag, dragRange, isDrag, trackRowsTouched } from "./range-drag.js";
import { rulerTicks } from "./ruler.js";
import { readTheme } from "./theme.js";
import { createWaveformLayer } from "./waveform-layer.js";
import { wheelIntent } from "./wheel.js";

// Drawing rules: docs/design/GUI-DESIGN.md, "Waveforms and the timeline".
const NAME_FONT_PX = 11;
const LABEL_H = 14;
const LABEL_BACKING_ALPHA = 0.85;
const HATCH_STEP = 6;
const POINT_RADIUS = 3;
const XFADE_ALPHA = 0.3;
const GAIN_ALPHA = 0.75;
const PLAYHEAD_CAP = 5.5;
const SEAM_ALPHA = 0.7;
const NOTCH_PX = 4;
const MARK_FONT_PX = 10;
const BRACKET_PX = 10;
const GATE_TICK_PX = 7;
const GATE_LABEL_MIN_LANE = 36;
const CANDIDATE_STRIPE_ALPHA = 0.35;
const CANDIDATE_EDGE_PX = 1;
const CANDIDATE_EDGE_CURRENT_PX = 2;
const FLAG_EDGE_PX = 3;
const REGION_BAR_PX = 5;
const MARKER_FLAG_H = 8;
const FLAG_EDGE_CURRENT_PX = 4;

export function createTimeline({ stack, waveCanvas, overlayCanvas, getState, actions }) {
  const overlay = overlayCanvas.getContext("2d");
  const layer = createWaveformLayer(waveCanvas);
  let theme = readTheme();
  let size = { width: 0, height: 0, ratio: 1 };
  let pointerFrame = null;
  let edgeSession = null; // an edge being dragged: see the pointer section
  let dropPreview = null; // files being dragged over: { kind, startFrame, mode, count } or null
  let rangeBand = null; // a range being dragged: { fromFrame, toFrame, tracks } or null
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
    size = {
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      ratio: devicePixelRatio || 1,
    };
    overlayCanvas.width = Math.round(size.width * size.ratio);
    overlayCanvas.height = Math.round(size.height * size.ratio);
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
        laneCurrent: theme.laneCurrent,
        busBands: theme.busBands,
        clipping: theme.clipping,
        mutedOpacity: theme.mutedOpacity,
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
    drawRange(state, height);
    for (const row of visibleRows(layout, state.scrollY, height - RULER_HEIGHT)) {
      const top = RULER_HEIGHT + row.top - state.scrollY;
      if (row.kind === "gap") continue; // plain lane between groups: nothing drawn
      overlay.strokeStyle = theme.rule;
      overlay.lineWidth = 1;
      overlay.beginPath();
      overlay.moveTo(0, top + row.height - 0.5);
      overlay.lineTo(width, top + row.height - 0.5);
      overlay.stroke();
      if (row.kind === "track") drawTrack(state, state.project.tracks[row.index], row, top, hues);
      else drawBusRow(row, top, groups);
    }
    drawRuler(state, rate);
    drawInOut(state, height);
    drawRangeBand(state, layout);
    if (dropPreview) drawDropPreview(state, layout);
    if (edgeSession?.dragging) drawEdgeGhost(state, layout);
    drawPlayhead(state, height);
  }

  // A clip edge being dragged (WP6): a thin line at the new edge, the clip's new outline and,
  // for roll, the neighbour's. Ripple is drawn dashed with the accent line, roll solid.
  function drawEdgeGhost(state, layout) {
    const row = layout.rows.find((item) => item.id === edgeSession.trackId);
    const track = state.project.tracks.find((item) => item.id === edgeSession.trackId);
    const clip = track?.clips.find((item) => item.id === edgeSession.clipId);
    if (!(row && clip)) return;
    const ghost = edgeGhost(state.project, track, clip, edgeSession.edge, edgeSession.frame, {
      ripple: edgeSession.ripple,
    });
    const geometry = ghostGeometry(ghost, { view: state, row });
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, RULER_HEIGHT, size.width, size.height - RULER_HEIGHT);
    overlay.clip();
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
    const hint = t(ghost.ripple ? "ui.edge.hint_ripple" : "ui.edge.hint_roll");
    overlay.fillText(hint, Math.max(4, geometry.line.x + 6), geometry.line.y + 3);
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

  function drawRange(state, height) {
    const { range } = markDrawing(state);
    if (range === null) return;
    const x1 = frameToX(range.start, state.scroll, state.zoom);
    const x2 = frameToX(range.end, state.scroll, state.zoom);
    overlay.fillStyle = theme.range;
    overlay.fillRect(x1, RULER_HEIGHT, x2 - x1, height - RULER_HEIGHT);
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
  }

  // In and out: 1 px accent edges with a flag in the ruler, pointing inwards.
  // A lone mark is drawn too, so pressing O or I shows something at once.
  function drawInOut(state, height) {
    const { inFrame, outFrame } = markDrawing(state);
    overlay.fillStyle = theme.accent;
    overlay.beginPath();
    if (inFrame !== null) {
      const x1 = frameToX(inFrame, state.scroll, state.zoom);
      overlay.fillRect(Math.round(x1), 0, 1, height);
      overlay.moveTo(x1, 0);
      overlay.lineTo(x1 + 8, 0);
      overlay.lineTo(x1, 8);
    }
    if (outFrame !== null) {
      const x2 = frameToX(outFrame, state.scroll, state.zoom);
      overlay.fillRect(Math.round(x2) - 1, 0, 1, height);
      overlay.moveTo(x2, 0);
      overlay.lineTo(x2 - 8, 0);
      overlay.lineTo(x2, 8);
    }
    overlay.fill();
  }

  function drawTrack(state, track, row, top, hues) {
    const { width } = size;
    const colours = theme.palette[(hues.get(track.id) ?? 0) % theme.palette.length];
    const marked = needsFileMark(track);
    const siblings = siblingsOf(state.project, state.selection);
    // Rows under the ruler must not paint over it.
    overlay.save();
    overlay.beginPath();
    overlay.rect(0, RULER_HEIGHT, width, size.height - RULER_HEIGHT);
    overlay.clip();
    for (const clip of track.clips) {
      const left = frameToX(clip.start, state.scroll, state.zoom);
      const right = frameToX(clipEnd(clip), state.scroll, state.zoom);
      if (right < 0 || left > width) continue;
      const y = top + 2;
      const h = row.height - 4;
      const w = Math.max(1, right - left);
      const selected = state.selection.has(clip.id);
      overlay.strokeStyle = colours.ink;
      overlay.lineWidth = 1;
      overlay.strokeRect(left + 0.5, y + 0.5, w - 1, h - 1);
      if (clip.muted) drawHatch(left, y, w, h, theme.hatch);
      if (clip.xfade_in) drawCrossfade(left, y, h, clip.xfade_in / state.zoom, colours.ink);
      if (clip.xfade_out) drawCrossfade(right, y, h, clip.xfade_out / state.zoom, colours.ink);
      if (row.height >= 36) drawName(state, clip, left, y, w, colours, marked);
      // The gain line only where it says something: not 0 dB, an envelope, or selected.
      const gainShown = (clip.gain_db ?? 0) !== 0 || clip.envelope?.length > 0 || selected;
      if (row.height >= 40 && gainShown) drawGain(state, clip, left, right, top, row.height);
      if (siblings.has(clip.id)) drawSiblingMarks(left, y, w, h);
      if (selected) {
        overlay.strokeStyle = theme.selection;
        overlay.lineWidth = 2;
        overlay.strokeRect(left + 1, y + 1, w - 2, h - 2);
      }
    }
    drawPlaceholders(state, track, row, top);
    if (state.collateral?.tracks.includes(track.id)) drawCollateral(state, track, row, top);
    if (state.showGates !== false) drawGate(state, track, top, row.height);
    drawCandidates(track.id, top, row.height);
    drawSeams(state, track, top, row.height);
    drawAutomation(state, track, top, row.height);
    overlay.restore();
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

  // The gate (WP44): a dim veil in the lane colour over each closed stretch,
  // a small tick at each edge, and 'mic closed' when the band is wide enough.
  // The waveform under it is drawn flat by the waveform layer. Runs are merged
  // pixels (gate.js), so thousands of ranges cost a few rectangles.
  const gateRuns = [];
  function drawGate(state, track, top, rowHeight) {
    if (!track.gate?.length) return;
    const runs = gatePixelRuns(track.gate, state.scroll, state.zoom, size.width, gateRuns);
    if (runs.length === 0) return;
    const y = top + 2;
    const h = rowHeight - 4;
    const tick = Math.min(GATE_TICK_PX, Math.floor(h / 3));
    overlay.fillStyle = theme.gate;
    overlay.globalAlpha = theme.gateOpacity;
    for (let i = 0; i < runs.length; i += 2) overlay.fillRect(runs[i], y, runs[i + 1] - runs[i], h);
    overlay.globalAlpha = 1;
    overlay.fillStyle = theme.muted;
    for (let i = 0; i < runs.length; i += 2) {
      if (runs[i] > 0) overlay.fillRect(runs[i], y + h - tick, 1, tick);
      if (runs[i + 1] < size.width) overlay.fillRect(runs[i + 1] - 1, y + h - tick, 1, tick);
    }
    if (rowHeight < GATE_LABEL_MIN_LANE) return;
    const text = t("ui.gate.mic_closed");
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    const textWidth = overlay.measureText(text).width;
    for (let i = 0; i < runs.length; i += 2) {
      const band = runs[i + 1] - runs[i];
      if (!gateLabelFits(band, textWidth)) continue;
      overlay.fillText(text, runs[i] + (band - textWidth) / 2, y + h / 2 - NAME_FONT_PX / 2);
    }
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
    overlay.save();
    overlay.beginPath();
    overlay.rect(x, y, w, h);
    overlay.clip();
    overlay.strokeStyle = colour;
    overlay.lineWidth = 1;
    overlay.beginPath();
    for (let offset = -h; offset < w; offset += HATCH_STEP) {
      overlay.moveTo(x + offset, y + h);
      overlay.lineTo(x + offset + h, y);
    }
    overlay.stroke();
    overlay.restore();
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

  // A bus row (expanded): its band, twice as strong as behind its members, so
  // the group header reads as the top of the group. Collapsed buses (a summed
  // waveform) are designed in GUI-DESIGN.md and not built yet.
  function drawBusRow(row, top, groups) {
    const band = theme.busBands[(groups.get(row.id) ?? 1) - 1];
    if (!band) return;
    overlay.fillStyle = band;
    overlay.fillRect(0, top, size.width, row.height - 1);
    overlay.fillRect(0, top, size.width, row.height - 1);
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

  // The clip's name on a backing of its body colour, so bars never cross the
  // text; before it, the file mark when the track holds more than one file.
  // The label says what the clip is, by the width there is (labels.js):
  // nothing, the person, "Olli 3", "Olli 3 · 1:20–3:20", then the first words.
  function drawName(state, clip, left, y, w, colours, marked) {
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
    overlay.strokeStyle = theme.gain;
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
      overlay.fillStyle = theme.gain;
      for (const [x, y] of points) {
        overlay.beginPath();
        overlay.arc(x, y, POINT_RADIUS, 0, Math.PI * 2);
        overlay.fill();
      }
    }
    overlay.globalAlpha = 1;
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
    const x = Math.round(frameToX(state.playhead, state.scroll, state.zoom)) + 0.5;
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

  // Over a closed stretch the tooltip says what it is and what a double-click does; over a
  // narration placeholder (WP43) it says it is to be recorded and that Enter edits it.
  function hoverGate(event) {
    const hit = hitAt(event);
    let text = "";
    if (hit.placeholder && !hit.clip) text = t("ui.placeholders.hover");
    else if (hit.gate) text = t("ui.gate.hover");
    if (overlayCanvas.title !== text) overlayCanvas.title = text;
  }
  overlayCanvas.addEventListener("pointermove", (event) => {
    const state = getState();
    pointerFrame = Math.max(0, xToFrame(locate(event).x, state.scroll, state.zoom));
    if (edgeSession) {
      if (event.pointerId === edgeSession.pointerId) updateEdge(event);
      return;
    }
    if (!state.project) return;
    hoverGate(event);
    const hit = hitAt(event);
    const cursor = hit.clip && hit.edge && hit.row?.kind === "track" ? "ew-resize" : "";
    if (overlayCanvas.style.cursor !== cursor) overlayCanvas.style.cursor = cursor;
  });
  overlayCanvas.addEventListener("pointerleave", () => {
    pointerFrame = null;
  });
  overlayCanvas.addEventListener("dblclick", (event) => {
    if (!getState().project || event.button !== 0) return;
    if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
    const { gate, placeholder, clip } = hitAt(event);
    if (placeholder && !clip) actions.editPlaceholder(placeholder);
    else if (gate) actions.openGate(gate);
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

  function startEdge(hit, event) {
    edgeSession = {
      clipId: hit.clip.id,
      trackId: hit.row.id,
      edge: hit.edge,
      origin: locate(event),
      pointerId: event.pointerId,
      dragging: false,
      ripple: event.shiftKey,
      raw: null,
      frame: hit.edge === "start" ? hit.clip.start : hit.clip.start + hit.clip.length,
    };
    overlayCanvas.setPointerCapture?.(event.pointerId);
    window.addEventListener("keydown", edgeKey, true);
    window.addEventListener("keyup", edgeKey, true);
  }

  // The edge's frame under the pointer, clamped by the rules of the current mode.
  function clampEdge() {
    const { state, track, clip } = edgeTarget(edgeSession);
    if (!clip || edgeSession.raw === null) return;
    edgeSession.frame = resolveEdge(state.project, track, clip, edgeSession.edge, edgeSession.raw, {
      ripple: edgeSession.ripple,
    }).frame;
  }

  function updateEdge(event) {
    const session = edgeSession;
    const point = locate(event);
    session.ripple = event.shiftKey;
    if (!session.dragging) {
      if (!isDrag(point.x - session.origin.x, point.y - session.origin.y)) return;
      session.dragging = true;
      overlayCanvas.style.cursor = "ew-resize";
    }
    const state = getState();
    session.raw = xToFrame(point.x, state.scroll, state.zoom);
    clampEdge();
    requestOverlay();
  }

  function endEdge(commit) {
    const session = edgeSession;
    edgeSession = null;
    overlayCanvas.style.cursor = "";
    window.removeEventListener("keydown", edgeKey, true);
    window.removeEventListener("keyup", edgeKey, true);
    overlayCanvas.releasePointerCapture?.(session.pointerId);
    requestOverlay();
    if (commit && session.dragging) {
      actions.edgeDrag({
        clipId: session.clipId,
        edge: session.edge,
        frame: session.frame,
        ripple: session.ripple,
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
    }
  }

  overlayCanvas.addEventListener("pointerup", (event) => {
    if (!edgeSession || event.pointerId !== edgeSession.pointerId) return;
    if (edgeSession.dragging) updateEdge(event);
    endEdge(true);
  });
  overlayCanvas.addEventListener("pointercancel", () => {
    if (edgeSession) endEdge(false);
  });
  overlayCanvas.addEventListener("pointerdown", (event) => {
    if (!getState().project || event.button !== 0) return;
    overlayCanvas.focus();
    const hit = hitAt(event);
    actions.pointerDown(hit, event);
    if (!event.shiftKey && canStartRangeDrag(hit)) beginRangeDrag(event, hit);
    if (hit.clip && hit.edge && hit.row?.kind === "track") startEdge(hit, event);
  });

  // Press, move, lift in a lane selects a time range (WP6). Until the pointer has moved
  // DRAG_PX it is the plain click pointerDown already handled; Esc cancels.
  function beginRangeDrag(event, hit) {
    const from = locate(event);
    const contentY = (y) => y - RULER_HEIGHT + getState().scrollY;
    let dragging = false;
    const current = (e) => {
      const at = locate(e);
      const state = getState();
      return {
        at,
        frame: xToFrame(at.x, state.scroll, state.zoom),
        tracks: trackRowsTouched(layoutFor(state), contentY(from.y), contentY(at.y)),
      };
    };
    const end = () => {
      overlayCanvas.removeEventListener("pointermove", move);
      overlayCanvas.removeEventListener("pointerup", up);
      overlayCanvas.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
      rangeBand = null;
      requestOverlay();
    };
    const move = (e) => {
      const now = current(e);
      if (!dragging && !isDrag(from, now.at)) return;
      dragging = true;
      rangeBand = { fromFrame: hit.frame, toFrame: now.frame, tracks: now.tracks };
      requestOverlay();
    };
    const up = (e) => {
      const now = current(e);
      const state = getState();
      end();
      if (!dragging) return;
      const range = dragRange(hit.frame, now.frame, projectEnd(state.project));
      if (range) actions.rangeDragged({ ...range, tracks: now.tracks, trackId: hit.row.id });
    };
    const cancel = () => end();
    const key = (e) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      end();
    };
    overlayCanvas.addEventListener("pointermove", move);
    overlayCanvas.addEventListener("pointerup", up);
    overlayCanvas.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key, true);
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
      actions.wheel(wheelIntent(event, { lanesFit }), locate(event).x, event);
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
    layerMode: layer.mode,
    destroy() {
      observer.disconnect();
      dark.removeEventListener("change", refreshTheme);
    },
  };
}
