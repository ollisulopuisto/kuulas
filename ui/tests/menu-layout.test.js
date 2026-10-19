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
      "submenu",
      "app.close_project",
      "app.import",
      "app.locate_media",
      "separator",
      "app.save",
      "app.save_named",
      "app.send_copy",
      "separator",
      "app.export",
      "export.mix_options",
      "export.range",
      "export.automix",
      "export.tracks_quick",
      "export.tracks",
      "submenu",
      "separator",
      "app.statistics",
      "separator",
      "app.preferences",
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
  const shape = () =>
    top("edit").items.map((e) =>
      e.kind === "separator" ? "-" : e.kind === "submenu" ? `>${e.labelKey}` : e.id,
    );
  test("is the owner's order (2026-10-19): undo, sync back, clipboard, select, find", () => {
    assert.deepEqual(shape(), [
      "edit.undo",
      "edit.redo",
      ">menu.sync_back",
      "-",
      "edit.cut",
      "edit.copy",
      "edit.paste",
      ">menu.paste_variants",
      ">menu.delete_cut",
      "range.scope_toggle",
      ">menu.clipboard",
      "time.copy",
      "-",
      "edit.select_all",
      ">menu.select",
      "transcript.find",
    ]);
  });
  test("Sync back holds the commands that put things back, in one submenu", () => {
    assert.deepEqual(subIds("edit", "menu.sync_back"), [
      "sync.resync",
      "sync.resync_all",
      "sync.free",
      "sync.free_all",
      "sync.send_home",
    ]);
  });
  test("the rarer sync commands are Clip > Sync, and the dialog switch is in View", () => {
    assert.deepEqual(subIds("clip", "menu.sync"), [
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

describe("Clip", () => {
  test("holds the clip commands: split, trim, group, mute and fade, level, sync", () => {
    const shape = top("clip").items.map((e) =>
      e.kind === "separator" ? "-" : e.kind === "submenu" ? `>${e.labelKey}` : e.id,
    );
    assert.deepEqual(shape, [
      "edit.split",
      "edit.split_all",
      "edit.merge",
      ">menu.trim_nudge",
      "-",
      "edit.group",
      "edit.ungroup",
      "-",
      "clip.mute",
      "clip.fade",
      "clip.match_loudness",
      ">menu.level_pan",
      "-",
      ">menu.sync",
    ]);
  });
  test("Level and pan holds gain and pan", () => {
    assert.deepEqual(subIds("clip", "menu.level_pan"), [
      "clip.gain_up",
      "clip.gain_down",
      "clip.pan_left",
      "clip.pan_right",
    ]);
  });
});

describe("Text", () => {
  test("holds Transcribe, the word and narration commands, and Cut candidates", () => {
    const shape = top("text").items.map((e) =>
      e.kind === "separator" ? "-" : e.kind === "submenu" ? `>${e.labelKey}` : e.id,
    );
    assert.deepEqual(shape, [
      ">menu.transcribe",
      "transcript.delete_words",
      "transcript.remove_words",
      "transcript.cut_words",
      "transcript.correct",
      "transcript.mark_candidate",
      "placeholder.add",
      "placeholder.edit",
      "placeholder.take",
      "placeholder.delete",
      "-",
      ">menu.candidates",
    ]);
  });
  test("Transcribe (Litteroi) holds the transcribing commands and the Colab sign-in", () => {
    assert.deepEqual(subIds("text", "menu.transcribe"), [
      "app.transcribe",
      "app.transcribe_colab",
      "app.transcribe_restart",
      "app.colab_signin",
      "app.colab_settings",
    ]);
    assert.ok(!sub("track", "menu.transcribe") && !sub("edit", "menu.transcribe"));
  });
  test("Cut candidates holds ten commands", () => {
    assert.ok(subIds("text", "menu.candidates").includes("candidate.find"));
    assert.equal(subIds("text", "menu.candidates").length, 10);
  });
});

describe("Track, Playback, View", () => {
  test("Track lost the clip commands and gained Rename", () => {
    const ids = menuTargets([top("track")]);
    assert.ok(ids.includes("rename"));
    assert.ok(!ids.some((id) => id.startsWith("clip.") || id.startsWith("sync.")));
  });
  test("Playback has Jump to a typed time next to Go to", () => {
    const ids = top("playback").items.map((e) => (e.kind === "submenu" ? e.labelKey : e.id));
    assert.equal(ids[ids.indexOf("menu.go") + 1], "spot");
  });
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
    assert.deepEqual(subIds("view", "menu.language"), [
      "view.language_auto",
      "view.language_fi",
      "view.language_en",
    ]);
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
  test("is File, Edit, Clip, Track, Text, Playback, View, Help", () => {
    assert.deepEqual(
      MENU.map((m) => m.id),
      ["file", "edit", "clip", "track", "text", "playback", "view", "help"],
    );
  });
  test("Playback holds transport, record, Go to and Markers as submenus", () => {
    const names = top("playback")
      .items.filter((e) => e.kind === "submenu")
      .map((e) => e.labelKey);
    assert.deepEqual(names, [
      "menu.record_settings",
      "menu.fast_playback",
      "menu.slow_listening",
      "menu.shuttle",
      "menu.go",
      "menu.markers",
    ]);
    for (const id of ["transport.play", "transport.record", "transport.loop"]) {
      assert.ok(direct("playback").includes(id), id);
    }
    assert.ok(subIds("playback", "menu.markers").includes("marker.add"));
    assert.ok(subIds("playback", "menu.go").includes("nav.home"));
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
