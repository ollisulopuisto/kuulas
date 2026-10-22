// Mod+S, Shift+Mod+S, File > Open earlier version… and File > Back up now. Every edit is
// committed as it is made, so "save" has nothing to write: it marks the current step in the
// history as a saved version (owner, 2026-10-21). Mod+S names it by the time ("Saved 14.32");
// Shift+Mod+S asks for a name. A step that already is a version makes no second one and the
// toast says when it was saved. The backup copy is its own command (the 10-minute timer makes
// them too). The keys are ours only while a project is open; the registry's key handler then
// also stops the browser's own Save-page dialog.

/** The local time as HH.MM (Finnish style), for the version's name. */
export function clockTime(date) {
  const two = (n) => String(n).padStart(2, "0");
  return `${two(date.getHours())}.${two(date.getMinutes())}`;
}

const hasProject = (state) => Boolean(state?.project);

/**
 * `app`: toast(text, { undo, action }), command(name, args) -> Promise<response | null> (null
 * after an error it has already shown, e.g. a read-only project), clock() -> Date,
 * markLeftOff() (a save is also "where I left off": the playhead now, written to resume.json),
 * askName(suggestion) -> Promise<string | null> (null: cancelled), refreshHistory() (the
 * History list fetches again: a version was added without the head moving),
 * renameSaved(node) (History opens with that version's name field), openEarlierVersion().
 */
export function registerSaveCommands(registry, { app, t }) {
  /** The toast for what the server did; the Rename button only for a version just made. */
  function say(saved) {
    const when = new Date(saved.created);
    if (saved.result === "already") {
      const time = Number.isNaN(when.getTime()) ? saved.name : clockTime(when);
      app.toast(t("ui.save.already", { time }), { undo: false });
    } else if (saved.result === "renamed") {
      app.toast(t("ui.save.version_renamed", { name: saved.name }), { undo: false });
    } else {
      app.toast(t("ui.save.version_made", { name: saved.name }), {
        undo: false,
        action: { label: t("ui.save.rename"), run: () => void rename(saved.node) },
      });
    }
  }

  /** History shows the version (fetched again first) and its name field opens. */
  async function rename(node) {
    await app.refreshHistory();
    app.renameSaved(node);
  }

  async function save(args) {
    const response = await app.command("save_checkpoint", args);
    if (!response?.saved) return;
    say(response.saved);
    void app.refreshHistory();
    app.markLeftOff();
  }

  const suggestion = () => t("ui.save.checkpoint_name", { time: clockTime(app.clock()) });

  registry.register("app.save", () => save({ name: suggestion() }), {
    can: hasProject,
    hintKey: "cmd.app.save.hint",
  });
  registry.register(
    "app.save_named",
    async () => {
      const name = await app.askName(suggestion());
      if (name === null || name === undefined || name.trim() === "") return;
      // rename: a name typed on a step that already is a version renames that version.
      await save({ name: name.trim(), rename: true });
    },
    { can: hasProject, hintKey: "cmd.app.save_named.hint" },
  );
  registry.register("app.open_earlier_version", () => app.openEarlierVersion(), {
    can: hasProject,
    hintKey: "cmd.app.open_earlier_version.hint",
  });
  registry.register(
    "app.backup_now",
    async () => {
      if (await app.command("save_backup", {})) app.toast(t("ui.backup.done"), { undo: false });
    },
    { can: hasProject, hintKey: "cmd.app.backup_now.hint" },
  );
}
