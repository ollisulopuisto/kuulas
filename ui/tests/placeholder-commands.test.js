import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { registerPlaceholderCommands } from "../placeholder-commands.js";

const project = (placeholders = []) => ({
  rate: 48000,
  tracks: [{ id: "t1" }, { id: "t2" }],
  placeholders,
});

function setup(initial, answer = "Hello there") {
  let state = { playhead: 4800, focusTrack: "t2", placeholderSelected: null, ...initial };
  const registry = createRegistry();
  const calls = { edits: [], toasts: [], patches: [], prompts: [], takes: [], downloads: [] };
  registerPlaceholderCommands(registry, {
    t: (key, values = {}) => `${key}${Object.keys(values).length ? JSON.stringify(values) : ""}`,
    makeId: () => "hNEW",
    app: {
      getState: () => state,
      patch: (patch) => {
        calls.patches.push(patch);
        state = { ...state, ...patch };
      },
      edit: (change) => {
        calls.edits.push(change);
        change.done?.({});
      },
      toast: (text, options) => calls.toasts.push([text, options]),
      promptText: async (request) => {
        calls.prompts.push(request);
        return answer;
      },
      takeFor: (id) => calls.takes.push(id),
      download: async (path, file) => {
        calls.downloads.push([path, file]);
        return file;
      },
    },
  });
  return { registry, calls, get: () => state };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

describe("placeholder.add", () => {
  test("asks for the text, adds it at the play cursor on the current track, selects it", async () => {
    const { registry, calls, get } = setup({ project: project() });
    assert.equal(registry.run("placeholder.add", null, get()), true);
    await tick();
    assert.deepEqual(calls.prompts, [{ text: "", rate: 48000 }]);
    assert.equal(calls.edits[0].op, "add_placeholder");
    assert.deepEqual(calls.edits[0].args, {
      track_id: "t2",
      start: 4800,
      text: "Hello there",
      placeholder_id: "hNEW",
    });
    assert.deepEqual(calls.patches.at(-1), { placeholderSelected: "hNEW" });
    assert.equal(calls.toasts[0][1].undo, true);
  });

  test("a cancelled or blank prompt adds nothing", async () => {
    for (const answer of [null, "   "]) {
      const { registry, calls, get } = setup({ project: project() }, answer);
      registry.run("placeholder.add", null, get());
      await tick();
      assert.equal(calls.edits.length, 0);
    }
  });

  test("not without a project or a track", () => {
    const { registry } = setup({});
    assert.equal(registry.can("placeholder.add", {}), false);
    assert.equal(registry.can("placeholder.add", { project: { tracks: [] } }), false);
  });
});

describe("edit, take and delete need a selected placeholder", () => {
  const ph = { id: "h1", track: "t1", start: 0, length: 100, text: "Old text" };
  const state = { project: project([ph]), placeholderSelected: "h1" };

  test("unavailable without a selection", () => {
    const { registry } = setup({ project: project([ph]) });
    for (const id of ["placeholder.edit", "placeholder.take", "placeholder.delete"])
      assert.equal(registry.can(id, { project: project([ph]) }), false, id);
  });

  test("edit prompts with the current text and sends the new one", async () => {
    const { registry, calls, get } = setup(state, "New text");
    registry.run("placeholder.edit", null, get());
    await tick();
    assert.equal(calls.prompts[0].text, "Old text");
    assert.deepEqual(calls.edits[0].args, { placeholder_id: "h1", text: "New text" });
  });

  test("edit with unchanged text sends nothing", async () => {
    const { registry, calls, get } = setup(state, "Old text");
    registry.run("placeholder.edit", null, get());
    await tick();
    assert.equal(calls.edits.length, 0);
  });

  test("take hands the id to the app", () => {
    const { registry, calls, get } = setup(state);
    registry.run("placeholder.take", null, get());
    assert.deepEqual(calls.takes, ["h1"]);
  });

  test("delete removes it, clears the selection, toasts with Undo", () => {
    const { registry, calls, get } = setup(state);
    registry.run("placeholder.delete", null, get());
    assert.equal(calls.edits[0].op, "delete_placeholder");
    assert.deepEqual(calls.patches.at(-1), { placeholderSelected: null });
    assert.equal(calls.toasts[0][1].undo, true);
  });
});

describe("script export", () => {
  test("two downloads, only when there is a placeholder", async () => {
    const withOne = setup({ project: project([{ id: "h1", track: "t1" }]) });
    assert.equal(withOne.registry.can("export.narration_script_txt", withOne.get()), true);
    withOne.registry.run("export.narration_script_md", null, withOne.get());
    await tick();
    assert.deepEqual(withOne.calls.downloads, [
      ["/api/narration-script?format=md", "narration-script.md"],
    ]);
    const none = setup({ project: project() });
    assert.equal(none.registry.can("export.narration_script_txt", none.get()), false);
  });
});
