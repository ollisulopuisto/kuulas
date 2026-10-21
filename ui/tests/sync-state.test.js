import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { createKeymap } from "../keys.js";
import {
  badgeFor,
  driftingAmong,
  driftRows,
  formatOffset,
  stepDrift,
  syncIndex,
} from "../sync-state.js";

const RATE = 48000;
const row = (clip_id, start, offset, state = "drift") => ({
  clip_id,
  track_id: "t",
  start,
  offset,
  state,
});

describe("formatOffset", () => {
  test("milliseconds under a second, seconds above, with a sign", () => {
    assert.equal(formatOffset(14400, RATE), "+300 ms");
    assert.equal(formatOffset(-57600, RATE), "-1.2 s");
    assert.equal(formatOffset(-480, RATE), "-10 ms");
    assert.equal(formatOffset(0, RATE), "+0 ms");
  });
  test("the number format is the language's", () => {
    assert.equal(
      formatOffset(-57600, RATE, (n) => String(n).replace(".", ",")),
      "-1,2 s",
    );
  });
});

describe("what a clip wears", () => {
  const index = syncIndex([row("a", 0, 14400), row("b", 5, 4800, "free"), row("c", 9, 0, "free")]);
  test("drift: a red badge with the offset", () => {
    assert.deepEqual(badgeFor(index.get("a")), { kind: "drift", offset: 14400 });
  });
  test("free: the grey icon with its offset, also when it is zero", () => {
    assert.deepEqual(badgeFor(index.get("b")), { kind: "free", offset: 4800 });
    assert.deepEqual(badgeFor(index.get("c")), { kind: "free", offset: 0 });
  });
  test("in sync: nothing", () => {
    assert.equal(badgeFor(index.get("nobody")), null);
    assert.equal(badgeFor(undefined), null);
  });
});

describe("the drift list", () => {
  const clips = [row("late", 900, 5), row("free", 100, 9, "free"), row("early", 100, -3)];
  test("only undecided drifts, in timeline order", () => {
    assert.deepEqual(
      driftRows(clips).map((r) => r.clip_id),
      ["early", "late"],
    );
  });
  test("] goes to the next one after the cursor and wraps; [ the previous one", () => {
    const rows = driftRows(clips);
    assert.equal(stepDrift(rows, 0, 1).clip_id, "early");
    assert.equal(stepDrift(rows, 100, 1).clip_id, "late");
    assert.equal(stepDrift(rows, 900, 1).clip_id, "early");
    assert.equal(stepDrift(rows, 900, -1).clip_id, "early");
    assert.equal(stepDrift(rows, 100, -1).clip_id, "late");
    assert.equal(stepDrift([], 0, 1), null);
  });
  test("after a move, only the clips that drifted are asked about", () => {
    assert.deepEqual(driftingAmong(clips, ["late", "free", "gone"]), ["late"]);
  });
});

const flush = () => new Promise((resolve) => setImmediate(resolve));

describe("the sync commands", () => {
  async function setup(initial) {
    const { registerSyncCommands } = await import("../sync-commands.js");
    let state = {
      project: { tracks: [{ id: "t", clips: [{ id: "a" }, { id: "b", free: true }] }] },
      selection: new Set(["a"]),
      playhead: 0,
      syncClips: [],
      ...initial,
    };
    const registry = createRegistry();
    const calls = { edits: [], toasts: [], jumps: [], server: [], patches: [], asked: [] };
    registerSyncCommands(registry, {
      t: (key, values = {}) => `${key}${values.count === undefined ? "" : `:${values.count}`}`,
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
        jump: (frame) => calls.jumps.push(frame),
        syncCommand: (name, args) => {
          calls.server.push([name, args]);
          return Promise.resolve();
        },
        syncPreview: async () => ({ kind: "move", count: 1, moves: [{}] }),
        confirmSync: async (preview) => {
          calls.asked.push(preview);
          return true;
        },
        confirmEnabled: () => true,
        notice: () => {},
      },
    });
    return { registry, calls, get: () => state };
  }

  test("U frees the selection, and links it again when all of it is free", async () => {
    const { registry, calls, get } = await setup({});
    registry.run("sync.free", null, get());
    assert.deepEqual(calls.edits[0].args, { clip_ids: ["a"], free: true });
    assert.equal(calls.edits[0].label, "ui.sync.history.free");
    assert.deepEqual(calls.toasts[0], ["ui.sync.toast.freed:1", { undo: true }]);
    const second = await setup({ selection: new Set(["b"]) });
    second.registry.run("sync.free", null, second.get());
    assert.deepEqual(second.calls.edits[0].args, { clip_ids: ["b"], free: false });
    assert.equal(second.calls.edits[0].label, "ui.sync.history.link");
  });

  test("U needs a selection", async () => {
    const { registry, get } = await setup({ selection: new Set() });
    assert.equal(registry.can("sync.free", get()), false);
  });

  test("R resyncs the selection, Shift+Alt+Mod+R everything from the cursor on", async () => {
    const { registry, calls, get } = await setup({ playhead: 4800 });
    registry.run("sync.resync", null, get());
    registry.run("sync.resync_end", null, get());
    await flush();
    assert.deepEqual(calls.server, [
      ["resync", { clip_ids: ["a"] }],
      ["resync_from", { frame: 4800 }],
    ]);
  });

  test("Resync all and Free all work on the drift list, and are off when it is empty", async () => {
    const empty = await setup({});
    assert.equal(empty.registry.can("sync.resync_all", empty.get()), false);
    assert.equal(empty.registry.can("sync.free_all", empty.get()), false);
    const { registry, calls, get } = await setup({
      syncClips: [row("a", 0, 5), row("b", 9, 7, "free"), row("c", 20, 1)],
    });
    registry.run("sync.resync_all", null, get());
    await flush();
    assert.deepEqual(calls.server, [["resync", { clip_ids: ["a", "c"] }]]);
    registry.run("sync.free_all", null, get());
    assert.deepEqual(calls.edits[0].args, { clip_ids: ["a", "c"], free: true });
  });

  test("F7 and Shift+F7 select and show the next and previous drifting clip", async () => {
    const { registry, calls, get } = await setup({
      playhead: 10,
      syncClips: [row("a", 0, 5), row("c", 20, 1)],
    });
    registry.run("sync.drift_next", null, get());
    assert.deepEqual(calls.jumps, [20]);
    assert.deepEqual([...get().selection], ["c"]);
    registry.run("sync.drift_previous", null, get());
    assert.deepEqual(calls.jumps, [20, 0]);
    assert.deepEqual([...get().selection], ["a"]);
  });
});

describe("F7 and Shift+F7 in the keymap", () => {
  function keyboard(context) {
    const calls = [];
    const registry = createRegistry();
    for (const entry of DEFAULT_KEYMAP) registry.register(entry.id, () => calls.push(entry.id));
    const keymap = createKeymap({ platform: "other", getContext: () => context, registry });
    keymap.setEntries(resolveKeymap(DEFAULT_KEYMAP, {}, "other"));
    const press = (key, shiftKey = false) =>
      keymap.handle({
        key,
        code: key.toUpperCase() === "F7" ? "F7" : `Key${key.toUpperCase()}`,
        shiftKey,
        altKey: false,
        ctrlKey: false,
        metaKey: false,
        repeat: false,
        target: { tagName: "DIV" },
        preventDefault() {},
        getModifierState: () => false,
      });
    return { calls, press };
  }
  test("in the Markers tab they step the drift list; the bracket keys do nothing", () => {
    const markers = keyboard("markers");
    markers.press("F7");
    markers.press("F7", true);
    assert.deepEqual(markers.calls, ["sync.drift_next", "sync.drift_previous"]);
    const timeline = keyboard("timeline");
    timeline.press("[");
    timeline.press("]");
    assert.deepEqual(timeline.calls, []);
  });
});
