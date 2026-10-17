// What the waveform worker draws: clip bodies and waveforms from peak tiles.
// It takes a plain-data job and a tile lookup, so it runs unchanged in the
// worker (OffscreenCanvas), on the main thread when workers are unavailable,
// and in tests with a recording context.
import { frameToX } from "./format.js";
import { layoutRows, RULER_HEIGHT, visibleRows } from "./lanes.js";
import { columnsFromTiles, pickLevel, waveformColumns } from "./waveform.js";

const MUTED_ALPHA = 0.35;
/** The sketches draw bars at 75 % so the clip colour still shows through. */
const WAVE_ALPHA = 0.75;
/** Clip bodies stand 2 px inside their lane so neighbours do not touch. */
const BODY_INSET = 2;
const MUSIC_COLOUR = 3;

/** Which palette entry a track uses: music has its own, speech cycles. */
export function paletteIndex(track, index) {
  return track.kind === "music" ? MUSIC_COLOUR : index % MUSIC_COLOUR;
}

/**
 * A structured-clone-safe description of what is on screen: only rows in view
 * and, in each, only the clips that overlap the visible time.
 */
export function makeWaveformJob(state, { width, height, ratio, id }, palette) {
  const { project, scroll, zoom, scrollY, laneHeight } = state;
  const layout = layoutRows(project, laneHeight);
  const rows = [];
  const first = scroll;
  const last = scroll + width * zoom;
  const shown = visibleRows(layout, scrollY, height - RULER_HEIGHT);
  for (const row of shown) {
    if (row.kind !== "track") continue;
    const track = project.tracks[row.index];
    const clips = [];
    for (const clip of track.clips) {
      if (clip.start + clip.length < first || clip.start > last) continue;
      clips.push({
        id: clip.id,
        media: clip.media,
        start: clip.start,
        offset: clip.offset,
        length: clip.length,
        muted: Boolean(clip.muted),
      });
    }
    rows.push({
      top: row.top,
      height: row.height,
      paletteIndex: paletteIndex(track, row.index),
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
    for (const clip of row.clips) {
      const left = frameToX(clip.start, job.scroll, job.zoom);
      const right = frameToX(clip.start + clip.length, job.scroll, job.zoom);
      const from = Math.max(0, Math.floor(left));
      const to = Math.min(job.width, Math.ceil(right));
      if (to <= from) continue;
      const y = top + BODY_INSET;
      const h = row.height - 2 * BODY_INSET;
      ctx.globalAlpha = clip.muted ? MUTED_ALPHA : 1;
      ctx.fillStyle = colours.fill;
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
      ctx.globalAlpha = (clip.muted ? MUTED_ALPHA : 1) * WAVE_ALPHA;
      ctx.beginPath();
      for (let column = 0; column < to - from; column += 1) {
        const barTop = bars[2 * column];
        const barBottom = bars[2 * column + 1];
        if (barBottom > barTop) ctx.rect(from + column, y + barTop, 1, barBottom - barTop);
      }
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
  ctx.restore();
  ctx.globalAlpha = 1;
  return { missing: [...missing.values()] };
}
