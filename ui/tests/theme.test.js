import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DENSITIES,
  densityAttribute,
  nextTheme,
  readTheme,
  THEMES,
  themeAttribute,
} from "../theme.js";

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

test("readTheme resolves the registry once: hues, bus colours and signals", () => {
  const values = {
    "--track-0-body": "#000001",
    "--track-0-body-alt": "#000005",
    "--track-0-wave": "#000002",
    "--track-0-edge": "#000003",
    "--track-0-label": "#000004",
    "--track-music-wave": "#00000a",
    "--bus-1-band": "#0000bb",
    "--playhead": "#ff0000",
    "--signal-selected": "#00ff00",
    "--signal-muted-opacity": "0.4",
    "--signal-gate": "#f6f8f9",
    "--signal-gate-opacity": "0.7",
    "--signal-candidate": "#c8321f",
    "--signal-candidate-fill": "#c8321f20",
  };
  const asked = [];
  const style = {
    getPropertyValue: (name) => {
      asked.push(name);
      return ` ${values[name] ?? ""}`;
    },
  };
  const theme = readTheme(null, () => style);
  assert.equal(theme.palette.length, 7);
  assert.deepEqual(theme.palette[0], {
    fill: "#000001",
    fillAlt: "#000005",
    wave: "#000002",
    ink: "#000003",
    label: "#000004",
  });
  assert.equal(theme.palette[6].wave, "#00000a");
  assert.equal(theme.busBands[0], "#0000bb");
  assert.equal(theme.playhead, "#ff0000");
  assert.equal(theme.selection, "#00ff00");
  assert.equal(theme.mutedOpacity, 0.4);
  assert.equal(theme.gate, "#f6f8f9");
  assert.equal(theme.candidate, "#c8321f");
  assert.equal(theme.candidateFill, "#c8321f20");
  assert.equal(theme.gateOpacity, 0.7);
  assert.equal(new Set(asked).size, asked.length, "every token is read once");
});

test("two densities: comfortable is the default and sets no attribute", () => {
  assert.deepEqual(DENSITIES, ["comfortable", "compact"]);
  assert.equal(densityAttribute("comfortable"), null);
  assert.equal(densityAttribute("compact"), "compact");
  assert.equal(densityAttribute("spacious"), null, "unknown values fall back to the default");
});
