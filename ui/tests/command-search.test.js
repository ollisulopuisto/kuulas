// WP75: the matching and ranking behind Help search and the palette. No DOM.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  commandRecords,
  fold,
  matchCommand,
  menuPaths,
  searchAll,
  searchCommands,
} from "../command-search.js";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";

const key = (id, keys, context = "global") => ({
  id,
  keys: { mac: keys, other: keys },
  context,
  labelKey: `cmd.${id}`,
});
const DATA = [
  key("edit.delete", "Backspace", "timeline"),
  key("edit.undo", "Mod+Z"),
  key("clip.gain_up", null, "timeline"),
  key("export.subtitles_srt", null),
  key("export.mix_wav", null),
  key("app.save", "Mod+S"),
  key("app.transcribe", null),
  key("transcript.find", "Mod+F"),
  key("transcript.prev_stop", "Shift+Tab", "transcript"),
  key("nav.prev_stop", "Shift+Tab", "timeline"),
];
const EN = {
  "menu.file": "File",
  "menu.edit": "Edit",
  "menu.export_transcripts": "Export transcripts",
  "menu.go": "Go",
  "cmd.edit.delete": "Delete, keep the gap",
  "cmd.edit.delete.hint": "Mute the selection in place; the gap stays",
  "cmd.edit.undo": "Undo",
  "cmd.edit.undo.hint": "Takes back the last change, a step at a time.",
  "cmd.clip.gain_up": "Clip gain up",
  "cmd.clip.gain_up.hint": "Raises the volume of the selected clips.",
  "cmd.export.subtitles_srt": "SRT subtitles",
  "cmd.export.subtitles_srt.hint": "Subtitles as an .srt file",
  "cmd.export.mix_wav": "Export mix as WAV",
  "cmd.export.mix_wav.hint": "Renders the whole programme",
  "cmd.app.save": "Save",
  "cmd.app.save.hint": "Writes the project to disk",
  "cmd.app.transcribe": "Transcribe the track",
  "cmd.app.transcribe.hint": "Turns speech into words",
  "cmd.transcript.find": "Find in the transcript",
  "cmd.transcript.find.hint": "Search the words",
  "cmd.transcript.prev_stop": "Previous stop (transcript)",
  "cmd.nav.prev_stop": "Previous stop",
};
const FI = {
  "menu.file": "Tiedosto",
  "menu.edit": "Muokkaa",
  "menu.export_transcripts": "Vie litteraatit",
  "cmd.edit.delete": "Poista, jätä aukko",
  "cmd.edit.delete.hint": "Hiljentää valinnan paikallaan",
  "cmd.edit.undo": "Kumoa",
  "cmd.clip.gain_up": "Leikkeen voimakkuus ylös",
  "cmd.export.subtitles_srt": "SRT-tekstitys",
};
const item = (id) => ({ kind: "item", id });
const MENU = [
  {
    id: "file",
    labelKey: "menu.file",
    items: [
      item("app.save"),
      { kind: "separator" },
      {
        kind: "submenu",
        labelKey: "menu.export_transcripts",
        items: [item("export.subtitles_srt")],
      },
    ],
  },
  {
    id: "edit",
    labelKey: "menu.edit",
    items: [
      item("edit.undo"),
      item("edit.delete"),
      item("clip.gain_up"),
      item("app.transcribe"),
      item("transcript.find"),
    ],
  },
  { id: "go", labelKey: "menu.go", items: [item("nav.prev_stop")] },
];
const ALIASES = { "transcript.prev_stop": "nav.prev_stop" };
const label = (k) => EN[k] ?? k;
const fiLabel = (k) => FI[k];
const fmt = (combo) => combo;
const REASONS = {
  planned: "Not built yet",
  noProject: "Open a project first",
  unavailable: "Not now",
};

function build({ state = { project: {} }, canDelete = true, synonymsFor } = {}) {
  const registry = createRegistry();
  for (const entry of DATA) {
    if (entry.id === "edit.delete") {
      registry.register(entry.id, () => {}, {
        can: () => canDelete,
        hintKey: `${entry.labelKey}.hint`,
      });
    } else if (entry.id === "app.transcribe") registry.planned(entry.id);
    else registry.register(entry.id, () => {}, { hintKey: `${entry.labelKey}.hint` });
  }
  return commandRecords({
    entries: resolveKeymap(DATA, {}, "other"),
    registry,
    state,
    menu: MENU,
    aliases: ALIASES,
    label,
    otherLabels: [fiLabel],
    format: fmt,
    platform: "other",
    synonymsFor,
    reasons: REASONS,
  });
}
const ids = (rows) => rows.map((row) => row.id);

describe("folding", () => {
  test("accents and case are ignored", () => {
    assert.equal(fold("Äänitys HILJENNÄ"), "aanitys hiljenna");
  });
});

describe("matching", () => {
  test("accents and case are ignored in the query and in the names", () => {
    const records = build();
    assert.deepEqual(ids(searchCommands(records, "JATA aukko")), ["edit.delete"]);
    assert.deepEqual(ids(searchCommands(records, "poista")), ["edit.delete"]);
  });

  test("every word must match", () => {
    const records = build();
    assert.deepEqual(ids(searchCommands(records, "previous stop")).sort(), [
      "nav.prev_stop",
      "transcript.prev_stop",
    ]);
    assert.deepEqual(searchCommands(records, "previous banana"), []);
  });

  test("the Finnish name is found while the UI is English, and the English name in Finnish", () => {
    const records = build();
    assert.equal(searchCommands(records, "kumoa")[0].id, "edit.undo");
    assert.equal(searchCommands(records, "undo")[0].id, "edit.undo");
    const registry = createRegistry();
    registry.register("edit.undo", () => {});
    const finnishUi = commandRecords({
      entries: resolveKeymap(DATA, {}, "other"),
      registry,
      state: {},
      menu: MENU,
      aliases: {},
      label: (k) => FI[k] ?? EN[k],
      otherLabels: [(k) => EN[k]],
      format: fmt,
      platform: "other",
      reasons: {},
    });
    assert.equal(searchCommands(finnishUi, "undo")[0].id, "edit.undo");
    assert.equal(searchCommands(finnishUi, "kumoa")[0].name, "Kumoa");
  });

  test("surrounding spaces do not matter", () => {
    assert.deepEqual(ids(searchCommands(build(), "  undo  ")), ["edit.undo"]);
  });
});

describe("ranking", () => {
  const record = (id, name, { hint = "", synonyms = [] } = {}) => ({
    id,
    names: [name],
    hints: hint ? [hint] : [],
    synonyms,
  });
  test("exact name > name prefix > name word > inside a name word > hint > synonym", () => {
    const rows = [
      record("syn", "Zebra", { synonyms: ["cut it", "slice"] }),
      record("hint", "Yak", { hint: "Will cut things" }),
      record("inside", "Recutting"),
      record("word", "Quick cut"),
      record("prefix", "Cutter"),
      record("exact", "Cut"),
    ];
    const found = rows
      .map((r) => [r.id, matchCommand(r, "cut")])
      .filter(([, m]) => m)
      .sort((a, b) => b[1].score - a[1].score)
      .map(([id]) => id);
    assert.deepEqual(found, ["exact", "prefix", "word", "inside", "hint", "syn"]);
  });

  test("a synonym that is exactly the query beats a hint match; one that only contains it does not", () => {
    const hint = record("hint", "Yak", { hint: "Will cut things" });
    const exact = record("exact", "Zebra", { synonyms: ["cut"] });
    const loose = record("loose", "Gnu", { synonyms: ["cut it"] });
    assert.ok(matchCommand(exact, "cut").score > matchCommand(hint, "cut").score);
    assert.ok(matchCommand(hint, "cut").score > matchCommand(loose, "cut").score);
  });

  test("the UI-language name beats the other language's name at the same tier", () => {
    const a = { id: "a", names: ["Cut", "Leikkaa"], hints: [], synonyms: [] };
    assert.ok(matchCommand(a, "cut").score > matchCommand(a, "leikkaa").score);
  });

  test("a short name beats a long one at the same tier", () => {
    const short = { id: "s", names: ["Cut"], hints: [], synonyms: [] };
    const long = { id: "l", names: ["Cut the thing in two parts"], hints: [], synonyms: [] };
    assert.ok(matchCommand(short, "cut").score > matchCommand(long, "cut").score);
  });

  test("a hint word finds the command", () => {
    assert.equal(searchCommands(build(), "volume")[0].id, "clip.gain_up");
  });

  test("exact name beats a hint match in the same search", () => {
    const rows = searchCommands(build(), "save");
    assert.equal(rows[0].id, "app.save");
  });

  test("synonyms find a command by what it does", () => {
    const records = build({
      synonymsFor: (id) => (id === "edit.delete" ? ["remove", "erase"] : []),
    });
    assert.equal(searchCommands(records, "erase")[0].id, "edit.delete");
    assert.equal(searchCommands(build(), "erase").length, 0);
  });

  test("a multi-word synonym matches as a phrase", () => {
    const records = build({ synonymsFor: (id) => (id === "app.save" ? ["save as"] : []) });
    assert.equal(searchCommands(records, "save as")[0].id, "app.save");
  });

  test("words may be spread over name, hint and synonyms", () => {
    const records = build({ synonymsFor: (id) => (id === "edit.undo" ? ["revert"] : []) });
    assert.equal(searchCommands(records, "revert undo")[0].id, "edit.undo");
    assert.equal(searchCommands(records, "undo step")[0].id, "edit.undo");
  });
});

describe("what a result says", () => {
  test("the menu path of a nested item ends in its name", () => {
    const row = searchCommands(build(), "srt")[0];
    assert.deepEqual(row.path, ["File", "Export transcripts"]);
    assert.equal(row.where, "File > Export transcripts > SRT subtitles");
    assert.equal(row.paletteOnly, false);
  });

  test("a top-level item: menu and name", () => {
    assert.equal(searchCommands(build(), "undo")[0].where, "Edit > Undo");
  });

  test("a command listed through an alias is found where the menu shows its twin", () => {
    const row = searchCommands(build(), "previous stop (transcript)")[0];
    assert.equal(row.id, "transcript.prev_stop");
    assert.equal(row.where, "Go > Previous stop (transcript)");
  });

  test("a command in no menu is marked palette only and has no path", () => {
    const row = searchCommands(build(), "wav")[0];
    assert.equal(row.id, "export.mix_wav");
    assert.equal(row.paletteOnly, true);
    assert.equal(row.where, null);
  });

  test("keys, and 'no key' for a command without one", () => {
    const records = build();
    assert.deepEqual(searchCommands(records, "undo")[0].keys, ["Mod+Z"]);
    const gain = searchCommands(records, "gain")[0];
    assert.deepEqual(gain.keys, []);
    assert.equal(gain.noKey, true);
  });

  test("the hint is carried", () => {
    assert.equal(
      searchCommands(build(), "undo")[0].hint,
      "Takes back the last change, a step at a time.",
    );
  });

  test("a greyed command says why: no project, planned, or cannot apply", () => {
    const none = searchCommands(build({ state: { project: null }, canDelete: false }), "delete")[0];
    assert.equal(none.enabled, false);
    assert.equal(none.reason, "Open a project first");
    const planned = searchCommands(build(), "transcribe")[0];
    assert.equal(planned.enabled, false);
    assert.equal(planned.reason, "Not built yet");
    const now = searchCommands(build({ canDelete: false }), "delete")[0];
    assert.equal(now.reason, "Not now");
    const fine = searchCommands(build(), "undo")[0];
    assert.equal(fine.enabled, true);
    assert.equal(fine.reason, null);
  });

  test("menuPaths lists each item's menus, outermost first", () => {
    const paths = menuPaths({ menu: MENU, aliases: ALIASES, label });
    assert.deepEqual(paths.get("export.subtitles_srt"), ["File", "Export transcripts"]);
    assert.deepEqual(paths.get("transcript.prev_stop"), ["Go"]);
    assert.equal(paths.has("export.mix_wav"), false);
  });
});

describe("searchAll", () => {
  const topics = [
    { id: "clip", title: "Clips", body: "A clip is one piece of a recording. Delete removes it." },
    { id: "bus", title: "Buses", body: "Tracks are grouped." },
  ];
  test("an empty query shows the recent commands that still exist, or nothing", () => {
    const records = build();
    const recent = searchAll({
      records,
      topics,
      query: "",
      recent: ["edit.undo", "gone", "app.save"],
    });
    assert.deepEqual(ids(recent.commands), ["edit.undo", "app.save"]);
    assert.deepEqual(recent.topics, []);
    assert.equal(recent.recent, true);
    const nothing = searchAll({ records, topics, query: " ", recent: [] });
    assert.deepEqual(nothing.commands, []);
    assert.deepEqual(nothing.topics, []);
  });

  test("commands first, then help topics matching title or body", () => {
    const found = searchAll({ records: build(), topics, query: "delete" });
    assert.equal(found.commands[0].id, "edit.delete");
    assert.deepEqual(ids(found.topics), ["clip"]);
    assert.equal(found.topics[0].title, "Clips");
  });

  test("about twelve results in all: topics keep their room, commands fill the rest", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({
      id: `c${i}`,
      names: [`Thing ${i}`],
      hints: [],
      synonyms: [],
    }));
    const manyTopics = Array.from({ length: 6 }, (_, i) => ({
      id: `t${i}`,
      title: `Thing topic ${i}`,
      body: "",
    }));
    const found = searchAll({ records: many, topics: manyTopics, query: "thing" });
    assert.equal(found.commands.length + found.topics.length, 12);
    assert.ok(found.topics.length >= 1 && found.topics.length <= 3);
    const fewTopics = searchAll({ records: many, topics: [], query: "thing" });
    assert.equal(fewTopics.commands.length, 12);
  });
});
