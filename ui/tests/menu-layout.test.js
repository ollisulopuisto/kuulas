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
      "app.import_nhsx",
      "app.locate_media",
      "separator",
      "app.save",
      "app.save_named",
      "submenu",
      "separator",
      "app.export",
      "export.mix_options",
      "export.automix",
      "submenu",
      "separator",
      "submenu",
      "app.statistics",
      "separator",
      "app.preferences",
    ]);
  });
  // docs/design/SERIES.md (owner, 2026-10-21): every series command in one submenu.
  test("Series holds the series commands", () => {
    assert.deepEqual(subIds("file", "menu.series"), [
      "series.dialog",
      "series.save",
      "series.apply",
      "series.new_episode",
      "series.music_add",
      "series.music_place",
      "series.music_clipboard",
    ]);
  });
  // Owner, 2026-10-24 (docs/design/MENUS.md): the three exports of the first hour stay in File;
  // the rest sit in one submenu, and the earlier versions, backup and copy in another.
  test("Versions holds the saved-version commands, rarely needed", () => {
    assert.deepEqual(subIds("file", "menu.versions"), [
      "app.open_earlier_version",
      "app.backup_now",
      "app.send_copy",
    ]);
  });
  test("More exports holds the other exports, the text exports and the reports", () => {
    assert.deepEqual(subIds("file", "menu.more_exports"), [
      "export.range",
      "export.tracks_quick",
      "export.tracks",
      "export.automix_log",
      "export.subtitles_srt",
      "export.subtitles_vtt",
      "export.transcript_txt",
      "export.transcript_md",
      "export.chapters_text",
      "export.chapters_json",
      "export.regions",
      "export.narration_script_txt",
      "export.narration_script_md",
      "export.music_report",
      "export.cut_list",
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
      "sync.resync_range",
      "sync.free",
      "sync.free_all",
      "sync.accept_range",
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
    // The dialog switch is one of the View > Options switches (owner, 2026-10-24).
    assert.ok(subIds("view", "menu.options").includes("sync.confirm"));
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
      "clip.quick_mute",
      "clip.fade",
      "clip.match_loudness",
      "clip.envelope_delete_point",
      "clip.envelope_reset",
      ">menu.level_pan",
      "-",
      ">menu.sync",
      "-",
      "clip.relink_media",
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
      "-",
      "transcript.find_removed",
      "transcript.mark_candidate",
      "-",
      ">menu.placeholders",
      ">menu.candidates",
    ]);
  });
  test("Placeholders holds the four narration commands", () => {
    assert.deepEqual(subIds("text", "menu.placeholders"), [
      "placeholder.add",
      "placeholder.edit",
      "placeholder.take",
      "placeholder.delete",
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
  test("Auto holds the ducking, Auto-Silence, Set music level, Level blocks and Open this stretch", () => {
    assert.deepEqual(subIds("track", "menu.auto"), [
      "app.automix",
      "app.auto_silence",
      "app.auto_silence_options",
      "app.silence_learn",
      "app.music_level",
      "app.block_level",
      "app.duck_music",
      "track.automation_delete_point",
      "track.automation_clear",
      "gate.open_stretch",
      "gate.open_under_clips",
      "gate.open_all",
    ]);
  });
  test("Speed is one submenu: fast, slow and shuttle listening", () => {
    const ids = subIds("playback", "menu.speed");
    assert.equal(ids.length, 13);
    assert.ok(ids.includes("transport.speed") && ids.includes("transport.slow_info"));
    assert.ok(ids.includes("transport.shuttle_back"));
    assert.ok(!direct("playback").some((id) => id.startsWith("transport.speed")));
    for (const old of ["menu.fast_playback", "menu.slow_listening", "menu.shuttle"]) {
      assert.ok(!sub("playback", old), old);
    }
  });
  test("Track keeps role and bus in submenus and Auto at the bottom", () => {
    const names = top("track")
      .items.filter((e) => e.kind === "submenu")
      .map((e) => e.labelKey);
    assert.deepEqual(names, ["menu.role", "menu.bus", "menu.auto"]);
    assert.deepEqual(subIds("track", "menu.role"), [
      "track.cycle_kind",
      "track.match_role",
      "track.role_speech",
      "track.role_music",
    ]);
    assert.ok(subIds("track", "menu.bus").includes("track.new_bus"));
    assert.ok(subIds("track", "menu.bus").includes("bus.reapply_role"));
  });
  test("History is in View, not in Go", () => {
    assert.ok(!subIds("playback", "menu.go").some((id) => id.startsWith("history.")));
    assert.deepEqual(subIds("view", "menu.history"), [
      "history.open",
      "history.restore",
      "history.goto_restore_point",
      "history.expand_all",
      "history.saved_only",
      "history.open_saved",
      "history.rename_version",
    ]);
  });
  test("Help starts with Getting started: the first-hour commands, each the real one", () => {
    assert.deepEqual(subIds("help", "menu.getting_started"), [
      "app.import",
      "transport.play",
      "edit.split",
      "app.transcribe",
      "app.export",
      "palette.open",
    ]);
  });
  test("View is grouped and has no loop toggle", () => {
    assert.equal(subIds("view", "menu.zoom_fit").length, 9);
    assert.deepEqual(subIds("view", "menu.buses"), [
      "view.collapse_all_buses",
      "view.expand_all_buses",
    ]);
    // The switches are one submenu (owner, 2026-10-24); each group keeps its order.
    assert.deepEqual(subIds("view", "menu.options"), [
      "view.drag_mode",
      "view.wheel_mode",
      "view.inactive_both",
      "view.inactive_desaturate",
      "view.inactive_dim",
      "view.pause_1_5",
      "view.pause_3",
      "view.pause_6",
      "view.pause_never",
      "view.clipboard_limit",
      "sync.confirm",
      "sync.show_drift",
      "view.reset_remembered",
    ]);
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
  test("Playback holds transport, record, Go to, Markers and the Cart as submenus", () => {
    const names = top("playback")
      .items.filter((e) => e.kind === "submenu")
      .map((e) => e.labelKey);
    assert.deepEqual(names, [
      "menu.record_settings",
      "menu.speed",
      "menu.go",
      "menu.markers",
      "menu.cart",
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
  test("the export keys (owner 2026-10-21): Mod+E mix, Shift+Mod+E automixer, Alt+Mod+E mix with options; the all-tracks exports have none", () => {
    assert.equal(entry("app.export").keys.mac, "Mod+E");
    assert.equal(entry("export.automix").keys.mac, "Shift+Mod+E");
    assert.equal(entry("export.mix_options").keys.mac, "Alt+Mod+E");
    assert.equal(entry("export.tracks_quick").keys.mac, null);
    assert.equal(entry("export.tracks").keys.mac, null);
  });
});

describe("the bar draws one level of submenus", () => {
  // A submenu inside a submenu cannot be opened from the menu bar (menubar.js keeps one level),
  // and Help search could not show where it is (the Cart sat two levels deep until 2026-10-24).
  const nested = (entries, path = []) =>
    entries.flatMap((entry) =>
      entry.items
        ? entry.items.flatMap((inner) =>
            inner.items ? [[...path, entry.labelKey ?? entry.id, inner.labelKey ?? inner.id]] : [],
          )
        : [],
    );

  test("no submenu holds a submenu", () => {
    const found = MENU.flatMap((menu) => nested(menu.items, [menu.id]));
    assert.deepEqual(found, []);
  });
});
