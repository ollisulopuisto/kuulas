// The take drawn on the timeline while it records (owner, 2026-10-23: "I want to see them
// drawn"). The recorder sends a level event several times a second: the loudest sample of each
// channel since the last one, and the position on the take's clock. Kept per lane as peaks,
// placed on the timeline where the take's clips will land (at + position - pre-roll), and
// read back as one column per screen pixel. Pure: timeline.js draws the columns.

/** dBFS to a linear peak 0..1 (a missing or silent reading is 0). */
export function dbToPeak(db) {
  if (!Number.isFinite(db) || db <= -100) return 0;
  return Math.min(1, 10 ** (db / 20));
}

export function createLiveTake() {
  let at = 0;
  let preroll = 0;
  let lanes = [];
  // Per lane: parallel arrays, positions on the take's clock and the peak since the last.
  let positions = [];
  let peaks = [];
  let active = false;

  const frameOf = (position) => at + position - preroll;

  return {
    get active() {
      return active;
    },
    /** `at`: where the take starts on the timeline; `preroll`: frames before Record; `lanes`:
     *  [{ trackId }] in the recorder's channel order (null id: a new track, not yet there). */
    begin({ at: start, preroll: before = 0, lanes: list }) {
      at = Math.max(0, Math.round(Number(start) || 0));
      preroll = Math.max(0, Math.round(Number(before) || 0));
      lanes = list.map((lane) => ({ trackId: lane.trackId ?? null }));
      positions = lanes.map(() => []);
      peaks = lanes.map(() => []);
      active = true;
    },
    /** A level event: the position on the take's clock, and each lane's reading in dBFS. */
    push(position, readings) {
      if (!active || !Number.isFinite(position)) return;
      lanes.forEach((_lane, i) => {
        positions[i].push(position);
        peaks[i].push(dbToPeak(readings?.[i]));
      });
    },
    /** The lanes that have a track to draw on: [{ index, trackId }]. */
    lanes() {
      if (!active) return [];
      return lanes.flatMap((lane, index) =>
        lane.trackId ? [{ index, trackId: lane.trackId }] : [],
      );
    },
    /**
     * One peak per screen pixel (0 = nothing), for lane `index` over the view `scroll` (frame at
     * x = 0), `zoom` (frames per pixel) and `width`. Each event covers the stretch since the
     * one before it, so there are no holes; a pixel with several events shows the loudest.
     */
    columns(index, { scroll, zoom, width }) {
      const out = new Float32Array(Math.max(0, width));
      const at_ = positions[index];
      const values = peaks[index];
      if (!active || !at_ || at_.length === 0 || !(zoom > 0)) return out;
      let before = 0;
      for (let i = 0; i < at_.length; i += 1) {
        const from = Math.floor((frameOf(before) - scroll) / zoom);
        const to = Math.floor((frameOf(at_[i]) - scroll) / zoom);
        before = at_[i];
        if (to < 0 || from >= out.length) continue;
        const value = values[i];
        for (let x = Math.max(0, from); x <= Math.min(out.length - 1, to); x += 1) {
          if (value > out[x]) out[x] = value;
        }
      }
      return out;
    },
    reset() {
      active = false;
      lanes = [];
      positions = [];
      peaks = [];
    },
  };
}
