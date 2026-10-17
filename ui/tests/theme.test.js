import assert from "node:assert/strict";
import { test } from "node:test";
import { nextTheme, readTheme, THEMES, themeAttribute } from "../theme.js";

test("the theme choice cycles system → light → dark → system", () => {
  assert.deepEqual(THEMES, ["system", "light", "dark"]);
  assert.equal(nextTheme("system"), "light");
  assert.equal(nextTheme("light"), "dark");
  assert.equal(nextTheme("dark"), "system");
  assert.equal(nextTheme("nonsense"), "light", "an unknown stored value counts as system");
});

test("only an explicit choice sets data-theme; system follows the OS", () => {
  assert.equal(themeAttribute("light"), "light");
  assert.equal(themeAttribute("dark"), "dark");
  assert.equal(themeAttribute("system"), null);
  assert.equal(themeAttribute(undefined), null);
});

test("readTheme returns the speaker hues and music, in palette order", () => {
  const values = {
    "--track-0-body": "#000001",
    "--track-0-wave": "#000002",
    "--track-0-edge": "#000003",
    "--track-0-label": "#000004",
    "--track-music-wave": "#00000a",
    "--playhead": "#ff0000",
  };
  const style = { getPropertyValue: (name) => ` ${values[name] ?? ""}` };
  const theme = readTheme(null, () => style);
  assert.equal(theme.palette.length, 7);
  assert.deepEqual(theme.palette[0], {
    fill: "#000001",
    wave: "#000002",
    ink: "#000003",
    label: "#000004",
  });
  assert.equal(theme.palette[6].wave, "#00000a");
  assert.equal(theme.playhead, "#ff0000");
});
