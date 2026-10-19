// The default keymap is data. These tests are the WP5 collision test and the
// owner's key decisions (18.10.2026), so a change to either is a visible diff.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { findCollisions, resolveKeymap } from "../keymap-config.js";
import { CONTEXTS, DEFAULT_KEYMAP, STATUS_HINTS } from "../keymap-default.js";
import { parseCombo } from "../keys.js";

const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));
const asList = (value) => (value === null || value === undefined ? [] : [value].flat());
const keysOf = (id, platform = "other") =>
  asList(DEFAULT_KEYMAP.find((entry) => entry.id === id)?.keys[platform]);

describe("the data", () => {
  test("one entry per command id, each with keys, a context and a label", () => {
    const ids = DEFAULT_KEYMAP.map((entry) => entry.id);
    assert.equal(new Set(ids).size, ids.length);
    for (const entry of DEFAULT_KEYMAP) {
      assert.ok(CONTEXTS.includes(entry.context), `${entry.id}: context ${entry.context}`);
      assert.ok("mac" in entry.keys && "other" in entry.keys, `${entry.id}: both platforms`);
      assert.match(entry.labelKey, /^cmd\./);
    }
  });

  test("every combo parses", () => {
    for (const entry of DEFAULT_KEYMAP) {
      for (const platform of ["mac", "other"]) {
        for (const combo of asList(entry.keys[platform])) {
          assert.notEqual(parseCombo(combo), null, `${entry.id}: ${combo}`);
        }
      }
    }
  });

  test("every label is in both catalogs", () => {
    for (const lang of ["en", "fi"]) {
      const messages = catalog(lang);
      for (const entry of DEFAULT_KEYMAP) {
        assert.ok(messages[entry.labelKey], `${lang}: ${entry.labelKey}`);
      }
      for (const hints of Object.values(STATUS_HINTS)) {
        for (const hint of hints) assert.ok(messages[hint.hintKey], `${lang}: ${hint.hintKey}`);
      }
    }
  });

  test("status-bar hints name commands that exist", () => {
    const ids = new Set(DEFAULT_KEYMAP.map((entry) => entry.id));
    for (const hints of Object.values(STATUS_HINTS)) {
      for (const hint of hints) assert.ok(ids.has(hint.id), hint.id);
    }
  });
});

describe("the WP5 collision test", () => {
  for (const platform of ["mac", "other"]) {
    test(`no two default commands share a key in one context (${platform})`, () => {
      const collisions = findCollisions(resolveKeymap(DEFAULT_KEYMAP, {}, platform));
      assert.deepEqual(collisions, []);
    });
  }
});

describe("Finnish keyboard (owner, 2026-10-19)", () => {
  test("no default key is on [ ] / \\ or the backquote (AltGr or Shift+digit there)", () => {
    for (const entry of DEFAULT_KEYMAP) {
      for (const platform of ["mac", "other"]) {
        const raw = entry.keys[platform];
        for (const combo of raw === null ? [] : [raw].flat()) {
          const parsed = parseCombo(combo);
          assert.ok(parsed, `${entry.id}: ${combo}`);
          assert.ok(!"[]/\\`".includes(parsed.key), `${entry.id} is bound to ${combo}`);
        }
      }
    }
  });

  test("help search is Shift+Mod+K, not Mod+/", () => {
    assert.deepEqual(keysOf("help.search"), ["Shift+Mod+K"]);
  });
});

describe("the owner's decisions", () => {
  test("fast listening: . toggles, Shift+J or , slow it and Shift+L speeds it by a step (held keys repeat), Alt+0 resets", () => {
    assert.deepEqual(keysOf("transport.speed"), ["."]);
    assert.deepEqual(keysOf("transport.speed_down"), ["Shift+J", ","]);
    assert.deepEqual(keysOf("transport.speed_up"), ["Shift+L"]);
    assert.deepEqual(keysOf("transport.speed_reset"), ["Alt+0"]);
    for (const id of ["transport.speed_down", "transport.speed_up"]) {
      assert.equal(DEFAULT_KEYMAP.find((entry) => entry.id === id).repeat, true);
    }
  });

  test("Backspace is Delete, X removes and closes the gap, Mod+X cuts to the clipboard, Mod+C copies", () => {
    assert.ok(keysOf("edit.delete").includes("Backspace"));
    assert.deepEqual(keysOf("edit.remove"), ["X"]);
    assert.deepEqual(keysOf("edit.cut"), ["Mod+X"]);
    assert.deepEqual(keysOf("edit.copy"), ["Mod+C"]);
  });

  test("Spot is Mod+J, find is Mod+F, fade is G, import is Mod+I", () => {
    assert.deepEqual(keysOf("spot"), ["Mod+J"]);
    assert.deepEqual(keysOf("transcript.find"), ["Mod+F"]);
    assert.deepEqual(keysOf("clip.fade"), ["G"]);
    assert.deepEqual(keysOf("app.import"), ["Mod+I"]);
  });

  test("candidates use Alt+Down/Up (no bracket keys), Enter keeps, F2 renames", () => {
    assert.deepEqual(keysOf("candidate.next"), ["Alt+ArrowDown"]);
    assert.deepEqual(keysOf("candidate.previous"), ["Alt+ArrowUp"]);
    assert.deepEqual(keysOf("candidate.reject"), ["Enter"]);
    assert.deepEqual(keysOf("rename"), ["F2"]);
  });

  test("the candidate keys: stepping and marking everywhere, deciding in the tab only", () => {
    const contextOf = (id) => DEFAULT_KEYMAP.find((entry) => entry.id === id).context;
    for (const id of ["candidate.mark", "candidate.filter"]) {
      assert.equal(contextOf(id), "global", id);
    }
    // ] and [ step the drift list while the Markers tab has the keyboard (WP19a), candidates elsewhere.
    for (const id of ["candidate.next", "candidate.previous"]) {
      assert.equal(contextOf(id), "not-markers", id);
    }
    for (const id of ["candidate.apply", "candidate.reject", "candidate.preview"]) {
      assert.equal(contextOf(id), "candidates", id);
    }
    assert.deepEqual(keysOf("candidate.apply"), ["Backspace", "Delete"]);
    assert.deepEqual(keysOf("candidate.preview"), ["Shift+Space"]);
    assert.deepEqual(keysOf("candidate.filter"), ["Shift+Mod+D"]);
    assert.deepEqual(keysOf("candidate.mark"), ["D"]);
    // The ripple apply is a button and a palette entry, not a key.
    assert.deepEqual(keysOf("candidate.apply_ripple"), []);
  });

  test("Tab steps to a word or transient in the timeline and the transcript only", () => {
    const contextsOf = (combo) =>
      DEFAULT_KEYMAP.filter((e) => asList(e.keys.other).includes(combo)).map((e) => e.context);
    // Not in the side panels, candidates or text fields: Tab keeps its focus move there.
    assert.deepEqual(contextsOf("Tab").sort(), ["timeline", "transcript"]);
    assert.deepEqual(contextsOf("Shift+Tab").sort(), ["timeline", "transcript"]);
    assert.deepEqual(keysOf("nav.tab_target_cycle", "mac"), ["Alt+Tab"]);
    assert.deepEqual(keysOf("nav.tab_target_cycle"), ["Shift+T"]);
  });

  test("sync: U frees, F7 and Shift+F7 step the drift list in the Markers tab, the rest has no key", () => {
    const contextOf = (id) => DEFAULT_KEYMAP.find((entry) => entry.id === id).context;
    assert.deepEqual(keysOf("sync.free"), ["U"]);
    assert.equal(contextOf("sync.free"), "timeline");
    assert.deepEqual(keysOf("sync.drift_next"), ["F7"]);
    assert.deepEqual(keysOf("sync.drift_previous"), ["Shift+F7"]);
    for (const id of ["sync.drift_next", "sync.drift_previous"]) {
      assert.equal(contextOf(id), "markers", id);
    }
    for (const id of ["sync.resync_all", "sync.free_all"]) assert.deepEqual(keysOf(id), [], id);
    assert.deepEqual(keysOf("sync.resync"), ["R", "Alt+Mod+R"]);
    assert.deepEqual(keysOf("sync.resync_end"), ["Shift+Alt+Mod+R"]);
  });

  test("X cuts the marked range from anywhere but a text field and the transcript", () => {
    for (const id of [
      "edit.remove",
      "edit.remove_track",
      "edit.cut",
      "edit.cut_track",
      "edit.lift_cut",
      "edit.close_gap_all",
    ]) {
      assert.equal(DEFAULT_KEYMAP.find((e) => e.id === id).context, "not-transcript", id);
    }
    assert.equal(DEFAULT_KEYMAP.find((e) => e.id === "transcript.cut_words").context, "transcript");
  });

  test("1 and 2 go to the in and out marks; Mod+1 and Mod+2 set them, like Hindenburg", () => {
    assert.deepEqual(keysOf("nav.to_in", "mac"), ["1"]);
    assert.deepEqual(keysOf("nav.to_out", "mac"), ["2"]);
    assert.ok(keysOf("mark.in", "mac").includes("Mod+1"));
    assert.ok(keysOf("mark.out", "mac").includes("Mod+2"));
  });

  test("Cmd+Enter adds a marker (Hindenburg); M mutes the clips and N is unwired", () => {
    assert.deepEqual(keysOf("marker.add", "mac"), ["Mod+Enter"]);
    assert.deepEqual(keysOf("clip.mute", "mac"), ["M", "Alt+Mod+M"]);
  });

  test("K stops the shuttle everywhere, including the Candidates tab", () => {
    const withK = DEFAULT_KEYMAP.filter((entry) => asList(entry.keys.other).includes("K"));
    assert.deepEqual(
      withK.map((entry) => [entry.id, entry.context]),
      [["transport.shuttle_stop", "global"]],
    );
  });

  test("P plays from a few seconds before the playhead, in every panel", () => {
    assert.deepEqual(keysOf("transport.play_before"), ["P"]);
    assert.equal(
      DEFAULT_KEYMAP.find((entry) => entry.id === "transport.play_before").context,
      "global",
    );
  });

  test("J and L shuttle from every panel", () => {
    assert.deepEqual(keysOf("transport.shuttle_back"), ["J"]);
    assert.deepEqual(keysOf("transport.shuttle_forward"), ["L"]);
    for (const id of ["transport.shuttle_back", "transport.shuttle_forward"]) {
      assert.equal(DEFAULT_KEYMAP.find((entry) => entry.id === id).context, "global");
    }
  });

  test("fitting tracks to the window is unbound by default", () => {
    for (const id of ["view.fit_tracks", "view.auto_fit_tracks"]) {
      const entry = DEFAULT_KEYMAP.find((e) => e.id === id);
      assert.ok(entry, id);
      assert.deepEqual(keysOf(id), [], id);
      assert.equal(entry.context, "global", id);
    }
  });

  test("buses collapse on Alt+Mod+Left/Right", () => {
    assert.deepEqual(keysOf("bus.collapse"), ["Alt+Mod+ArrowLeft"]);
    assert.deepEqual(keysOf("bus.expand"), ["Alt+Mod+ArrowRight"]);
  });

  test("the keys the app already had are still in the data", () => {
    assert.deepEqual(keysOf("transport.play"), ["Space"]);
    assert.deepEqual(keysOf("nav.home"), ["Escape"]);
    assert.deepEqual(keysOf("panel.next"), ["F6"]);
    assert.deepEqual(keysOf("panel.previous"), ["Shift+F6"]);
    assert.deepEqual(keysOf("view.toggle"), ["Z"]);
    assert.deepEqual(keysOf("view.fit"), ["0"]);
    assert.deepEqual(keysOf("view.fit_selection"), ["F"]);
    assert.deepEqual(keysOf("view.back"), ["Alt+Mod+Shift+ArrowLeft"]);
    assert.deepEqual(keysOf("view.forward"), ["Alt+Mod+Shift+ArrowRight"]);
    assert.deepEqual(keysOf("mark.clear_in"), ["Shift+I"]);
    assert.deepEqual(keysOf("mark.clear_out"), ["Shift+O"]);
    assert.deepEqual(keysOf("mark.clear"), ["Shift+Alt+I"]);
    // Cmd+Z and Cmd+Shift+Z are undo and redo: no view command lives on a modified Z.
    for (const entry of DEFAULT_KEYMAP.filter((e) => e.id.startsWith("view."))) {
      for (const key of asList(entry.keys.other)) assert.doesNotMatch(key, /\+Z$/i, entry.id);
    }
    assert.ok(keysOf("view.zoom_in").includes("="));
    assert.deepEqual(keysOf("view.zoom_out"), ["-"]);
    assert.deepEqual(keysOf("palette.open"), ["Mod+K"]);
    assert.deepEqual(keysOf("help.keys"), ["?"]);
    assert.deepEqual(keysOf("help.open"), ["F1"]);
  });

  test("F1 opens help from anywhere, also while typing", () => {
    assert.equal(DEFAULT_KEYMAP.find((e) => e.id === "help.open").context, "text-field");
  });

  test("parked items are not bound", () => {
    const ids = DEFAULT_KEYMAP.map((entry) => entry.id).join(" ");
    assert.doesNotMatch(ids, /compare|clean|clipboard_history/);
    for (const entry of DEFAULT_KEYMAP) {
      for (const combo of [entry.keys.mac, entry.keys.other].flatMap(asList)) {
        if (entry.id !== "edit.lift_cut") assert.notEqual(combo, "Alt+X", entry.id);
        assert.notEqual(combo, "`", entry.id);
      }
    }
  });

  test("the palette and keymap file commands exist, with no key", () => {
    for (const id of ["keymap.import", "keymap.export", "keymap.reset"]) {
      assert.deepEqual(keysOf(id), [], id);
    }
  });
});

describe("the standard Mac keys (owner, 2026-10-19)", () => {
  test("Cmd+W closes the project, Cmd+, opens Preferences, Cmd+M minimises", () => {
    assert.deepEqual(keysOf("app.close_project"), ["Mod+W"]);
    assert.deepEqual(keysOf("app.preferences"), ["Mod+Comma"]);
    assert.deepEqual(keysOf("app.minimise"), ["Mod+M"]);
  });
  test("Open Recent has no key and Revert to saved does not exist", () => {
    assert.deepEqual(keysOf("app.clear_recent"), []);
    assert.equal(
      DEFAULT_KEYMAP.some((entry) => /revert/i.test(entry.id)),
      false,
    );
  });
});

describe("the N key stays free (owner, 2026-10-19)", () => {
  test("N sits between B (split) and M (mute): no default binding uses N or Shift+N", () => {
    for (const entry of DEFAULT_KEYMAP) {
      for (const platform of ["mac", "other"]) {
        const keys = [entry.keys?.[platform]].flat().filter(Boolean);
        assert.ok(!keys.includes("N") && !keys.includes("Shift+N"), `${entry.id} ${platform}`);
      }
    }
  });
});
