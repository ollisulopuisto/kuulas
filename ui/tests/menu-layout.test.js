// WP74: the owner's notes on every menu, as tests of the menu data (labels are keys here).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, MENU_ALIASES, menuTargets } from "../menu-model.js";

const top = (id) => MENU.find((m) => m.id === id);
const direct = (id) =>
  top(id)
    .items.filter((e) => e.kind === "item")
    .map((e) => e.id);
const sub = (menuId, labelKey) =>
  top(menuId).items.find((e) => e.kind === "submenu" && e.labelKey === labelKey);
const subIds = (menuId, labelKey) => menuTargets([{ items: sub(menuId, labelKey).items }]);

describe("File", () => {
  test("is in the owner's order", () => {
    const shape = top("file").items.map((e) => (e.kind === "item" ? e.id : e.kind));
    assert.deepEqual(shape, [
      "app.new",
      "app.open",
      "app.import",
      "app.locate_media",
      "separator",
      "app.save",
      "app.save_named",
      "app.send_copy",
      "separator",
      "app.export",
      "export.mix_options",
      "export.automix",
      "export.tracks_quick",
      "export.tracks",
      "submenu",
      "separator",
      "app.statistics",
    ]);
  });
  test("Export transcripts holds the text exports", () => {
    assert.deepEqual(subIds("file", "menu.export_transcripts"), [
      "export.subtitles_srt",
      "export.subtitles_vtt",
      "export.transcript_txt",
      "export.transcript_md",
      "export.chapters_text",
      "export.chapters_json",
      "export.regions",
      "export.narration_script_txt",
      "export.narration_script_md",
    ]);
  });
  test("the per-format export commands are not in the menu", () => {
    const ids = menuTargets(MENU);
    assert.ok(
      !ids.some((id) => /^export\.(mix|tracks)_(wav|flac|mp3|aiff|m4a|opus|ogg)$/.test(id)),
    );
  });
});

describe("Edit", () => {
  test("keeps the basics at the top level", () => {
    for (const id of [
      "edit.undo",
      "edit.redo",
      "edit.cut",
      "edit.copy",
      "edit.paste",
      "edit.select_all",
      "transcript.find",
    ]) {
      assert.ok(direct("edit").includes(id), id);
    }
  });
  test("groups the rest into short submenus", () => {
    const names = top("edit")
      .items.filter((e) => e.kind === "submenu")
      .map((e) => e.labelKey);
    assert.deepEqual(names, [
      "menu.delete_cut",
      "menu.paste_variants",
      "menu.clipboard",
      "menu.trim_nudge",
      "menu.split_merge",
      "menu.groups",
      "menu.select",
      "menu.transcribe",
      "menu.transcript_narration",
      "menu.candidates",
    ]);
    assert.ok(direct("edit").length <= 16);
  });
  test("the sync commands that put things back follow Undo and Redo, in one group (owner, 2026-10-19)", () => {
    const ids = top("edit").items.map((e) => (e.kind === "separator" ? "-" : (e.id ?? e.kind)));
    assert.deepEqual(ids.slice(0, 9), [
      "edit.undo",
      "edit.redo",
      "-",
      "sync.resync",
      "sync.resync_all",
      "sync.free",
      "sync.free_all",
      "sync.send_home",
      "-",
    ]);
  });
  test("the rarer sync commands stay under Track > Sync, and the dialog switch is in View", () => {
    assert.deepEqual(subIds("track", "menu.sync"), [
      "sync.mark",
      "sync.set_anchor",
      "sync.point1",
      "sync.point2",
      "sync.resync_end",
      "sync.drift_next",
      "sync.drift_previous",
    ]);
    assert.ok(direct("view").includes("sync.confirm"));
  });
});

describe("Track, Playback, View", () => {
  test("Auto holds the ducking, Auto-Silence and Open this stretch", () => {
    assert.deepEqual(subIds("track", "menu.auto"), [
      "app.automix",
      "app.auto_silence",
      "gate.open_stretch",
    ]);
  });
  test("Fast playback is a submenu of four", () => {
    assert.equal(subIds("playback", "menu.fast_playback").length, 4);
    assert.ok(!direct("playback").some((id) => id.startsWith("transport.speed")));
  });
  test("View is grouped and has no loop toggle", () => {
    assert.equal(subIds("view", "menu.zoom_fit").length, 9);
    assert.deepEqual(subIds("view", "menu.buses"), [
      "view.collapse_all_buses",
      "view.expand_all_buses",
    ]);
    assert.deepEqual(subIds("view", "menu.mouse"), ["view.drag_mode", "view.wheel_mode"]);
    assert.ok(!menuTargets([top("view")]).includes("transport.loop"));
    assert.ok(menuTargets([top("playback")]).includes("transport.loop"));
  });
  test("Go shows each stop command once; the Transcript twin is an alias", () => {
    const go = subIds("playback", "menu.go");
    assert.ok(go.includes("nav.prev_stop") && go.includes("nav.next_stop"));
    assert.ok(!go.includes("transcript.prev_stop") && !go.includes("transcript.next_stop"));
    assert.deepEqual(MENU_ALIASES, {
      "transcript.prev_stop": "nav.prev_stop",
      "transcript.next_stop": "nav.next_stop",
    });
  });
});

describe("top-level bar (owner, 2026-10-19)", () => {
  test("is File, Edit, Track, Playback, View, Help", () => {
    assert.deepEqual(
      MENU.map((m) => m.id),
      ["file", "edit", "track", "playback", "view", "help"],
    );
  });
  test("Playback holds transport, record, Go to and Markers as submenus", () => {
    const names = top("playback")
      .items.filter((e) => e.kind === "submenu")
      .map((e) => e.labelKey);
    assert.deepEqual(names, ["menu.fast_playback", "menu.shuttle", "menu.go", "menu.markers"]);
    for (const id of ["transport.play", "transport.record", "transport.loop"]) {
      assert.ok(direct("playback").includes(id), id);
    }
    assert.ok(subIds("playback", "menu.markers").includes("marker.add"));
    assert.ok(subIds("playback", "menu.go").includes("nav.home"));
  });
  test("Edit holds Transcript and narration, and Cut candidates, as submenus", () => {
    assert.deepEqual(subIds("edit", "menu.transcript_narration"), [
      "transcript.delete_words",
      "transcript.remove_words",
      "transcript.cut_words",
      "transcript.correct",
      "transcript.mark_candidate",
      "placeholder.add",
      "placeholder.edit",
      "placeholder.take",
      "placeholder.delete",
    ]);
    assert.ok(subIds("edit", "menu.candidates").includes("candidate.find"));
    assert.equal(subIds("edit", "menu.candidates").length, 10);
  });
  test("the transcribing commands are Edit > Transcribe (Litteroi), no longer under Track", () => {
    assert.deepEqual(subIds("edit", "menu.transcribe"), [
      "app.transcribe",
      "app.transcribe_colab",
      "app.transcribe_restart",
      "app.colab_settings",
    ]);
    assert.ok(!sub("track", "menu.transcribe"));
  });
});

describe("keys", () => {
  const entry = (id) => DEFAULT_KEYMAP.find((e) => e.id === id);
  test("Clear in and out points has a letter key", () => {
    assert.equal(entry("mark.clear").keys.mac, "Shift+Alt+I");
    assert.equal(entry("mark.clear").keys.other, "Shift+Alt+I");
  });
  test("no default key is on a bracket key (Finnish keyboards need AltGr for them)", () => {
    assert.deepEqual(entry("candidate.next").keys.mac, "Alt+ArrowDown");
    assert.deepEqual(entry("candidate.previous").keys.mac, "Alt+ArrowUp");
  });
  test("the export keys: Mod+E is the plain mix, Shift adds the options", () => {
    assert.equal(entry("app.export").keys.mac, "Mod+E");
    assert.equal(entry("export.mix_options").keys.mac, "Shift+Mod+E");
    assert.equal(entry("export.tracks_quick").keys.mac, "Alt+Mod+E");
    assert.equal(entry("export.tracks").keys.mac, "Shift+Alt+Mod+E");
  });
});
