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
