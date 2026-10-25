import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// These keys are fixed local input gestures, outside the command keymap.
const ALLOWED = new Map([
  ["ui.keys.layer.shift", "The keymap dialog names the modifier layer itself."],
  ["ui.keys.layer.alt", "The keymap dialog names the modifier layer itself."],
  ["ui.keys.layer.alt+shift", "The keymap dialog names the modifier layer itself."],
  ["ui.drag_mode.now_range", "Fixed modifier for a mouse drag, outside the command keymap."],
  ["ui.drag_mode.now_move", "Fixed modifier for a mouse drag, outside the command keymap."],
  ["cmd.view.wheel_mode.hint", "Fixed wheel and trackpad gesture modifiers."],
  ["ui.wheel_mode.now_zoom", "Fixed wheel and trackpad gesture modifier."],

  ["ui.edge.hint_alone", "Fixed modifiers and cancel gesture during edge dragging."],
  ["ui.edge.hint_roll", "Fixed modifiers and cancel gesture during edge dragging."],
  ["ui.edge.hint_roll_alone", "Fixed modifiers and cancel gesture during edge dragging."],
  ["ui.edge.hint_ripple", "Fixed modifiers and cancel gesture during edge dragging."],
  ["ui.range.hint", "Fixed modifiers and cancel gesture during range dragging."],
  ["ui.range.hint_alt", "Fixed modifiers and cancel gesture during range dragging."],
  ["cmd.view.drag_mode.hint", "Fixed mouse gesture modifiers, outside the command keymap."],

  ["cli.open.serving", "Terminal interrupt belongs to the terminal, not the editor keymap."],
  ["ui.ab.was", "Fixed field reset gesture in the A/B inputs."],
  ["ui.clock.edit_hint", "Fixed commit/cancel gestures in the clock input."],
  ["ui.range.edit_hint", "Fixed commit/cancel gestures in the range input."],
  ["cmd.transcript.find.hint", "Fixed next-result gesture inside the find field."],
  ["ui.placeholders.hover", "Fixed edit gesture on a placeholder."],
  ["ui.automix.opt.speech_plugins.hint", "Fixed selection gesture in a plugin picker."],
  ["ui.automix.opt.music_plugins.hint", "Fixed selection gesture in a plugin picker."],
  ["ui.dialog.safe_hint", "Fixed safe default for confirmation dialogs."],
  ["ui.record.stop_keys", "Fixed recording overlay gestures; playback keys do not stop a take."],
]);

const typedKey =
  /(?:Cmd|Ctrl|Control|Alt|Mod|Shift|Vaihto|Komento)\+|\b(?:Press|press|Paina|paina|with) [A-Z]\b|\b(?:Space|Backspace|Esc|Escape|Tab|Enter|Cmd|Ctrl|Shift|Alt|Vaihto|Välilyönti|Askelpalautin)\b|\b[IOY] (?:and|ja|\()|\b[A-Z](?:-näppäim|:llä|:lla)|\([A-Z]\)|\b[MDGRU] (?:again|opens|mutes|on|links|puts|says|avaa|mykistää|uudelleen|palautus|liittää|palauttaa|kertoo)/;

for (const lang of ["en", "fi"]) {
  test(`${lang}: prose gets command keys from the active keymap`, () => {
    const catalog = JSON.parse(
      readFileSync(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url)),
    );
    const offenders = Object.entries(catalog).filter(([key, value]) => {
      if (key.startsWith("key.") || ALLOWED.has(key)) return false;
      // Enter at the start of an instruction can be the English verb.
      const text = JSON.stringify(value)
        .replace(/\{key:[^}]+\}/g, "")
        .replace(/Enter (?:a |plain |when )/g, "");
      return typedKey.test(text);
    });
    assert.deepEqual(offenders, []);
  });
}
