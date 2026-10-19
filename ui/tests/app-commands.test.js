import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { prerollStart, registerAppCommands, seekOffsets, stepTrack } from "../app-commands.js";
import { createRegistry } from "../commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";

const project = { rate: 48000, tracks: [{ id: "a" }, { id: "b" }, { id: "c" }] };

describe("track stepping", () => {
  test("moves to the next or previous track and stops at the ends", () => {
    assert.equal(stepTrack(project, "a", 1), "b");
    assert.equal(stepTrack(project, "b", -1), "a");
    assert.equal(stepTrack(project, "a", -1), "a");
    assert.equal(stepTrack(project, "c", 1), "c");
  });
  test("with no focus Down picks the first and Up the last; no project, nothing", () => {
    assert.equal(stepTrack(project, null, 1), "a");
    assert.equal(stepTrack(project, null, -1), "c");
    assert.equal(stepTrack(null, null, 1), null);
    assert.equal(stepTrack({ tracks: [] }, null, 1), null);
  });
});

describe("seek offsets", () => {
  test("nudge is 4 screen pixels, Shift 1 s, Alt 10 ms, in frames", () => {
    assert.deepEqual(seekOffsets(48000, 20), { nudge: 80, near: 48000, fine: 480 });
    assert.equal(seekOffsets(48000, 0.25).nudge, 1);
  });
  test("the nudge is at least one frame, whole frames, and tolerates a missing zoom", () => {
    assert.equal(seekOffsets(48000, 0.01).nudge, 1);
    assert.equal(seekOffsets(48000, 2.6).nudge, 10);
    assert.equal(seekOffsets(48000).nudge, 4);
    assert.equal(seekOffsets(48000, Number.NaN).nudge, 4);
  });
});

describe("play from a few seconds before the playhead", () => {
  test("starts 3 s back by default and never before the start", () => {
    assert.equal(prerollStart(480000, 48000), 336000);
    assert.equal(prerollStart(100000, 48000), 0);
    assert.equal(prerollStart(0, 48000), 0);
  });
  test("the length can be given", () => {
    assert.equal(prerollStart(480000, 48000, 5), 240000);
  });
});

describe("the commands the app registers", () => {
  function setup(state = {}) {
    const calls = [];
    const registry = createRegistry();
    const actions = new Proxy(
      {},
      {
        get:
          (_t, name) =>
          (...a) =>
            calls.push([name, ...a]),
      },
    );
    const app = {
      undo: () => calls.push(["undo"]),
      redo: () => calls.push(["redo"]),
      chooseMedia: () => calls.push(["import"]),
      focusName: () => calls.push(["rename"]),
      seek: (frame) => calls.push(["seek", frame]),
      totalFrames: () => 480000,
      patch: (p) => calls.push(["patch", p]),
      getState: () => state,
      openPalette: () => calls.push(["palette"]),
      openKeys: () => calls.push(["keys"]),
      openHelp: () => calls.push(["help"]),
      openSearch: () => calls.push(["openSearch"]),
      importKeys: () => calls.push(["importKeys"]),
      exportKeys: () => calls.push(["exportKeys"]),
      resetKeys: () => calls.push(["resetKeys"]),
      restoreStep: () => calls.push(["restoreStep"]),
      openHistory: () => calls.push(["openHistory"]),
      closeProject: () => calls.push(["closeProject"]),
      openPreferences: () => calls.push(["openPreferences"]),
      minimise: () => calls.push(["minimise"]),
      openRecent: (path) => calls.push(["openRecent", path]),
      clearRecent: () => calls.push(["clearRecent"]),
      openStatistics: () => calls.push(["openStatistics"]),
      openLocateMedia: () => calls.push(["openLocateMedia"]),
      openSendCopy: () => calls.push(["openSendCopy"]),
      newProject: () => calls.push(["newProject"]),
      openProject: () => calls.push(["openProject"]),
      autoSilence: () => calls.push(["autoSilence"]),
      duckMicrophones: () => calls.push(["duckMicrophones"]),
      transcribeTrack: () => calls.push(["transcribeTrack"]),
    };
    registerAppCommands(registry, { actions, app });
    return { registry, calls };
  }

  test("every registered id is in the keymap data", () => {
    const { registry } = setup();
    const ids = new Set(DEFAULT_KEYMAP.map((e) => e.id));
    for (const id of registry.ids()) assert.ok(ids.has(id), id);
  });

  test("Track > Auto-Silence, Duck the microphones and Transcribe work with a project (they were inert)", () => {
    const { registry, calls } = setup();
    const withProject = { project: { tracks: [{ id: "a" }] } };
    const ids = ["app.auto_silence", "app.automix", "app.transcribe"];
    for (const id of ids) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.can(id, withProject), true, id);
      assert.equal(registry.can(id, {}), false, id);
    }
    for (const id of ids) registry.run(id, null, withProject);
    assert.deepEqual(
      calls.map((call) => call[0]),
      ["autoSilence", "duckMicrophones", "transcribeTrack"],
    );
  });

  test("File > New project… and Open project… need no project and ask the app", () => {
    const { registry, calls } = setup();
    for (const id of ["app.new", "app.open"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.hintKey(id), `cmd.${id}.hint`, id);
      assert.equal(registry.can(id, {}), true, id);
    }
    registry.run("app.new", null, {});
    registry.run("app.open", null, {});
    assert.deepEqual(calls, [["newProject"], ["openProject"]]);
  });

  test("Close project needs a project; Preferences and Minimise need none", () => {
    const { registry, calls } = setup();
    const withProject = { project: { tracks: [] } };
    assert.equal(registry.can("app.close_project", {}), false);
    assert.equal(registry.can("app.close_project", withProject), true);
    for (const id of ["app.close_project", "app.preferences", "app.minimise"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.hintKey(id), `cmd.${id}.hint`, id);
    }
    registry.run("app.close_project", null, withProject);
    registry.run("app.preferences", null, {});
    registry.run("app.minimise", null, {});
    assert.deepEqual(calls, [["closeProject"], ["openPreferences"], ["minimise"]]);
  });

  test("Open Recent opens the path it is given; Clear menu empties the list", () => {
    const { registry, calls } = setup();
    const none = { recentProjects: [] };
    const some = { recentProjects: [{ path: "/p/A.kuulas" }] };
    assert.equal(registry.can("app.clear_recent", none), false);
    assert.equal(registry.can("app.clear_recent", some), true);
    registry.run("app.open", "/p/A.kuulas", some); // an Open Recent entry
    registry.run("app.open", { type: "keydown" }, some); // the key: the dialog
    registry.run("app.clear_recent", null, some);
    assert.deepEqual(calls, [["openRecent", "/p/A.kuulas"], ["openProject"], ["clearRecent"]]);
  });

  test("undo and redo can only apply when there is something to undo or redo", () => {
    const { registry } = setup();
    assert.equal(registry.can("edit.undo", { canUndo: false }), false);
    assert.equal(registry.can("edit.undo", { canUndo: true }), true);
    assert.equal(registry.can("edit.redo", { canRedo: false }), false);
  });

  test("history.restore runs in the History panel on a pick that is not the head", () => {
    const { registry, calls } = setup();
    const state = { panel: "history", head: "b", historySelected: "a" };
    assert.equal(registry.can("history.restore", { ...state, panel: "timeline" }), false);
    assert.equal(registry.can("history.restore", { ...state, historySelected: "b" }), false);
    assert.equal(registry.run("history.restore", null, state), true);
    assert.equal(registry.run("history.open", null, {}), true);
    assert.deepEqual(calls, [["restoreStep"], ["openHistory"]]);
  });

  test("Statistics opens its dialog once a project is open (WP70)", () => {
    const { registry, calls } = setup();
    assert.equal(registry.can("app.statistics", {}), false);
    assert.equal(registry.can("app.statistics", { project }), true);
    assert.equal(registry.run("app.statistics", null, { project }), true);
    assert.deepEqual(calls, [["openStatistics"]]);
  });

  test("Locate media… and Send a copy… open their dialogs once a project is open (WP39, WP32)", () => {
    const { registry, calls } = setup();
    for (const id of ["app.locate_media", "app.send_copy"]) {
      assert.equal(registry.can(id, {}), false, id);
      assert.equal(registry.can(id, { project }), true, id);
      assert.equal(registry.run(id, null, { project }), true, id);
    }
    assert.deepEqual(calls, [["openLocateMedia"], ["openSendCopy"]]);
  });

  test("Tab and Shift+Tab step to the next and previous stop, Alt+Tab cycles the scope", () => {
    const { registry, calls } = setup({ project });
    const state = { project };
    for (const id of ["nav.next_stop", "transcript.next_stop"]) registry.run(id, null, state);
    for (const id of ["nav.prev_stop", "transcript.prev_stop"]) registry.run(id, null, state);
    registry.run("nav.tab_target_cycle", null, state);
    assert.deepEqual(calls, [
      ["tabStop", 1],
      ["tabStop", 1],
      ["tabStop", -1],
      ["tabStop", -1],
      ["cycleTabScope"],
    ]);
    assert.equal(registry.can("nav.next_stop", {}), false);
  });

  test("clearing the in and out points", () => {
    const { registry, calls } = setup({ project });
    assert.equal(registry.run("mark.clear_in", null, { project }), true);
    assert.equal(registry.run("mark.clear_out", null, { project }), true);
    assert.equal(registry.run("mark.clear", null, { project }), true);
    assert.deepEqual(calls, [
      ["patch", { inPoint: null, rangeTracks: new Set() }],
      ["patch", { outPoint: null, rangeTracks: new Set() }],
      ["patch", { inPoint: null, outPoint: null, rangeTracks: new Set() }],
    ]);
    assert.equal(registry.can("mark.clear", {}), false);
  });

  test("0 shows the whole edit and F fits the selection", () => {
    const { registry, calls } = setup({ project });
    registry.run("view.fit", null, { project });
    registry.run("view.fit_selection", null, { project });
    assert.deepEqual(calls, [["fitView"], ["fitSelection"]]);
  });

  test("the four pause-break choices call setPauseBreak and need no project", () => {
    const { registry, calls } = setup({});
    for (const id of ["1_5", "3", "6", "never"]) {
      assert.equal(registry.run(`view.pause_${id}`, null, {}), true);
    }
    assert.deepEqual(calls, [
      ["setPauseBreak", "1_5"],
      ["setPauseBreak", "3"],
      ["setPauseBreak", "6"],
      ["setPauseBreak", "never"],
    ]);
  });

  test("fit tracks and auto-fit need a project and call the actions", () => {
    const { registry, calls } = setup({ project });
    assert.equal(registry.can("view.fit_tracks", {}), false);
    assert.equal(registry.can("view.auto_fit_tracks", {}), false);
    registry.run("view.fit_tracks", null, { project });
    registry.run("view.auto_fit_tracks", null, { project });
    assert.deepEqual(calls, [["fitTracks"], ["toggleAutoFitTracks"]]);
  });

  test("P plays from the pre-roll before the playhead and needs a project", () => {
    const { registry, calls } = setup({ project, playhead: 480000 });
    assert.equal(registry.can("transport.play_before", { project }), true);
    assert.equal(registry.can("transport.play_before", {}), false);
    assert.equal(registry.run("transport.play_before", null, { project, playhead: 480000 }), true);
    assert.deepEqual(calls, [["playFrom", 336000]]);
  });

  test("the loop toggle needs a range to loop, or the loop already on", () => {
    const { registry, calls } = setup({ project });
    const idle = { project, loop: false, inPoint: null, outPoint: null, selection: new Set() };
    assert.equal(registry.can("transport.loop", idle), false);
    assert.equal(registry.can("transport.loop", { ...idle, inPoint: 10, outPoint: 90 }), true);
    assert.equal(registry.can("transport.loop", { ...idle, loop: true }), true);
    assert.equal(registry.can("transport.loop", {}), false);
    registry.run("transport.loop", null, { ...idle, inPoint: 10, outPoint: 90 });
    assert.deepEqual(calls, [["toggleLoop"]]);
  });

  test("nav.to_resume goes to the left-off position, and needs one", () => {
    const state = { project, playhead: 5, leftOff: { frame: 96000, savedAt: null } };
    const { registry, calls } = setup(state);
    assert.equal(registry.can("nav.to_resume", {}), false);
    assert.equal(registry.can("nav.to_resume", { project, leftOff: null }), false);
    assert.equal(registry.can("nav.to_resume", state), true);
    registry.run("nav.to_resume");
    assert.deepEqual(calls, [["seek", 96000]]);
  });

  test("the playhead commands need a project and move by the right amount", () => {
    const state = { project, playhead: 100000, zoom: 20 };
    const { registry, calls } = setup(state);
    assert.equal(registry.can("nav.start", {}), false);
    assert.equal(registry.can("nav.start", state), true);
    registry.run("nav.start");
    registry.run("nav.end");
    registry.run("nav.forward"); // 4 pixels at 20 frames per pixel
    registry.run("nav.back_far"); // Shift: 1 s
    registry.run("nav.back_fine"); // Alt: 10 ms
    assert.deepEqual(calls, [
      ["seek", 0],
      ["seek", 480000],
      ["seek", 100080],
      ["seek", 52000],
      ["seek", 99520],
    ]);
  });

  test("seeking never goes before zero or past the end", () => {
    const { registry, calls } = setup({ project, playhead: 10, zoom: 20 });
    registry.run("nav.back");
    assert.deepEqual(calls, [["seek", 0]]);
  });

  test("track.next focuses the next track and clears a focused bus", () => {
    const { registry, calls } = setup({ project, focusTrack: "a" });
    registry.run("track.next");
    assert.deepEqual(calls, [
      ["patch", { focusTrack: "b", focusBus: null, rangeTracks: new Set() }],
    ]);
  });

  test("the shuttle commands press J, K and L and need a project", () => {
    const state = { project };
    const { registry, calls } = setup(state);
    assert.equal(registry.can("transport.shuttle_forward", {}), false);
    assert.equal(registry.can("transport.shuttle_forward", state), true);
    registry.run("transport.shuttle_back", null, state);
    registry.run("transport.shuttle_stop", null, state);
    registry.run("transport.shuttle_forward", null, state);
    assert.deepEqual(calls, [
      ["shuttle", "j"],
      ["shuttle", "k"],
      ["shuttle", "l"],
    ]);
  });

  test("the fast-listening keys toggle, nudge and reset", () => {
    const { registry, calls } = setup({ project });
    for (const id of ["speed", "speed_down", "speed_up", "speed_reset"]) {
      assert.equal(registry.status(`transport.${id}`), "ready");
      registry.run(`transport.${id}`, null, { project });
    }
    assert.deepEqual(calls, [
      ["fastListening"],
      ["fastNudge", -1],
      ["fastNudge", 1],
      ["fastReset"],
    ]);
  });

  test("mark.in and mark.out set the points at the playhead", () => {
    const { registry, calls } = setup({ project, playhead: 5 });
    registry.run("mark.in");
    registry.run("mark.out");
    // The marks never reverse, so each command also says what happens to the other one.
    assert.deepEqual(calls, [
      ["patch", { inPoint: 5, outPoint: null, rangeTracks: new Set() }],
      ["patch", { inPoint: null, outPoint: 5, rangeTracks: new Set() }],
    ]);
  });

  test("1 and 2 jump to the in and out marks (Hindenburg's way), only when they are set", () => {
    const { registry, calls } = setup({ project, inPoint: 1000, outPoint: 5000 });
    const state = { project, inPoint: 1000, outPoint: 5000 };
    assert.equal(registry.can("nav.to_in", state), true);
    assert.equal(registry.can("nav.to_in", { project, inPoint: null }), false);
    assert.equal(registry.can("nav.to_out", { project }), false);
    registry.run("nav.to_in", null, state);
    registry.run("nav.to_out", null, state);
    assert.deepEqual(calls, [
      ["seek", 1000],
      ["seek", 5000],
    ]);
  });

  test("Shift+Space plays the marked range; Mod+Shift+Space rehearses the edit; both need a range", () => {
    const state = { project, inPoint: 10 * 48000, outPoint: 20 * 48000 };
    const { registry, calls } = setup(state);
    assert.equal(registry.can("transport.play_selection", { project }), false);
    assert.equal(registry.can("transport.rehearse", { project, inPoint: 5 }), false);
    registry.run("transport.play_selection", null, state);
    registry.run("transport.rehearse", null, state);
    assert.deepEqual(calls, [
      ["playRequest", { at: 480000, until: 960000, skip: null }],
      ["playRequest", { at: 336000, until: null, skip: [[480000, 960000]] }],
    ]);
  });

  test("an out mark before the in mark replaces the in mark", () => {
    const { registry, calls } = setup({ project, playhead: 2, inPoint: 9, outPoint: null });
    registry.run("mark.out");
    assert.deepEqual(calls, [["patch", { inPoint: null, outPoint: 2, rangeTracks: new Set() }]]);
  });

  test("rename needs a focused track or bus", () => {
    const { registry } = setup();
    assert.equal(registry.can("rename", { focusTrack: null, focusBus: null }), false);
    assert.equal(registry.can("rename", { focusTrack: "a" }), true);
  });

  test("help.open is always available and opens help", () => {
    const { registry, calls } = setup();
    assert.equal(registry.can("help.open", undefined), true);
    assert.equal(registry.can("help.open", {}), true);
    assert.equal(registry.hintKey("help.open"), "cmd.help.open.hint");
    registry.run("help.open", null, {});
    assert.deepEqual(calls, [["help"]]);
  });

  test("help.search is always available and opens the Help search (WP75)", () => {
    const { registry, calls } = setup();
    assert.equal(registry.can("help.search", undefined), true);
    assert.equal(registry.hintKey("help.search"), "cmd.help.search.hint");
    registry.run("help.search", null, {});
    assert.deepEqual(calls, [["openSearch"]]);
  });

  test("hints are given for the commands that have a one-line description", () => {
    const { registry } = setup();
    assert.equal(registry.hintKey("edit.undo"), "cmd.edit.undo.hint");
  });
});
