// The Candidates commands (WP18 UI), registered by id like the editor's. The ids and keys
// are in keymap-default.js: ] [ D and Shift+Mod+D work everywhere (they are not typing
// keys), Enter, K and Shift+Space only while the Candidates tab has the keyboard, because
// Enter and Shift+Space mean other things elsewhere and K is kept for the shuttle's stop.
// Enter is the soft cut (Delete: the gap stays); closing the gap is a second command.
import { extractCurrent, listedRows, stepTarget } from "./candidates-model.js";

const hasProject = (state) => Boolean(state?.project);
const currentRow = (state) => extractCurrent(state.candidates ?? [], state.candidateCurrent);
const currentOpen = (state) => currentRow(state)?.state === "open";

/** The track that plays `frame`, else null (the server picks the first that does). */
function trackAt(state, frame) {
  const track = state.project?.tracks.find((item) => item.id === state.focusTrack);
  const plays = track?.clips.some(
    (clip) => clip.start <= frame && frame < clip.start + clip.length,
  );
  return plays ? track.id : null;
}

/**
 * What D does: the in-out range when both are set; otherwise a stretch begun at the
 * playhead by the first press and ended at the playhead by the second (playback never
 * stops, so it works on a first listen). -> { action: "mark", start, end, track } |
 * { action: "begin", at }.
 */
export function markPlan(state) {
  const { inPoint, outPoint, playhead, candidateMarkStart: begun } = state;
  if (inPoint !== null && outPoint !== null && inPoint < outPoint) {
    return { action: "mark", start: inPoint, end: outPoint, track: trackAt(state, inPoint) };
  }
  if (begun === null || begun === undefined || begun === playhead) {
    return { action: "begin", at: playhead };
  }
  const start = Math.min(begun, playhead);
  return { action: "mark", start, end: Math.max(begun, playhead), track: trackAt(state, start) };
}

/**
 * `app`: getState, patch(statePatch), selectCandidate(row) (cursor, scroll, current),
 * findCandidates(), applyCandidate(id, mode), keepCandidate(id), markCandidate(start, end,
 * track), previewCandidate(row), toast(text). `t` translates.
 */
export function registerCandidateCommands(registry, { app, t }) {
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const rows = (state) => listedRows(state.candidates ?? [], state.candidatesOpenOnly !== false);
  const stepFrom = (state, direction) =>
    stepTarget(
      rows(state),
      { currentId: state.candidateCurrent, playhead: state.playhead },
      direction,
    );
  const step = (direction) => () => {
    const target = stepFrom(app.getState(), direction);
    if (target) app.selectCandidate(target);
  };

  def("candidate.next", step(1), (state) => stepFrom(state, 1) !== null);
  def("candidate.previous", step(-1), (state) => stepFrom(state, -1) !== null);

  // Enter on a focused button must press that button (the panel's own actions), not apply
  // the candidate: the key handler has already cancelled the browser's click.
  def(
    "candidate.apply",
    (event) => {
      if (event?.target?.tagName === "BUTTON") return event.target.click();
      const row = currentRow(app.getState());
      if (row) app.applyCandidate(row.id, "soft");
    },
    currentOpen,
  );
  def(
    "candidate.apply_ripple",
    () => {
      const row = currentRow(app.getState());
      if (row) app.applyCandidate(row.id, "ripple");
    },
    currentOpen,
  );
  def(
    "candidate.reject",
    () => {
      const row = currentRow(app.getState());
      if (row) app.keepCandidate(row.id);
    },
    currentOpen,
  );
  def(
    "candidate.preview",
    () => {
      const row = currentRow(app.getState());
      if (row) app.previewCandidate(row);
    },
    (state) => currentOpen(state) && currentRow(state).start !== null,
  );
  def(
    "candidate.filter",
    () => app.patch({ candidatesOpenOnly: app.getState().candidatesOpenOnly === false }),
    hasProject,
  );
  def(
    "candidate.find",
    () => app.findCandidates(),
    (state) => hasProject(state) && !state.candidateBusy,
  );

  def(
    "candidate.mark",
    () => {
      const plan = markPlan(app.getState());
      if (plan.action === "begin") {
        app.patch({ candidateMarkStart: plan.at });
        app.toast(t("ui.candidates.mark_begun"));
        return;
      }
      app.patch({ candidateMarkStart: null });
      app.markCandidate(plan.start, plan.end, plan.track);
    },
    hasProject,
  );
  def(
    "candidate.mark_range",
    () => {
      const state = app.getState();
      app.markCandidate(state.inPoint, state.outPoint, trackAt(state, state.inPoint));
    },
    (state) =>
      hasProject(state) &&
      state.inPoint !== null &&
      state.outPoint !== null &&
      state.inPoint < state.outPoint,
  );
}
