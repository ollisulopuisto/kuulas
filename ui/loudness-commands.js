// Match loudness (a Clip-menu / palette command, no default key): sets each clip's gain
// so its measured loudness lands on the target. Measuring takes seconds, so a toast says so
// first; the server answers with a report (matched, skipped as silent) and one undo step.
import { selectedClips } from "./selection.js";

/** No project setting for a loudness target exists yet, so spoken-word podcasts' -16 LUFS. */
export const DEFAULT_LOUDNESS_LUFS = -16;

/** The clips to match: the selected ones, else every clip of the current track. */
export function matchTargets(state) {
  const chosen = selectedClips(state);
  if (chosen.length > 0) return chosen.map((entry) => entry.clip.id);
  const track = state?.focusBus
    ? null
    : state?.project?.tracks.find((x) => x.id === state.focusTrack);
  return track ? track.clips.map((clip) => clip.id) : [];
}

export function reportToast(report, t) {
  return t("ui.loudness.done", { count: report.matched.length, skipped: report.skipped.length });
}

/** `app`: getState, toast(text, { undo }), matchLoudness(clipIds, target) -> report | null. */
export function registerLoudnessCommands(registry, { app, t }) {
  let busy = false;
  registry.register(
    "clip.match_loudness",
    async () => {
      if (busy) return;
      const ids = matchTargets(app.getState());
      if (ids.length === 0) return;
      busy = true;
      app.toast(t("ui.loudness.measuring", { count: ids.length }), { undo: false });
      try {
        const report = await app.matchLoudness(ids, DEFAULT_LOUDNESS_LUFS);
        if (report) app.toast(reportToast(report, t), { undo: report.matched.length > 0 });
      } finally {
        busy = false;
      }
    },
    {
      can: (state) => matchTargets(state).length > 0,
      hintKey: "cmd.clip.match_loudness.hint",
    },
  );
}
