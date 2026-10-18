import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { clockTime, registerSaveCommands } from "../save-commands.js";

function setup(answers = {}) {
  const registry = createRegistry();
  const calls = { commands: [], toasts: [], left: [] };
  registerSaveCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    app: {
      toast: (text, options) => calls.toasts.push([text, options]),
      command: async (name, args) => {
        calls.commands.push([name, args]);
        return name in answers ? answers[name] : {};
      },
      clock: () => new Date(2026, 9, 18, 9, 5),
      markLeftOff: () => calls.left.push("mark"),
    },
  });
  return { registry, calls };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

describe("save commands", () => {
  test("the clock time is HH.MM, zero padded", () => {
    assert.equal(clockTime(new Date(2026, 9, 18, 9, 5)), "09.05");
  });

  test("both are ready, and need a project", () => {
    const { registry } = setup();
    for (const id of ["app.save", "app.save_named"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.can(id, {}), false, id);
      assert.equal(registry.can(id, { project: {} }), true, id);
    }
  });

  test("Mod+S asks for a backup and says so", async () => {
    const { registry, calls } = setup();
    registry.run("app.save", null, { project: {} });
    await settle();
    assert.deepEqual(calls.commands, [["save_backup", {}]]);
    assert.match(calls.toasts[0][0], /^ui\.save\.done/);
    assert.deepEqual(calls.toasts[0][1], { undo: false });
  });

  test("Shift+Mod+S names a checkpoint Saved HH.MM and the notice carries the name", async () => {
    const { registry, calls } = setup();
    registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(calls.commands, [
      ["save_checkpoint", { name: 'ui.save.checkpoint_name{"time":"09.05"}' }],
    ]);
    assert.match(calls.toasts[0][0], /^ui\.save\.named.*checkpoint_name/);
  });

  test("a save also records where the user left off; a failed one does not", async () => {
    const ok = setup();
    ok.registry.run("app.save", null, { project: {} });
    ok.registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(ok.calls.left, ["mark", "mark"]);
    const failed = setup({ save_backup: null, save_checkpoint: null });
    failed.registry.run("app.save", null, { project: {} });
    failed.registry.run("app.save_named", null, { project: {} });
    await settle();
    assert.deepEqual(failed.calls.left, []);
  });

  test("a failed command shows no success notice", async () => {
    const { registry, calls } = setup({ save_backup: null });
    registry.run("app.save", null, { project: {} });
    await settle();
    assert.deepEqual(calls.toasts, []);
  });
});
