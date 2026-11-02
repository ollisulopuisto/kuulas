// Pro Tools style spot placement: align the earliest selected clip to a time while
// preserving every selected clip's relative position. With no clip selection, seek.
import { selectedClips } from "./selection.js";
import { expandGroups } from "./clip-groups.js";

export function spotPlan(state, frame) {
  const selection = expandGroups(state?.project, state?.selection ?? []);
  const clips = selectedClips({ ...state, selection });
  if (clips.length === 0) return { kind: "playhead", frame };
  const first = Math.min(...clips.map(({ clip }) => clip.start));
  return {
    kind: "edit",
    op: "shift_clips",
    args: { clip_ids: clips.map(({ clip }) => clip.id), delta: frame - first },
  };
}
