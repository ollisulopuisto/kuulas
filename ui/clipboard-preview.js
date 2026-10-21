// The clipboard preview's state on the page (WP46): which chip plays, what its Play button
// shows, and how far its progress meter is filled. Pure; app.js keeps the state and the
// live channel's "preview" anchors (a playhead clock of their own, never the timeline's).

/** How much of the preview has been heard, 0..1: `position` over `duration` (frames). */
export function previewFraction(position, duration) {
  if (!(duration > 0) || !Number.isFinite(position)) return 0;
  return Math.min(1, Math.max(0, position / duration));
}

/**
 * The playing chip, `{ id, seq }` or null, after `event`:
 * - `{ type: "start", id, seq }`: the server started that entry's preview at transport
 *   version `seq` (another chip's preview is replaced);
 * - `{ type: "stop" }`: the user stopped it (the chip again, Stop or Space);
 * - `{ type: "ended", seq }`: the live channel says no preview plays. One older than the
 *   start (the previous preview ending while this one began) is dropped.
 */
export function previewPlaying(current, event) {
  switch (event.type) {
    case "start":
      return { id: event.id, seq: event.seq ?? null };
    case "stop":
      return null;
    case "ended":
      if (!current) return null;
      if (current.seq === null || event.seq === null || event.seq === undefined) return null;
      return event.seq > current.seq ? null : current;
    default:
      return current;
  }
}

/**
 * Which stop the playing chip's Stop button sends. A preview played while the timeline
 * plays is mixed into it (owner, 2026-10-21): only its voice goes away, the timeline plays
 * on ("preview"). Played alone it is the transport's stop, which puts the playhead back.
 */
export function previewStop(state) {
  return state.playing && state.clipboardPlaying ? "preview" : "transport";
}

/** What an entry's Play button shows: Stop while that entry plays, else Play. */
export function previewButton(playing, entryId) {
  const on = playing?.id === entryId;
  return {
    playing: on,
    icon: on ? "stop" : "play",
    labelKey: on ? "ui.clipboard.preview_stop" : "ui.clipboard.preview",
  };
}
