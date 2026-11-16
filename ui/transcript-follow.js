// The transcript unlocks on a user scroll and stays unlocked until the user asks to follow.
export function transcriptFollowStep({ paused }, event) {
  if (event.type === "manual-scroll") return { paused: true };
  if (event.type === "follow" || event.type === "play-start") return { paused: false };
  return { paused };
}

/** Reset follow only on a transition into playback, not on repeated playing anchors. */
export function transcriptPlaybackStep({ paused, wasPlaying }, playing) {
  const nowPlaying = Boolean(playing);
  return {
    paused: nowPlaying && !wasPlaying ? false : paused,
    wasPlaying: nowPlaying,
  };
}

/**
 * The word to scroll into view for the playhead: none while playing after a manual scroll; else
 * the word under it, or in a pause the last word started. A stopped playhead always follows,
 * because moving it is the user's own act.
 */
export function followWord({ playing, paused, at, before }) {
  if (playing && paused) return -1;
  return at >= 0 ? at : before;
}
