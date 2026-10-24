import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { resolvePalette, SEMANTIC_TOKENS } from "../grammar.js";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
function themeValues(selector, start) {
  const section = css.slice(css.indexOf(start));
  const open = section.indexOf(`${selector} {`);
  const close = section.indexOf("\n}", open);
  return new Map(
    [...section.slice(open, close).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, key, value]) => [
      key,
      value.trim(),
    ]),
  );
}
const themes = [
  themeValues(":root", "== 2. semantic roles: light"),
  themeValues(':root[data-theme="dark"]', "chosen explicitly"),
];

test("clip edges have a separate neutral color from every waveform hue", () => {
  assert.ok(SEMANTIC_TOKENS.includes("--signal-clip-edge"));
  for (const theme of themes) {
    const resolved = resolvePalette((name) => theme.get(name) ?? "#000000");
    assert.ok(resolved.signals.clipEdge);
    for (const track of resolved.tracks) assert.notEqual(resolved.signals.clipEdge, track.wave);
  }
});
