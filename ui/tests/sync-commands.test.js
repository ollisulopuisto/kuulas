import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { registerSyncCommands } from "../sync-commands.js";
import { anchorIds, anchorNameFor, homeNameFor } from "../sync-state.js";

const project = {
  sync_groups: [{ id: "g", main: "mz", members: { mz: 0, ma: 0, mv: 0 } }],
  tracks: [
    { id: "t1", name: "Anna", clips: [{ id: "ca", media: "ma", home: "t2" }] },
    { id: "t2", name: "Ville", clips: [{ id: "cv", media: "mv" }] },
    { id: "t3", name: "Zoom", clips: [{ id: "cz", media: "mz" }] },
  ],
};
const anchors = [{ clip_id: "cz", track_id: "t3", name: "Zoom", group: "g" }];

function setup(selection) {
  const registry = createRegistry();
  const calls = { edits: [], syncs: [], toasts: [], previews: [], asked: [], notices: [] };
  const config = { preview: { kind: "move", count: 1, moves: [{}] }, answer: true, confirm: true };
  const state = { project, selection: new Set(selection), syncClips: [], playhead: 0 };
  registerSyncCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    app: {
      getState: () => state,
      patch: () => {},
      seek: () => {},
      edit: (change) => {
        calls.edits.push(change);
        change.done?.();
      },
      toast: (text, options) => calls.toasts.push([text, options]),
      syncCommand: (name, args) => calls.syncs.push([name, args]),
      syncPreview: async (name, args) => {
        calls.previews.push([name, args]);
        return config.preview;
      },
      confirmSync: async (preview) => {
        calls.asked.push(preview);
        return config.answer;
      },
      confirmEnabled: () => config.confirm,
      notice: (text) => calls.notices.push(text),
    },
  });
  return { registry, calls, state, config };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

describe("anchor commands", () => {
  test("make this the anchor works on a clip that is not the anchor", () => {
    const { registry, calls, state } = setup(["ca"]);
    assert.equal(registry.can("sync.set_anchor", state), true);
    registry.run("sync.set_anchor", null, state);
    assert.equal(calls.edits[0].op, "set_sync_anchor");
    assert.deepEqual(calls.edits[0].args, { clip_id: "ca" });
    assert.match(calls.toasts[0][0], /^ui\.sync\.toast\.anchor.*Anna/);
  });

  test("it is unavailable on the anchor itself, with nothing selected, and outside a group", () => {
    const anchor = setup(["cz"]);
    assert.equal(anchor.registry.can("sync.set_anchor", anchor.state), false);
    const none = setup([]);
    assert.equal(none.registry.can("sync.set_anchor", none.state), false);
    const loose = setup(["ca"]);
    loose.state.project = { ...project, sync_groups: [] };
    assert.equal(loose.registry.can("sync.set_anchor", loose.state), false);
  });

  test("Y marks the selection in sync with the first selected clip as the anchor", () => {
    const { registry, calls, state } = setup(["cv", "ca"]);
    registry.run("sync.mark", null, state);
    assert.deepEqual(calls.edits[0].args, {
      clip_ids: ["cv", "ca"],
      main: "cv",
      basis: "timeline",
    });
    assert.match(calls.toasts[0][0], /^ui\.sync\.toast\.marked.*Ville/);
    const one = setup(["cv"]);
    assert.equal(one.registry.can("sync.mark", one.state), false);
  });

  test("sync selected clips to the anchor asks the server to resync the selection", async () => {
    const { registry, calls, state } = setup(["ca"]);
    registry.run("sync.resync", null, state);
    await flush();
    assert.deepEqual(calls.syncs, [["resync", { clip_ids: ["ca"] }]]);
  });

  test("put back on the original track works on the clips that were moved", async () => {
    const { registry, calls, state } = setup(["ca"]);
    assert.equal(registry.can("sync.send_home", state), true);
    registry.run("sync.send_home", null, state);
    await flush();
    assert.equal(calls.edits[0].op, "send_home");
    assert.deepEqual(calls.edits[0].args, { clip_ids: ["ca"] });
    const never = setup(["cv"]);
    assert.equal(never.registry.can("sync.send_home", never.state), false);
  });
});

describe("keys", () => {
  test("the new commands have keys and a context", () => {
    const find = (id) => DEFAULT_KEYMAP.find((entry) => entry.id === id);
    assert.equal(find("sync.set_anchor").keys.other, "Shift+Y");
    assert.equal(find("sync.send_home").keys.other, "Shift+U");
    assert.equal(find("sync.set_anchor").context, "timeline");
  });
});

describe("the anchor and the home track on the screen", () => {
  test("anchorIds is the set of anchor clips", () => {
    assert.deepEqual([...anchorIds(anchors)], ["cz"]);
    assert.deepEqual([...anchorIds(undefined)], []);
  });

  test("anchorNameFor names the anchor of the clip's group", () => {
    assert.equal(anchorNameFor(project, anchors, project.tracks[0].clips[0]), "Zoom");
    assert.equal(anchorNameFor(project, anchors, { id: "x", media: "other" }), "");
  });

  test("homeNameFor names the track a clip was moved from, only while it is elsewhere", () => {
    const moved = project.tracks[0].clips[0];
    assert.equal(homeNameFor(project, moved, "t1"), "Ville");
    assert.equal(homeNameFor(project, moved, "t2"), "");
    assert.equal(homeNameFor(project, project.tracks[1].clips[0], "t2"), "");
    assert.equal(homeNameFor(project, { id: "q", home: "gone" }, "t1"), "");
  });
});

describe("sync asks first (owner, 2026-10-19)", () => {
  const moving = [
    ["sync.resync", ["ca"], "resync", { clip_ids: ["ca"] }],
    ["sync.resync_end", ["ca"], "resync_from", { frame: 0 }],
    ["sync.send_home", ["ca"], "send_home", { clip_ids: ["ca"] }],
  ];

  for (const [id, selection, name, args] of moving) {
    test(`${id} previews, asks, then does it`, async () => {
      const { registry, calls, state } = setup(selection);
      registry.run(id, null, state);
      await flush();
      assert.deepEqual(calls.previews, [[name, args]]);
      assert.equal(calls.asked.length, 1);
      assert.equal(calls.syncs.length + calls.edits.length, 1);
    });

    test(`${id} does nothing when the dialog is cancelled`, async () => {
      const { registry, calls, state, config } = setup(selection);
      config.answer = false;
      registry.run(id, null, state);
      await flush();
      assert.equal(calls.asked.length, 1);
      assert.deepEqual([calls.syncs, calls.edits, calls.toasts], [[], [], []]);
    });

    test(`${id} says so and opens no dialog when nothing would move`, async () => {
      const { registry, calls, state, config } = setup(selection);
      config.preview = { kind: "nothing", message: "already in sync", moves: [] };
      registry.run(id, null, state);
      await flush();
      assert.deepEqual(calls.notices, ["already in sync"]);
      assert.deepEqual([calls.asked, calls.syncs, calls.edits], [[], [], []]);
    });

    test(`${id} goes straight through when "Confirm before re-syncing" is off`, async () => {
      const { registry, calls, state, config } = setup(selection);
      config.confirm = false;
      registry.run(id, null, state);
      await flush();
      assert.equal(calls.asked.length, 0);
      assert.equal(calls.syncs.length + calls.edits.length, 1);
    });
  }

  test("re-sync all previews the drift list", async () => {
    const { registry, calls, state } = setup([]);
    state.syncClips = [{ clip_id: "ca", state: "drift", start: 0, offset: 5 }];
    registry.run("sync.resync_all", null, state);
    await flush();
    assert.deepEqual(calls.previews, [["resync", { clip_ids: ["ca"] }]]);
    assert.equal(calls.asked.length, 1);
    assert.deepEqual(calls.syncs, [["resync", { clip_ids: ["ca"] }]]);
  });

  test("freeing never asks: nothing moves", async () => {
    const { registry, calls, state } = setup(["ca"]);
    state.syncClips = [{ clip_id: "ca", state: "drift", start: 0, offset: 5 }];
    registry.run("sync.free", null, state);
    registry.run("sync.free_all", null, state);
    await flush();
    assert.deepEqual([calls.previews, calls.asked], [[], []]);
    assert.equal(calls.edits.length, 2);
  });
});
