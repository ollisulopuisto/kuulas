// docs/GLOSSARY.md (WP74): bus = väylä, group = ryhmä, clip = leike. A banned old word coming
// back in the Finnish catalog or help fails here.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
const catalog = JSON.parse(readFileSync(at("../../src/kuulas/locales/fi.json"), "utf8"));
const text = (value) => (typeof value === "string" ? value : Object.values(value).join(" "));
const BANNED = [/klip/i, /pätk/i, /bussi/i, /bussia/i];

describe("Finnish terminology", () => {
  test("no klippi, pätkä or bussi in the catalog", () => {
    for (const [key, value] of Object.entries(catalog)) {
      for (const word of BANNED) assert.ok(!word.test(text(value)), `${key}: ${text(value)}`);
    }
  });
  test("no klippi, pätkä or bussi in the help topics", () => {
    const dir = at("../help/fi/");
    for (const file of readdirSync(dir).filter((name) => name.endsWith(".md"))) {
      const body = readFileSync(dir + file, "utf8");
      for (const word of BANNED) assert.ok(!word.test(body), `${file}: ${word}`);
    }
  });
  test("a bus is a väylä in every bus command, never a ryhmä", () => {
    for (const key of Object.keys(catalog).filter((k) => /^cmd\.(bus\.|view\..*buses)/.test(k))) {
      assert.ok(!/ryhm/i.test(text(catalog[key])), `${key}: ${catalog[key]}`);
    }
    assert.equal(catalog["cmd.bus.collapse"], "Supista väylä");
    assert.equal(catalog["menu.bus"], "Väylä");
  });
});
