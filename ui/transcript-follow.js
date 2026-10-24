// The transcript unlocks on a user scroll and stays unlocked until the user asks to follow.
export function transcriptFollowStep({ paused, playing }, event) {
  if (event.type === "manual-scroll" && playing) return { paused: true };
  if (event.type === "follow" || event.type === "play-start") return { paused: false };
  return { paused };
}
