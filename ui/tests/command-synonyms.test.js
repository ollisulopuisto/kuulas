// WP75: the synonym list is data; these tests keep it honest. Real commands, real menus and
// the real English and Finnish catalogs, no DOM.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { commandRecords, searchCommands } from "../command-search.js";
import { SYNONYMS, synonymsFor } from "../command-synonyms.js";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, MENU_ALIASES } from "../menu-model.js";

const read = (lang) =>
  JSON.parse(
    readFileSync(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url), "utf8"),
  );
const EN = read("en");
const FI = read("fi");

function records(ui = "en") {
  const registry = createRegistry();
  for (const entry of DEFAULT_KEYMAP) {
    registry.register(entry.id, () => {}, { hintKey: `${entry.labelKey}.hint` });
  }
  const [mine, other] = ui === "en" ? [EN, FI] : [FI, EN];
  return commandRecords({
    entries: resolveKeymap(DEFAULT_KEYMAP, {}, "other"),
    registry,
    state: { project: {} },
    menu: MENU,
    aliases: MENU_ALIASES,
    label: (key) => mine[key] ?? other[key] ?? key,
    otherLabels: [(key) => other[key]],
    format: (combo) => combo,
    platform: "other",
    synonymsFor,
    reasons: {},
  });
}

describe("the synonym list", () => {
  test("names only real commands", () => {
    const ids = new Set(DEFAULT_KEYMAP.map((entry) => entry.id));
    const unknown = Object.keys(SYNONYMS).filter((id) => !ids.has(id));
    assert.deepEqual(unknown, []);
  });

  test("holds plain, non-empty strings, none twice for one command", () => {
    for (const [id, words] of Object.entries(SYNONYMS)) {
      assert.ok(Array.isArray(words) && words.length > 0, id);
      for (const word of words)
        assert.ok(typeof word === "string" && word.trim() === word && word, id);
      assert.equal(
        new Set(words.map((w) => w.toLowerCase())).size,
        words.length,
        `${id} repeats a word`,
      );
    }
  });

  test("the per-format exports share a list", () => {
    assert.ok(synonymsFor("export.mix_flac").includes("render"));
    assert.ok(synonymsFor("export.tracks_mp3").includes("stems"));
    assert.deepEqual(synonymsFor("no.such.command"), []);
  });
});

// A person's words, and where the command they mean must land (position in the results).
const EXPECT = [
  // [query, id, within the first N]
  ["remove", "edit.delete", 6],
  ["erase", "edit.delete", 4],
  ["poista", "edit.delete", 6],
  ["volume", "clip.gain_up", 4],
  ["volume", "clip.gain_down", 4],
  ["gain", "clip.gain_up", 3],
  ["voimakkuus", "clip.gain_up", 4],
  ["mic", "app.automix", 8],
  ["microphone", "track.add", 8],
  ["mikrofoni", "track.add", 8],
  ["mikki", "app.automix", 6],
  ["save as", "app.save_named", 8],
  ["save as", "app.export", 8],
  ["tallenna nimellä", "app.save_named", 4],
  ["avaa aiempi versio", "app.open_earlier_version", 1],
  ["palauta tallennus", "app.open_earlier_version", 3],
  ["earlier version", "app.open_earlier_version", 2],
  ["varmuuskopio", "app.backup_now", 2],
  ["render", "app.export", 5],
  ["bounce", "export.mix_options", 6],
  ["export", "app.export", 4],
  ["vie", "app.export", 6],
  ["stems", "export.tracks_quick", 4],
  ["cut", "edit.cut", 3],
  ["trim", "edit.trim_start", 3],
  ["leikkaa", "edit.cut", 4],
  ["silence", "app.auto_silence", 4],
  ["mute", "track.mute", 4],
  ["hiljennä", "app.auto_silence", 4],
  ["hiljenna", "clip.mute", 6],
  ["subtitles", "export.subtitles_srt", 3],
  ["captions", "export.subtitles_vtt", 4],
  ["speech to text", "app.transcribe", 3],
  ["undo", "edit.undo", 1],
  ["kumoa", "edit.undo", 1],
  ["peru", "edit.undo", 3],
  ["bus", "track.new_bus", 6],
  ["väylä", "track.new_bus", 6],
  ["ryhmä", "edit.group", 4],
  ["shortcuts", "help.keys", 3],
  ["fillers", "candidate.find", 3],
  ["bookmark", "marker.add", 3],
];

describe("what people type finds the command they mean", () => {
  for (const ui of ["en", "fi"]) {
    for (const [query, id, within] of EXPECT) {
      test(`${ui} UI: "${query}" finds ${id} in the first ${within}`, () => {
        const found = searchCommands(records(ui), query).map((row) => row.id);
        const at = found.indexOf(id);
        assert.ok(at >= 0 && at < within, `${id} at ${at} in ${found.slice(0, 10).join(", ")}`);
      });
    }
  }
});
