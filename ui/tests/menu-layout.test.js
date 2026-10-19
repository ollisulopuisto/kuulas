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
    ]);
    assert.ok(direct("edit").length <= 10);
  });
});

describe("Track, Transport, View, Go", () => {
  test("Auto holds the ducking, Auto-Silence and Open this stretch", () => {
    assert.deepEqual(subIds("track", "menu.auto"), [
      "app.automix",
      "app.auto_silence",
      "gate.open_stretch",
    ]);
  });
  test("Fast playback is a submenu of four", () => {
    assert.equal(subIds("transport", "menu.fast_playback").length, 4);
    assert.ok(!direct("transport").some((id) => id.startsWith("transport.speed")));
  });
  test("View is grouped and has no loop toggle", () => {
    assert.equal(subIds("view", "menu.zoom_fit").length, 9);
    assert.deepEqual(subIds("view", "menu.buses"), [
      "view.collapse_all_buses",
      "view.expand_all_buses",
    ]);
    assert.deepEqual(subIds("view", "menu.mouse"), ["view.drag_mode", "view.wheel_mode"]);
    assert.ok(!menuTargets([top("view")]).includes("transport.loop"));
    assert.ok(menuTargets([top("transport")]).includes("transport.loop"));
  });
  test("Go shows each stop command once; the Transcript twin is an alias", () => {
    const go = menuTargets([top("go")]);
    assert.ok(go.includes("nav.prev_stop") && go.includes("nav.next_stop"));
    assert.ok(!go.includes("transcript.prev_stop") && !go.includes("transcript.next_stop"));
    assert.deepEqual(MENU_ALIASES, {
      "transcript.prev_stop": "nav.prev_stop",
      "transcript.next_stop": "nav.next_stop",
    });
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
