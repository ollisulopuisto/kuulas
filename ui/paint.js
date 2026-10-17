// What the waveform worker draws: clip bodies and waveforms from peak tiles.
// It takes a plain-data job and a tile lookup, so it runs unchanged in the
// worker (OffscreenCanvas), on the main thread when workers are unavailable,
// and in tests with a recording context.
import { frameToX } from "./format.js";
import { busHues, SPEAKER_HUE_COUNT, zebraSteps } from "./grammar.js";
import { layoutFor, RULER_HEIGHT, visibleRows } from "./lanes.js";
import { columnsFromTiles, pickLevel, waveformColumns } from "./waveform.js";

/** Fallback for --signal-muted-opacity when a job carries none (tests). */
const MUTED_ALPHA = 0.35;
/** -0.1 dBFS: a column at or above it gets the clipping cap. */
const CLIP_LEVEL = 0.989;
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
      clips.push({
        id: clip.id,
        media: clip.media,
        start: clip.start,
        offset: clip.offset,
        length: clip.length,
        muted: Boolean(clip.muted),
        step: steps.get(clip.id) ?? 0,
      });
    }
    rows.push({
      top: row.top,
      height: row.height,
      current: track.id === state.focusTrack,
      // Member lanes carry no band at rest (density rework, 2026-10-18): the
      // group gap and the header spine say "group"; a theme may turn it on.
      band:
        row.bus && colours.memberBands ? (colours.busBands?.[groups.get(row.bus) - 1] ?? "") : "",
      paletteIndex: hues.get(track.id) ?? 0,
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
 * Paint `job` into `ctx`. `lookup(media, level, tile)` returns a tile's
 * Float32Array or undefined. Returns { missing }: the tiles to fetch before
 * painting again.
 */
export function paintWaveforms(ctx, job, lookup) {
  const missing = new Map();
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
      const bars = waveformColumns(data, job.mode, job.scale, h, job.gain);
      ctx.fillStyle = colours.wave;
      ctx.globalAlpha = (clip.muted ? faint : 1) * WAVE_ALPHA;
      ctx.beginPath();
      for (let column = 0; column < to - from; column += 1) {
        const barTop = bars[2 * column];
        const barBottom = bars[2 * column + 1];
        if (barBottom > barTop) ctx.rect(from + column, y + barTop, 1, barBottom - barTop);
      }
      ctx.fill();
      // Clipping: a cap on top of each column whose peak reaches -0.1 dBFS.
      if (job.clipping) {
        ctx.fillStyle = job.clipping;
        for (let column = 0; column < to - from; column += 1) {
          const peak = Math.max(Math.abs(data[2 * column]), Math.abs(data[2 * column + 1]));
          if (peak >= CLIP_LEVEL) ctx.fillRect(from + column, y + bars[2 * column], 1, CAP_PX);
        }
      }
      ctx.globalAlpha = 1;
    }
  }
  ctx.restore();
  ctx.globalAlpha = 1;
  return { missing: [...missing.values()] };
}
