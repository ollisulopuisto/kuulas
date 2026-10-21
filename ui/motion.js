// The motion language (owner, 2026-10-18): gentle cues that pull the eye to
// what changed, never decoration. One setting (full / subtle / off, default
// full, off when the OS asks for reduced motion) decides how every cue plays;
// "off" shows a static highlight carrying the same information. The setting
// lands on <html data-motion>; CSS reads it, canvases ask cueFor. Rules:
// 120-300 ms mostly, one animation at a time, nothing loops except real
// activity (jobs, recording), nothing moves a target under the pointer,
// nothing blocks input, nothing animates during playback but the playhead.
// Spec: docs/design/GUI-DESIGN.md, "Motion".

export const MOTION_MODES = ["full", "subtle", "off"];

/**
 * Every cue: what plays, its duration and easing tokens (tokens.css), its
 * length in ms (for canvases), whether it moves things, and the still
 * alternative for "off".
 */
export const CUES = {
  "undo-flash": {
    duration: "--dur-flash",
    easing: "--ease-standard",
    ms: 600,
    moves: false,
    still: "a 2 px accent outline on the changed clips for 1.2 s",
  },
  "ripple-close": {
    duration: "--dur-slow",
    easing: "--ease-standard",
    ms: 260,
    moves: true,
    still: "the later material appears in place with the undo flash outline",
  },
  "import-in": {
    duration: "--dur-slow",
    easing: "--ease-standard",
    ms: 240,
    moves: true,
    still: "new tracks appear with the accent outline for 1.2 s",
  },
  "candidate-pulse": {
    duration: "--dur-base",
    easing: "--ease-standard",
    ms: 180,
    moves: false,
    still: "the current candidate's 2 px edges and its highlighted list row",
  },
  "collateral-breathe": {
    duration: "--dur-flash",
    easing: "--ease-standard",
    ms: 600,
    moves: false,
    still: "the collateral hatch at full strength, no change over time",
  },
  "ab-cue": {
    duration: "--dur-base",
    easing: "--ease-standard",
    ms: 140,
    moves: false,
    still: "the active slot stays filled; the other slots are outlined",
  },
  toast: {
    duration: "--dur-base",
    easing: "--ease-standard",
    ms: 140,
    moves: true,
    still: "the message appears and disappears without movement",
  },
  "soft-cut-restore": {
    duration: "--dur-slow",
    easing: "--ease-standard",
    ms: 240,
    moves: false,
    still: "the restored stretch carries the undo flash outline",
  },
  "focus-resize": {
    duration: "--dur-layout",
    easing: "--ease-standard",
    ms: 120,
    moves: true,
    still: "the lanes take their focus heights at once; the inactive look marks the others",
  },
  "playhead-ease": {
    duration: "--dur-slow",
    easing: "--ease-standard",
    ms: 200,
    moves: true,
    still: "the playhead jumps; its cap shows a 1.2 s halo at the new place",
  },
};

/** The effective mode from the user's choice (or null) and the OS preference. */
export function motionMode(choice, prefersReduced) {
  if (MOTION_MODES.includes(choice)) return choice;
  return prefersReduced ? "off" : "full";
}

/**
 * How cue `name` plays in `mode`: { animate, move, ms, still }. "subtle"
 * fades only (no movement) at 60 % of the length. While playing, nothing
 * animates (the playhead itself is drawn, not animated).
 */
export function cueFor(name, mode, { playing = false } = {}) {
  const cue = CUES[name];
  if (!cue) return { animate: false, move: false, ms: 0, still: "" };
  if (mode === "off" || playing) return { animate: false, move: false, ms: 0, still: cue.still };
  if (mode === "subtle") {
    return { animate: true, move: false, ms: Math.round(cue.ms * 0.6), still: cue.still };
  }
  return { animate: true, move: cue.moves, ms: cue.ms, still: cue.still };
}
