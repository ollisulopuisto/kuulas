import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { clockTime, registerSaveCommands } from "../save-commands.js";

// `answers`: what each server command answers; save_checkpoint's default is a made version.
function setup(answers = {}, { asked = "My name" } = {}) {
  const registry = createRegistry();
  const calls = { commands: [], toasts: [], left: [], asked: [], history: [], renamed: [] };
  registerSaveCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    app: {
      toast: (text, options) => calls.toasts.push([text, options]),
      command: async (name, args) => {
        calls.commands.push([name, args]);
        if (name in answers) return answers[name];
        if (name === "save_checkpoint") {
          return {
            saved: { node: "N1", name: args.name, created: "2026-10-18T06:05:00Z", result: "made" },
          };
        }
        return {};
      },
      clock: () => new Date(2026, 9, 18, 9, 5),
      markLeftOff: () => calls.left.push("mark"),
      askName: async (initial) => {
        calls.asked.push(initial);
        return asked;
      },
      refreshHistory: async () => calls.history.push("refresh"),
      renameSaved: (node) => calls.renamed.push(node),
      openEarlierVersion: () => calls.history.push("open_saved"),
    },
  });
  return { registry, calls };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));
const saved = (result, name = "Saved 09.05") => ({
  saved: { node: "N1", name, created: new Date(2026, 9, 18, 9, 5).toISOString(), result },
});

describe("save commands", () => {
  test("the clock time is HH.MM, zero padded", () => {
    assert.equal(clockTime(new Date(2026, 9, 18, 9, 5)), "09.05");
  });

  test("all four are ready and need a project", () => {
    const { registry } = setup();
    for (const id of ["app.save", "app.save_named", "app.backup_now", "app.open_earlier_version"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.can(id, {}), false, id);
      assert.equal(registry.can(id, { project: {} }), true, id);
    }
  });

  test("Mod+S makes a version named by the time, not a backup, and offers Rename", async () => {
    const { registry, calls } = setup();
    registry.run("app.save", null, { project: {} });
    await settle();
    assert.deepEqual(calls.commands, [
      ["save_checkpoint", { name: 'ui.save.checkpoint_name{"time":"09.05"}' }],
    ]);
    assert.equal(
      calls.commands.some(([name]) => name === "save_backup"),
      false,
    );
    const [text, options] = calls.toasts[0];
    assert.match(text, /^ui\.save\.version_made.*checkpoint_name/);
    assert.equal(options.undo, false);
    assert.match(options.action.label, /^ui\.save\.rename/);
    options.action.run();
    await settle();
    assert.deepEqual(calls.renamed, ["N1"]);
    // once after the save, once more before the name field opens
    assert.deepEqual(calls.history, ["refresh", "refresh"]);
  });

  test("Mod+S on a step that is already a version says so with that version's time", async () => {
    const { registry, calls } = setup({ save_checkpoint: saved("already") });
    registry.run("app.save", null, { project: {} });
    await settle();
    assert.equal(calls.toasts.length, 1);
    assert.equal(calls.toasts[0][0], 'ui.save.already{"time":"09.05"}');
    assert.equal(calls.toasts[0][1].action, undefined);
  });

  test("Shift+Mod+S asks for a name, suggesting the time one, and saves it as a version", async () => {
    const { registry, calls } = setup({}, { asked: "Before the interview" });
    registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(calls.asked, ['ui.save.checkpoint_name{"time":"09.05"}']);
    assert.deepEqual(calls.commands, [
      ["save_checkpoint", { name: "Before the interview", rename: true }],
    ]);
    assert.match(calls.toasts[0][0], /^ui\.save\.version_made.*Before the interview/);
  });

  test("Shift+Mod+S cancelled in the dialog does nothing", async () => {
    const { registry, calls } = setup({}, { asked: null });
    registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(calls.commands, []);
    assert.deepEqual(calls.toasts, []);
    assert.deepEqual(calls.left, []);
  });

  test("Shift+Mod+S on a saved step: a new name says it renamed, the same name says already", async () => {
    const renamed = setup({ save_checkpoint: saved("renamed", "Final") });
    renamed.registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.equal(renamed.calls.toasts[0][0], 'ui.save.version_renamed{"name":"Final"}');
    const same = setup({ save_checkpoint: saved("already", "Final") });
    same.registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.equal(same.calls.toasts[0][0], 'ui.save.already{"time":"09.05"}');
  });

  test("a save also records where the user left off; a failed one does not", async () => {
    const ok = setup();
    ok.registry.run("app.save", null, { project: {} });
    ok.registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(ok.calls.left, ["mark", "mark"]);
    const failed = setup({ save_checkpoint: null });
    failed.registry.run("app.save", null, { project: {} });
    failed.registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(failed.calls.left, []);
  });

  test("a failed command shows no success notice", async () => {
    const { registry, calls } = setup({ save_checkpoint: null });
    registry.run("app.save", null, { project: {} });
    await settle();
    assert.deepEqual(calls.toasts, []);
  });

  test("Back up now makes the backup copy and says so", async () => {
    const { registry, calls } = setup();
    registry.run("app.backup_now", null, { project: {} });
    await settle();
    assert.deepEqual(calls.commands, [["save_backup", {}]]);
    assert.match(calls.toasts[0][0], /^ui\.backup\.done/);
  });

  test("a failed backup shows no success notice", async () => {
    const { registry, calls } = setup({ save_backup: null });
    registry.run("app.backup_now", null, { project: {} });
    await settle();
    assert.deepEqual(calls.toasts, []);
  });

  test("Open earlier version opens History at the saved versions", async () => {
    const { registry, calls } = setup();
    registry.run("app.open_earlier_version", null, { project: {} });
    await settle();
    assert.deepEqual(calls.history, ["open_saved"]);
  });
});
