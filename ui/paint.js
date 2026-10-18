// What the waveform worker draws: clip bodies and waveforms from peak tiles.
// It takes a plain-data job and a tile lookup, so it runs unchanged in the
// worker (OffscreenCanvas), on the main thread when workers are unavailable,
// and in tests with a recording context.
import { CLIP_LIMIT_DB, columnOvers } from "./clip-overs.js";
import { frameToX } from "./format.js";
import { columnGainsDb, waveformScale } from "./gain-scale.js";
import { flatBar, gatePixelRuns } from "./gate.js";
import { busHues, SPEAKER_HUE_COUNT, zebraSteps } from "./grammar.js";
import { layoutFor, RULER_HEIGHT, visibleRows } from "./lanes.js";
import { columnsFromTiles, pickLevel, waveformColumns } from "./waveform.js";

/** Fallback for --signal-muted-opacity when a job carries none (tests). */
const MUTED_ALPHA = 0.35;
/** Below this a gain is silence: JSON cannot carry -Infinity, so the job clamps to it. */
const SILENCE_DB = -200;
const CAP_PX = 3;
/** Bars are opaque: --track-N-wave on --track-N-body is checked at >= 3:1 (tokens.test.js). */
const WAVE_ALPHA = 1;
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
function baseGainDb(clip, track) {
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
      current: track.id === state.focusTrack,
      // Member lanes carry no band at rest (density rework, 2026-10-18): the
      // group gap and the header spine say "group"; a theme may turn it on.
      band:
        row.bus && colours.memberBands ? (colours.busBands?.[groups.get(row.bus) - 1] ?? "") : "",
      // WP44: the gate as merged pixel runs [x0, x1, ...]; the painter draws
      // the waveform flat under them. Empty when the user hides gates.
      gate: state.showGates === false ? [] : gatePixelRuns(track.gate, scroll, zoom, width),
      paletteIndex: hues.get(track.id) ?? 0,
      scale: scaleFor(track.kind, state.waveformScale),
      clips,
    });
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
    laneCurrent: colours.laneCurrent ?? "",
    clipping: colours.clipping ?? "",
    mutedOpacity: colours.mutedOpacity ?? MUTED_ALPHA,
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
function gained(clip, data, startFrame, framesPerPixel) {
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
    const colours = job.palette[row.paletteIndex % job.palette.length];
    // The current track (the ↑/↓ cursor) reads across the whole lane.
    if (row.current && job.laneCurrent) {
      ctx.fillStyle = job.laneCurrent;
      ctx.fillRect(0, top, job.width, row.height - 1);
    }
    // The bus band: a faint tint of the bus colour behind the group's lanes.
    if (row.band) {
      ctx.fillStyle = row.band;
      ctx.fillRect(0, top, job.width, row.height - 1);
    }
    const faint = job.mutedOpacity ?? MUTED_ALPHA;
    for (const clip of row.clips) {
      const left = frameToX(clip.start, job.scroll, job.zoom);
      const right = frameToX(clip.start + clip.length, job.scroll, job.zoom);
      const from = Math.max(0, Math.floor(left));
      const to = Math.min(job.width, Math.ceil(right));
      if (to <= from) continue;
      const y = top + BODY_INSET;
      const h = row.height - 2 * BODY_INSET;
      ctx.globalAlpha = clip.muted ? faint : 1;
      // Zebra: a clip from a different file than its neighbour takes the other tone.
      ctx.fillStyle = clip.step === 1 && colours.fillAlt ? colours.fillAlt : colours.fill;
      ctx.fillRect(left, y, Math.max(1, right - left), h);
      const startFrame = clip.offset + (job.scroll + from * job.zoom - clip.start);
      const { data, missing: absent } = columnsFromTiles({
        lookup: (tile) => lookup(clip.media, level, tile),
        level,
        startFrame,
        framesPerPixel: job.zoom,
        count: to - from,
      });
      for (const tile of absent)
        missing.set(`${clip.media}/${level}/${tile}`, { media: clip.media, level, tile });
      const { shown, dbs } = gained(clip, data, startFrame, job.zoom);
      const bars = waveformColumns(shown, job.mode, row.scale ?? job.scale, h, job.gain);
      if (row.gate?.length) flattenGated(bars, data, row.gate, from, to, job.mode, h);
      // Clipping is judged per drawn column (a peak bucket at this zoom), on the true gain,
      // not the capped display scale. Gated columns are zeroed above, so they never clip.
      // A muted clip does not play, so it is not flagged.
      const judged = clip.muted
        ? null
        : columnOvers(data, dbs ?? new Float32Array(to - from), CLIP_LIMIT_DB);
      const anyOver = judged?.over.includes(1) ?? false;
      if (anyOver) overs[clip.id] = judged.maxOver;
      const flagged = job.clipping && anyOver ? judged.over : null;
      ctx.fillStyle = colours.wave;
      ctx.globalAlpha = (clip.muted ? faint : 1) * WAVE_ALPHA;
      ctx.beginPath();
      for (let column = 0; column < to - from; column += 1) {
        const barTop = bars[2 * column];
        const barBottom = bars[2 * column + 1];
        if (barBottom > barTop && !flagged?.[column])
          ctx.rect(from + column, y + barTop, 1, barBottom - barTop);
      }
      ctx.fill();
      // Clipping: the whole bar of a column over the limit in the clipping colour, with a
      // cap on top (the shape twin of the colour, grammar.js `clipping`).
      if (flagged) {
        ctx.fillStyle = job.clipping;
        ctx.beginPath();
        for (let column = 0; column < to - from; column += 1) {
          if (!flagged[column]) continue;
          const barTop = bars[2 * column];
          const barBottom = bars[2 * column + 1];
          if (barBottom > barTop) ctx.rect(from + column, y + barTop, 1, barBottom - barTop);
        }
        ctx.fill();
        for (let column = 0; column < to - from; column += 1) {
          if (flagged[column]) ctx.fillRect(from + column, y + bars[2 * column], 1, CAP_PX);
        }
      }
      ctx.globalAlpha = 1;
    }
  }
  ctx.restore();
  ctx.globalAlpha = 1;
  return { missing: [...missing.values()], overs };
}

/**
 * Draw the columns inside the gate's pixel runs flat: the 1 px floor line,
 * and no clipping cap (their peaks are zeroed). The band's veil is drawn on
 * the overlay; this is the "waveform drawn flat under it" of the design.
 */
function flattenGated(bars, data, runs, from, to, mode, height) {
  const [floorTop, floorBottom] = flatBar(mode, height);
  for (let i = 0; i < runs.length; i += 2) {
    const first = Math.max(runs[i], from) - from;
    const last = Math.min(runs[i + 1], to) - from;
    for (let column = first; column < last; column += 1) {
      bars[2 * column] = floorTop;
      bars[2 * column + 1] = floorBottom;
      data[2 * column] = 0;
      data[2 * column + 1] = 0;
    }
  }
}
