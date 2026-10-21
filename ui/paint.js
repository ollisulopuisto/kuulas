// What the waveform worker draws: clip bodies and waveforms from peak tiles.
// It takes a plain-data job and a tile lookup, so it runs unchanged in the
// worker (OffscreenCanvas), on the main thread when workers are unavailable,
// and in tests with a recording context.
import { CLIP_LIMIT_DB, columnOvers } from "./clip-overs.js";
import { frameToX } from "./format.js";
import { columnGainsDb, waveformScale } from "./gain-scale.js";
import { gatePixelRuns } from "./gate.js";
import { busHues, SPEAKER_HUE_COUNT, zebraSteps } from "./grammar.js";
import { layoutFor, RULER_HEIGHT, visibleRows } from "./lanes.js";
import { columnRuns, envelopeOutline, silentColumns } from "./silence-visuals.js";
import { columnsFromTiles, pickLevel, waveformColumns } from "./waveform.js";

/** Below this a gain is silence: JSON cannot carry -Infinity, so the job clamps to it. */
const SILENCE_DB = -200;
const CAP_PX = 3;
/** Bars are opaque: --track-N-wave on --track-N-body is checked at >= 3:1 (tokens.test.js). */
const WAVE_ALPHA = 1;
/** Pixels between the lines of a diagonal hatch (cut candidates, collateral, edge drags). */
export const HATCH_STEP = 6;
/** Clip bodies stand 2 px inside their lane so neighbours do not touch. */
const BODY_INSET = 2;
/** Speaker hues in tokens.css (--track-0 .. --track-5); then music's own. */
export const SPEAKER_HUES = SPEAKER_HUE_COUNT;
export const MUSIC_HUE = SPEAKER_HUES;

/**
 * Which palette entry (theme.js `palette`) each track uses, by track id.
 * A hue belongs to a speaker, not a track: tracks with the same `speaker`
 * share it (a person's split or backup tracks read as one voice). Music takes
 * its own low-chroma role colour and does not use up a speaker hue.
 */
export function trackHues(project) {
  const hues = new Map();
  const speakers = new Map();
  for (const track of project?.tracks ?? []) {
    if (track.kind === "music") {
      hues.set(track.id, MUSIC_HUE);
      continue;
    }
    const key = track.speaker || `track:${track.id}`;
    if (!speakers.has(key)) speakers.set(key, speakers.size % SPEAKER_HUES);
    hues.set(track.id, speakers.get(key));
  }
  return hues;
}

/**
 * The vertical scale a track's waveform uses. "auto" (the default) follows the
 * role, an owner decision of 2026-10-18: speech dB-shaped (its detail is in the
 * quiet parts), music linear. "linear" or "db" force one scale for all roles.
 * Derived from the track on every job, so a role change shows on the next draw.
 */
export function scaleFor(kind, setting = "auto") {
  if (setting === "linear" || setting === "db") return setting;
  return kind === "music" ? "linear" : "db";
}

/** Clip + track gain in dB for a job: finite (silence clamps to SILENCE_DB), 0 when unset. */
export function baseGainDb(clip, track) {
  const db = (clip.gain_db ?? 0) + (track.gain_db ?? 0);
  if (Number.isNaN(db)) return 0;
  return Math.max(SILENCE_DB, Math.min(-SILENCE_DB, db));
}

/**
 * A structured-clone-safe description of what is on screen: only rows in view
 * and, in each, only the clips that overlap the visible time.
 */
export function makeWaveformJob(state, { width, height, ratio, id }, palette, colours = {}) {
  const groups = busHues(state.project);
  const { project, scroll, zoom, scrollY, laneHeight } = state;
  const layout = layoutFor(state);
  const hues = trackHues(project);
  const rows = [];
  const first = scroll;
  const last = scroll + width * zoom;
  const shown = visibleRows(layout, scrollY, height - RULER_HEIGHT);
  const missingMedia = state.missingMedia;
  for (const row of shown) {
    if (row.kind !== "track") continue;
    const track = project.tracks[row.index];
    const clips = [];
    const steps = zebraSteps(track.clips);
    for (const clip of track.clips) {
      if (clip.start + clip.length < first || clip.start > last) continue;
      const entry = {
        id: clip.id,
        media: clip.media,
        start: clip.start,
        offset: clip.offset,
        length: clip.length,
        muted: Boolean(clip.muted),
        step: steps.get(clip.id) ?? 0,
      };
      // Only when set, so a job is unchanged for the common clip.
      if (clip.ungated) entry.ungated = true;
      if (missingMedia?.has(clip.media)) entry.missing = true;
      // WP57: the size follows clip + track gain and the clip's envelope. Pan and mute do
      // not; bus gain is not included yet. Absent at 0 dB, so a job is unchanged there.
      const gainDb = baseGainDb(clip, track);
      if (gainDb !== 0) entry.gainDb = gainDb;
      if (clip.envelope?.length) entry.envelope = clip.envelope;
      clips.push(entry);
    }
    rows.push({
      top: row.top,
      height: row.height,
      // Member lanes carry no band at rest (density rework, 2026-10-18): the
      // group gap and the header spine say "group"; a theme may turn it on.
      band:
        row.bus && colours.memberBands ? (colours.busBands?.[groups.get(row.bus) - 1] ?? "") : "",
      // WP44: the gate as merged pixel runs [x0, x1, ...]; the painter draws the waveform as
      // an outline (silent) under them. Empty when the user hides gates.
      gate: state.showGates === false ? [] : gatePixelRuns(track.gate, scroll, zoom, width),
      paletteIndex: hues.get(track.id) ?? 0,
      scale: scaleFor(track.kind, state.waveformScale),
      clips,
    });
    const made = rows.at(-1);
    // The Auto-Silence preview (silence-panel.js): what the options would close, outlined in
    // the preview colour. Shown even when gates are hidden: the panel is open to see this.
    const preview = state.silencePreview?.get?.(track.id);
    if (preview?.length) made.preview = gatePixelRuns(preview, scroll, zoom, width);
    // Outside the current operation, with a desaturating inactive style: the grey palette.
    if (colours.inactive?.has(track.id)) made.inactive = true;
  }
  return {
    id,
    width,
    height,
    ratio,
    scroll,
    zoom,
    scrollY,
    rulerHeight: RULER_HEIGHT,
    mode: state.waveformMode,
    scale: state.waveformScale,
    gain: state.waveformGain ?? 1,
    palette,
    clipping: colours.clipping ?? "",
    silentBody: colours.silentBody ?? "",
    previewColour: colours.preview ?? "",
    missingFill: colours.missingFill ?? "",
    paletteInactive: colours.inactive?.size ? (colours.paletteInactive ?? []) : [],
    rows,
    laneHeight,
  };
}

/**
 * What the waveform shows for one clip's columns: the display peaks (scaled by
 * the clip's gain, capped as gain_scale.waveform_scale caps it) and each
 * column's total gain in dB, which the clipping judgement uses uncapped. At
 * 0 dB with no envelope it returns `data` itself and no per-column gains.
 */
export function gained(clip, data, startFrame, framesPerPixel) {
  const base = clip.gainDb ?? 0;
  if (base === 0 && !clip.envelope?.length) return { shown: data, dbs: null };
  const count = data.length / 2;
  const dbs = columnGainsDb(base, clip.envelope, startFrame, framesPerPixel, count);
  const shown = new Float32Array(data.length);
  for (let column = 0; column < count; column += 1) {
    const scale = waveformScale(dbs[column]);
    shown[2 * column] = data[2 * column] * scale;
    shown[2 * column + 1] = data[2 * column + 1] * scale;
  }
  return { shown, dbs };
}

/**
 * Paint `job` into `ctx`. `lookup(media, level, tile)` returns a tile's
 * Float32Array or undefined. Returns { missing, overs }: the tiles to fetch
 * before painting again, and for each clip with columns over the clipping
 * limit after gain, how far its loudest column is above full scale in dB
 * (0 when only between the limit and full scale).
 */
export function paintWaveforms(ctx, job, lookup) {
  const missing = new Map();
  const overs = {};
  ctx.setTransform(job.ratio, 0, 0, job.ratio, 0, 0);
  ctx.clearRect(0, 0, job.width, job.height);
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, job.rulerHeight, job.width, job.height - job.rulerHeight);
  ctx.clip();
  const level = pickLevel(job.zoom);
  for (const row of job.rows) {
    const top = job.rulerHeight + row.top - job.scrollY;
    if (top > job.height || top + row.height < job.rulerHeight) continue;
    // The bus band: a faint tint of the bus colour behind the group's lanes.
    if (row.band) {
      ctx.fillStyle = row.band;
      ctx.fillRect(0, top, job.width, row.height - 1);
    }
    // A lane outside the current operation draws in the grey twin of its palette (computed
    // once per theme, silence-visuals.js desaturatePalette), so the cost is nothing.
    const inactive = row.inactive && job.paletteInactive?.length;
    const colours = inactive
      ? job.paletteInactive[row.paletteIndex % job.paletteInactive.length]
      : job.palette[row.paletteIndex % job.palette.length];
    for (const clip of row.clips) {
      const left = frameToX(clip.start, job.scroll, job.zoom);
      const right = frameToX(clip.start + clip.length, job.scroll, job.zoom);
      const from = Math.max(0, Math.floor(left));
      const to = Math.min(job.width, Math.ceil(right));
      if (to <= from) continue;
      const y = top + BODY_INSET;
      const h = row.height - 2 * BODY_INSET;
      // Zebra: a clip from a different file than its neighbour takes the other tone.
      ctx.fillStyle = clip.step === 1 && colours.fillAlt ? colours.fillAlt : colours.fill;
      if (clip.missing && job.missingFill) ctx.fillStyle = job.missingFill;
      ctx.fillRect(left, y, Math.max(1, right - left), h);
      // Missing media (owner, 2026-10-21): no waveform at all, not even an outline (silent is
      // an outline), and no tile is asked for. The overlay draws the error sign over it.
      if (clip.missing) continue;
      paintClipWave(ctx, job, row, clip, {
        from,
        to,
        y,
        h,
        colours,
        level,
        lookup,
        missing,
        overs,
      });
    }
  }
  ctx.restore();
  ctx.globalAlpha = 1;
  return { missing: [...missing.values()], overs };
}

/**
 * One clip's waveform: filled where it sounds, the outline of its min/max envelope where it is
 * silent (muted, or under the gate unless the clip keeps the mic open), with the body toned
 * down there (job.silentBody); the Auto-Silence preview's would-close columns outlined in the
 * preview colour. Silent columns never clip (they do not play).
 */
function paintClipWave(ctx, job, row, clip, view) {
  const { from, to, y, h, colours, level, lookup, missing, overs } = view;
  const count = to - from;
  const startFrame = clip.offset + (job.scroll + from * job.zoom - clip.start);
  const { data, missing: absent } = columnsFromTiles({
    lookup: (tile) => lookup(clip.media, level, tile),
    level,
    startFrame,
    framesPerPixel: job.zoom,
    count,
  });
  for (const tile of absent)
    missing.set(`${clip.media}/${level}/${tile}`, { media: clip.media, level, tile });
  const { shown, dbs } = gained(clip, data, startFrame, job.zoom);
  const bars = waveformColumns(shown, job.mode, row.scale ?? job.scale, h, job.gain);
  const silent = silentColumns(count, from, {
    muted: clip.muted,
    ungated: clip.ungated,
    gate: row.gate,
  });
  const preview = row.preview?.length
    ? silentColumns(count, from, { ungated: clip.ungated, gate: row.preview })
    : null;
  const silentRuns = columnRuns(silent);
  if (preview)
    for (let column = 0; column < count; column += 1) if (silent[column]) preview[column] = 0;
  // The body tone of a silent stretch: a light darkening, well under the inactive veil.
  if (silentRuns.length && job.silentBody) {
    ctx.fillStyle = job.silentBody;
    for (let i = 0; i < silentRuns.length; i += 2)
      ctx.fillRect(from + silentRuns[i], y, silentRuns[i + 1] - silentRuns[i], h);
  }
  // Clipping is judged per drawn column (a peak bucket at this zoom), on the true gain, not
  // the capped display scale, and only where the clip sounds.
  let judged = null;
  if (silentRuns.length < 2 || silentRuns[0] !== 0 || silentRuns[1] !== count) {
    const heard = silentRuns.length ? Float32Array.from(data) : data;
    for (let i = 0; i < silentRuns.length; i += 2)
      heard.fill(0, 2 * silentRuns[i], 2 * silentRuns[i + 1]);
    judged = columnOvers(heard, dbs ?? new Float32Array(count), CLIP_LIMIT_DB);
  }
  const anyOver = judged?.over.includes(1) ?? false;
  if (anyOver) overs[clip.id] = judged.maxOver;
  const flagged = job.clipping && anyOver ? judged.over : null;
  ctx.fillStyle = colours.wave;
  ctx.globalAlpha = WAVE_ALPHA;
  ctx.beginPath();
  for (let column = 0; column < count; column += 1) {
    if (silent[column] || preview?.[column] || flagged?.[column]) continue;
    const barTop = bars[2 * column];
    const barBottom = bars[2 * column + 1];
    if (barBottom > barTop) ctx.rect(from + column, y + barTop, 1, barBottom - barTop);
  }
  ctx.fill();
  strokeOutlines(ctx, bars, silentRuns, { from, y, h, colour: colours.wave });
  if (preview) {
    strokeOutlines(ctx, bars, columnRuns(preview), {
      from,
      y,
      h,
      colour: job.previewColour || colours.wave,
    });
  }
  // Clipping: the whole bar of a column over the limit in the clipping colour, with a cap on
  // top (the shape twin of the colour, grammar.js `clipping`).
  if (flagged) {
    ctx.fillStyle = job.clipping;
    ctx.beginPath();
    for (let column = 0; column < count; column += 1) {
      if (!flagged[column]) continue;
      const barTop = bars[2 * column];
      const barBottom = bars[2 * column + 1];
      if (barBottom > barTop) ctx.rect(from + column, y + barTop, 1, barBottom - barTop);
    }
    ctx.fill();
    for (let column = 0; column < count; column += 1) {
      if (flagged[column]) ctx.fillRect(from + column, y + bars[2 * column], 1, CAP_PX);
    }
  }
  ctx.globalAlpha = 1;
}

/** Stroke the envelope outline (silence-visuals.js envelopeOutline) of each column run. */
function strokeOutlines(ctx, bars, runs, { from, y, h, colour }) {
  if (runs.length === 0) return;
  ctx.strokeStyle = colour;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i < runs.length; i += 2) {
    const points = envelopeOutline(bars, runs[i], runs[i + 1], h);
    ctx.moveTo(from + points[0], y + points[1]);
    for (let p = 2; p < points.length; p += 2) ctx.lineTo(from + points[p], y + points[p + 1]);
    ctx.closePath();
  }
  ctx.stroke();
}

/**
 * A diagonal hatch over a box: cut candidates, collateral and edge-drag regions. Silence is
 * never hatched (docs/design/SILENCE-VISUALS.md): a muted clip or a closed stretch is an
 * outline-only waveform instead.
 */
export function drawDiagonalHatch(ctx, x, y, w, h, colour) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();
  ctx.strokeStyle = colour;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let offset = -h; offset < w; offset += HATCH_STEP) {
    ctx.moveTo(x + offset, y + h);
    ctx.lineTo(x + offset + h, y);
  }
  ctx.stroke();
  ctx.restore();
}

/** The dash of the preview's band edges: the "preview" signal is a dash (grammar.js). */
export const PREVIEW_DASH = [4, 3];
/** The preview's dashed edges stand this far inside the body, clear of the clip border. */
const PREVIEW_INSET = 2;

/**
 * The Auto-Silence live preview's closed stretches (pixel runs as gatePixelRuns gives them):
 * dashed top and bottom edges in the preview colour (`colours.edge`), 2 px inside the clip
 * body so the clip borders (drawn later, above) never hide them. The waveform layer outlines
 * the would-close columns in the same colour (paint.js `paintClipWave`): together they say
 * "this would become silent", unlike a committed gate (an outline in the track colour and a
 * lock). No veil and no hatch any more (owner, 2026-10-21).
 */
export function drawPreviewBands(ctx, runs, y, h, colours) {
  if (runs.length === 0) return;
  ctx.save();
  ctx.strokeStyle = colours.edge;
  ctx.lineWidth = 1;
  ctx.setLineDash(PREVIEW_DASH);
  ctx.beginPath();
  for (let i = 0; i < runs.length; i += 2) {
    ctx.moveTo(runs[i], y + PREVIEW_INSET + 0.5);
    ctx.lineTo(runs[i + 1], y + PREVIEW_INSET + 0.5);
    ctx.moveTo(runs[i], y + h - PREVIEW_INSET - 0.5);
    ctx.lineTo(runs[i + 1], y + h - PREVIEW_INSET - 0.5);
  }
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
}
