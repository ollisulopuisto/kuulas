// The timeline canvases. Two layers, one above the other:
//   - the waveform layer (clip bodies and waveforms) is drawn in a Web Worker
//     from peak tiles (waveform-layer.js, paint.js);
//   - this overlay draws everything that is cheap and changes often: the
//     ruler, clip outlines and names, gain lines, selection, in/out, playhead.
// The overlay redraws on requestAnimationFrame when state changed; the
// waveform layer only when something it shows changed.
import { frameToX, xToFrame } from "./format.js";
import {
  clipEnd,
  dbToY,
  envelopeFrame,
  hitTest,
  layoutRows,
  RULER_HEIGHT,
  visibleRows,
} from "./lanes.js";
import { makeWaveformJob, paletteIndex } from "./paint.js";
import { rulerTicks } from "./ruler.js";
import { readTheme } from "./theme.js";
import { createWaveformLayer } from "./waveform-layer.js";
import { wheelIntent } from "./wheel.js";

const NAME_FONT_PX = 11;
const HATCH_STEP = 6;
const POINT_RADIUS = 3;
const XFADE_ALPHA = 0.25;

export function createTimeline({ stack, waveCanvas, overlayCanvas, getState, actions }) {
  const overlay = overlayCanvas.getContext("2d");
  const layer = createWaveformLayer(waveCanvas);
  let theme = readTheme();
  let size = { width: 0, height: 0, ratio: 1 };
  let pointerFrame = null;
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
      const job = makeWaveformJob(state, { ...size, id: 0 }, theme.palette);
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
    const layout = layoutRows(state.project, state.laneHeight);
    drawRange(state, height);
    for (const row of visibleRows(layout, state.scrollY, height - RULER_HEIGHT)) {
      const top = RULER_HEIGHT + row.top - state.scrollY;
      overlay.strokeStyle = theme.rule;
      overlay.lineWidth = 1;
      overlay.beginPath();
      overlay.moveTo(0, top + row.height - 0.5);
      overlay.lineTo(width, top + row.height - 0.5);
      overlay.stroke();
      if (row.kind === "track") drawTrack(state, state.project.tracks[row.index], row, top);
    }
    drawRuler(state, rate);
    drawPlayhead(state, height);
  }

  function drawRange(state, height) {
    if (state.inPoint === null || state.outPoint === null) return;
    const x1 = frameToX(state.inPoint, state.scroll, state.zoom);
    const x2 = frameToX(state.outPoint, state.scroll, state.zoom);
    overlay.fillStyle = theme.accent;
    overlay.globalAlpha = 0.14;
    overlay.fillRect(x1, RULER_HEIGHT, x2 - x1, height - RULER_HEIGHT);
    overlay.globalAlpha = 1;
  }

  function drawTrack(state, track, row, top) {
    const { width } = size;
    const colours = theme.palette[paletteIndex(track, row.index) % theme.palette.length];
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
      if (clip.muted) drawHatch(left, y, w, h, colours.ink);
      if (clip.xfade_in) drawCrossfade(left, y, h, clip.xfade_in / state.zoom, colours.ink);
      if (clip.xfade_out) drawCrossfade(right, y, h, clip.xfade_out / state.zoom, colours.ink);
      if (row.height >= 36) drawName(state, clip, left, y, w, colours.ink);
      if (row.height >= 40) drawGain(state, clip, left, right, top, row.height);
      if (selected) {
        overlay.strokeStyle = theme.ink;
        overlay.lineWidth = 2;
        overlay.strokeRect(left + 1, y + 1, w - 2, h - 2);
      }
    }
    drawAutomation(state, track, top, row.height);
    overlay.restore();
  }

  function drawHatch(x, y, w, h, colour) {
    overlay.save();
    overlay.beginPath();
    overlay.rect(x, y, w, h);
    overlay.clip();
    overlay.strokeStyle = colour;
    overlay.globalAlpha = 0.4;
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

  function drawName(state, clip, left, y, w, colour) {
    const media = state.project.media.find((item) => item.id === clip.media);
    if (!media || w < 24) return;
    overlay.font = `600 ${NAME_FONT_PX}px ${theme.font}`;
    overlay.textBaseline = "top";
    overlay.fillStyle = colour;
    overlay.save();
    overlay.beginPath();
    overlay.rect(left, y, w, NAME_FONT_PX + 6);
    overlay.clip();
    overlay.fillText(media.name, Math.max(left, 0) + 4, y + 3);
    overlay.restore();
  }

  // Clip gain: a dashed line at gain_db; envelope points as dots joined by lines.
  function drawGain(state, clip, left, right, top, rowHeight) {
    const baseline = top + dbToY(clip.gain_db ?? 0, rowHeight);
    overlay.strokeStyle = theme.ink;
    overlay.globalAlpha = 0.7;
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
      overlay.fillStyle = theme.ink;
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
    overlay.strokeStyle = theme.ink;
    overlay.globalAlpha = 0.5;
    overlay.lineWidth = 1;
    overlay.beginPath();
    track.automation.forEach(([frame, db], i) => {
      const x = frameToX(frame, state.scroll, state.zoom);
      const y = bottom - band * (1 - Math.max(-24, Math.min(0, db)) / -24);
      if (i === 0) overlay.moveTo(x, y);
      else overlay.lineTo(x, y);
    });
    overlay.stroke();
    overlay.globalAlpha = 1;
  }

  function drawRuler(state, rate) {
    const { width } = size;
    overlay.fillStyle = theme.panel;
    overlay.fillRect(0, 0, width, RULER_HEIGHT);
    overlay.strokeStyle = theme.rule;
    overlay.beginPath();
    overlay.moveTo(0, RULER_HEIGHT - 0.5);
    overlay.lineTo(width, RULER_HEIGHT - 0.5);
    overlay.stroke();
    overlay.font = `10px ${theme.mono}`;
    overlay.textBaseline = "middle";
    overlay.fillStyle = theme.muted;
    overlay.strokeStyle = theme.muted;
    for (const tick of rulerTicks({ scroll: state.scroll, zoom: state.zoom, width, rate })) {
      const major = tick.label !== null;
      overlay.beginPath();
      overlay.moveTo(Math.round(tick.x) + 0.5, RULER_HEIGHT - (major ? 8 : 4));
      overlay.lineTo(Math.round(tick.x) + 0.5, RULER_HEIGHT - 1);
      overlay.stroke();
      if (major) overlay.fillText(tick.label, tick.x + 3, 9);
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
    overlay.beginPath();
    overlay.moveTo(x - 5, 0);
    overlay.lineTo(x + 5, 0);
    overlay.lineTo(x, 7);
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
    const layout = layoutRows(state.project, state.laneHeight);
    return hitTest({ layout, project: state.project, view: { ...state, width: size.width }, x, y });
  }

  overlayCanvas.addEventListener("pointermove", (event) => {
    const state = getState();
    pointerFrame = Math.max(0, xToFrame(locate(event).x, state.scroll, state.zoom));
  });
  overlayCanvas.addEventListener("pointerleave", () => {
    pointerFrame = null;
  });
  overlayCanvas.addEventListener("pointerdown", (event) => {
    if (!getState().project || event.button !== 0) return;
    overlayCanvas.focus();
    actions.pointerDown(hitAt(event), event);
  });
  overlayCanvas.addEventListener(
    "wheel",
    (event) => {
      const state = getState();
      event.preventDefault();
      const layout = layoutRows(state.project, state.laneHeight);
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
    layerMode: layer.mode,
    destroy() {
      observer.disconnect();
      dark.removeEventListener("change", refreshTheme);
    },
  };
}
