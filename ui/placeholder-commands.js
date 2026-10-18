// The narration placeholder commands (WP43): T adds one at the play cursor on the current
// track and asks for its text; Enter edits the selected one; Take records or imports a file
// into it; Shift+Alt+T deletes it. Each is one undoable edit with a toast that offers Undo.
// Keys are in keymap-default.js. The text prompt is the app's (`promptText`), so these stay
// testable without a DOM.
import { newPlaceholderId, selectedPlaceholder, targetTrack } from "./placeholders-model.js";

const hasProject = (state) => Boolean(state?.project);
const placeholdersOf = (state) => state?.project?.placeholders ?? [];

/**
 * `app`: getState, patch(statePatch), edit(change), toast(text, { undo }), seek(frame),
 * promptText({ text, rate }) -> Promise<string | null> (null when cancelled),
 * takeFor(placeholderId) (pick a file, replace in place), download(path, fallback) -> name | null.
 * `t` translates.
 */
export function registerPlaceholderCommands(registry, { app, t, makeId = newPlaceholderId }) {
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const hasSelection = (state) => hasProject(state) && selectedPlaceholder(state) !== null;

  def(
    "placeholder.add",
    async () => {
      const state = app.getState();
      const track = targetTrack(state);
      if (!track) return;
      const text = await app.promptText({ text: "", rate: state.project.rate });
      if (!text?.trim()) return;
      const id = makeId();
      app.edit({
        op: "add_placeholder",
        args: { track_id: track, start: state.playhead, text: text.trim(), placeholder_id: id },
        label: t("ui.placeholders.history.add"),
        done: () => {
          app.patch({ placeholderSelected: id });
          app.toast(t("ui.placeholders.added"), { undo: true });
        },
      });
    },
    (state) => hasProject(state) && targetTrack(state) !== null,
  );

  def(
    "placeholder.edit",
    async () => {
      const state = app.getState();
      const current = selectedPlaceholder(state);
      if (!current) return;
      const text = await app.promptText({ text: current.text, rate: state.project.rate });
      if (!text?.trim() || text.trim() === current.text) return;
      app.edit({
        op: "edit_placeholder_text",
        args: { placeholder_id: current.id, text: text.trim() },
        label: t("ui.placeholders.history.edit"),
        done: () => app.toast(t("ui.placeholders.edited"), { undo: true }),
      });
    },
    hasSelection,
  );

  def(
    "placeholder.take",
    () => {
      const current = selectedPlaceholder(app.getState());
      if (current) app.takeFor(current.id);
    },
    hasSelection,
  );

  def(
    "placeholder.delete",
    () => {
      const current = selectedPlaceholder(app.getState());
      if (!current) return;
      app.edit({
        op: "delete_placeholder",
        args: { placeholder_id: current.id },
        label: t("ui.placeholders.history.delete"),
        done: () => {
          if (app.getState().placeholderSelected === current.id)
            app.patch({ placeholderSelected: null });
          app.toast(t("ui.placeholders.deleted"), { undo: true });
        },
      });
    },
    hasSelection,
  );

  for (const [id, path, file] of [
    ["export.narration_script_txt", "/api/narration-script?format=txt", "narration-script.txt"],
    ["export.narration_script_md", "/api/narration-script?format=md", "narration-script.md"],
  ]) {
    def(
      id,
      async () => {
        const name = await app.download(path, file);
        if (name) app.toast(t("ui.export.done", { name }), { undo: false });
      },
      (state) => hasProject(state) && placeholdersOf(state).length > 0,
    );
  }
}
