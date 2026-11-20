// Error recovery must lead to a real control, not a former menu layout.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { MENU } from "../menu-model.js";

function pathTo(id, items = MENU, parents = []) {
  for (const item of items) {
    if (item.id === id) return [...parents, `cmd.${id}`];
    const key = item.labelKey;
    const path = pathTo(id, item.items ?? [], key ? [...parents, key] : parents);
    if (path) return path;
  }
  return null;
}

for (const lang of ["en", "fi"]) {
  const catalog = JSON.parse(
    readFileSync(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url), "utf8"),
  );
  test(`${lang}: local transcription errors name the actual installation menu`, () => {
    const path = pathTo("app.orukeet_setup")
      .map((key) => catalog[key].replace(/…$/, ""))
      .join(" > ");
    for (const key of ["error.transcribe.missing_extra", "error.orukeet.no_installation"])
      assert.ok(catalog[key].includes(path), `${key}: ${path}`);
  });
  test(`${lang}: live transcript installation does not promise spoken words`, () => {
    assert.doesNotMatch(catalog["error.orukeet.no_installation"], /hear words/);
  });
  test(`${lang}: stop and playback errors distinguish the available controls`, () => {
    assert.ok(catalog["error.record.stop_gesture"].includes(catalog["ui.record.stop"]));
    assert.doesNotMatch(
      catalog["error.record.stop_gesture"],
      /only from the record view|vain äänitysnäkymän/,
    );
    assert.doesNotMatch(catalog["error.record.no_playback"], /Nothing plays|Mitään ei soiteta/);
  });
}
