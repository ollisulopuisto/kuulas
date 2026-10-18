// The transcript's commands (WP7), registered by id like the editor's. Backspace is
// Delete (a soft cut on THIS speaker's track: the words go silent in place and the gap
// stays); X is Cut (the stretch is ripple-deleted on every track, `cut_words`). Keys live
// in keymap-default.js, under the "transcript" context.
import { autoName, clipsInRange, describeClips } from "./clipboard.js";
import {
  cutRange,
  cutWordsPlan,
  deleteWordsPlan,
  noSelection,
  ownerTracks,
  selectedIndices,
} from "./transcript-model.js";

/** The selected words, but only while they are the words the server has now. */
export function chosenWords(state) {
  if (!state?.words || state.wordsHead !== state.head) return [];
  const sel = state.transcriptSelection ?? noSelection();
  return selectedIndices(sel).filter((i) => i < state.words.length);
}

/**
 * `app`: getState, edit(change), toast(text, { undo }), cutWords(indices) -> Promise,
 * correct() (opens the inline edit). `t` translates.
 */
export function registerTranscriptCommands(registry, { app, t }) {
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const nameOf = (state, track) => {
    const found = state.project?.tracks.find((x) => x.id === track);
    return found?.speaker || found?.name || track;
  };

  def(
    "transcript.delete_words",
    () => {
      const state = app.getState();
      const indices = chosenWords(state);
      const edits = deleteWordsPlan(state.words, indices);
      if (!edits) return;
      const who = ownerTracks(state.words, indices).map((track) => nameOf(state, track));
      edits.forEach((edit, n) => {
        app.edit({
          op: edit.op,
          args: edit.args,
          label: t("ui.transcript.label.delete"),
          done: () => {
            if (n === edits.length - 1)
              app.toast(
                t("ui.transcript.toast.delete", {
                  count: indices.length,
                  name: who.join(", "),
                }),
                { undo: true },
              );
          },
        });
      });
    },
    (state) => deleteWordsPlan(state.words ?? [], chosenWords(state)) !== null,
  );

  def(
    "transcript.cut_words",
    () => {
      const state = app.getState();
      const indices = chosenWords(state);
      const plan = cutWordsPlan(indices);
      if (!plan) return;
      // X is Cut: the stretch goes to the clipboard first (the same range and every track,
      // as the cut removes), then the words are cut. A failed copy never stops the cut.
      const range = cutRange(state.words, indices);
      const tracks = (state.project?.tracks ?? []).map((track) => track.id);
      const parts = range ? clipsInRange(state.project, tracks, range.start, range.end) : [];
      const name = autoName(describeClips(parts, state.project?.rate ?? 1), t);
      const copying =
        range && tracks.length > 0
          ? app.copy({ ...range, track_ids: tracks, group_editing: false, name })
          : Promise.resolve(false);
      void copying.then(async (copied) => {
        if (!(await app.cutWords(plan.args.indices))) return;
        const key = copied ? "ui.transcript.toast.cut" : "ui.transcript.toast.cut_uncopied";
        app.toast(t(key, { count: indices.length }), { undo: true });
      });
    },
    (state) => cutWordsPlan(chosenWords(state)) !== null,
  );

  def(
    "transcript.correct",
    () => app.correct(),
    (state) => {
      if (!state?.words || state.wordsHead !== state.head) return false;
      const sel = state.transcriptSelection ?? noSelection();
      const picked = chosenWords(state);
      return picked.length === 1 || (picked.length === 0 && sel.cursor >= 0);
    },
  );
}
