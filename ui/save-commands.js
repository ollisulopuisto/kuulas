// Mod+S and Shift+Mod+S. Every edit is committed as it is made, so "save" has nothing
// to write: Mod+S makes a backup copy now (and says so, because people press it
// without thinking), Shift+Mod+S names the current step in the history. The keys are
// ours only while a project is open; the registry's key handler then also stops the
// browser's own Save-page dialog.

/** The local time as HH.MM (Finnish style), for the checkpoint's name. */
export function clockTime(date) {
  const two = (n) => String(n).padStart(2, "0");
  return `${two(date.getHours())}.${two(date.getMinutes())}`;
}

const hasProject = (state) => Boolean(state?.project);

/**
 * `app`: toast(text, { undo }), command(name, args) -> Promise<response | null> (null after
 * an error it has already shown, e.g. a read-only project), clock() -> Date,
 * markLeftOff() (a save is also "where I left off": the playhead now, written to resume.json).
 */
export function registerSaveCommands(registry, { app, t }) {
  registry.register(
    "app.save",
    async () => {
      if (await app.command("save_backup", {})) {
        app.toast(t("ui.save.done"), { undo: false });
        app.markLeftOff();
      }
    },
    { can: hasProject, hintKey: "cmd.app.save.hint" },
  );
  registry.register(
    "app.save_named",
    async () => {
      const name = t("ui.save.checkpoint_name", { time: clockTime(app.clock()) });
      if (await app.command("save_checkpoint", { name })) {
        app.toast(t("ui.save.named", { name }), { undo: false });
        app.markLeftOff();
      }
    },
    { can: hasProject, hintKey: "cmd.app.save_named.hint" },
  );
}
