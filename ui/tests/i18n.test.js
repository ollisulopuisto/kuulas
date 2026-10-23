// Unit tests for ui/i18n.js. The catalogs are the real ones the server sends.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import * as i18n from "../i18n.js";

const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));

beforeEach(() => {
  i18n.setCatalogs({ en: catalog("en"), fi: catalog("fi") });
  i18n.setLanguageNow("en");
});

describe("t", () => {
  test("fills placeholders in the current language", () => {
    assert.equal(i18n.t("error.edit.no_clip", { clip_id: "c1" }), "There is no clip c1.");
    i18n.setLanguageNow("fi");
    assert.notEqual(i18n.t("error.edit.no_clip", { clip_id: "c1" }), "There is no clip c1.");
    assert.match(i18n.t("error.edit.no_clip", { clip_id: "c1" }), /c1/);
  });

  test("unknown key falls back to English, then to the key itself, never throws", () => {
    i18n.setCatalogs({ en: { "only.en": "English {x}" }, fi: {} });
    i18n.setLanguageNow("fi");
    assert.equal(i18n.t("only.en", { x: 1 }), "English 1");
    assert.equal(i18n.t("no.such.key"), "no.such.key");
    assert.equal(i18n.t("no.such.key", { a: 1 }), "no.such.key (a=1)");
  });

  test("a missing value stays as written", () => {
    assert.match(i18n.t("error.edit.no_clip", {}), /\{clip_id\}/);
    assert.match(i18n.t("error.edit.no_clip"), /\{clip_id\}/);
  });

  test("plurals follow Intl.PluralRules per language", () => {
    i18n.setCatalogs({
      en: { n: { one: "{count} clip", other: "{count} clips" } },
      fi: { n: { one: "{count} pätkä", other: "{count} pätkää" } },
    });
    assert.equal(i18n.t("n", { count: 1 }), "1 clip");
    assert.equal(i18n.t("n", { count: 0 }), "0 clips");
    assert.equal(i18n.t("n", { count: 2 }), "2 clips");
    i18n.setLanguageNow("fi");
    assert.equal(i18n.t("n", { count: 1 }), "1 pätkä");
    assert.equal(i18n.t("n", { count: 5 }), "5 pätkää");
  });

  test("a plural entry lacking the category uses other", () => {
    i18n.setCatalogs({ en: { n: { other: "{count} things" } }, fi: {} });
    assert.equal(i18n.t("n", { count: 1 }), "1 things");
  });
});

describe("numbers and times", () => {
  test("Finnish decimal comma, English decimal point", () => {
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatNumber(2.5, { digits: 1 }), "2,5");
    assert.equal(i18n.formatDb(-2.5), "−2,5 dB");
    i18n.setLanguageNow("en");
    assert.equal(i18n.formatNumber(2.5, { digits: 1 }), "2.5");
    assert.equal(i18n.formatDb(-2.5), "−2.5 dB");
  });

  test("timecodes carry the locale's decimal separator", () => {
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatTimecode(754.567), "12:34,567");
    assert.equal(i18n.formatTimecode(3723.5), "1:02:03,500");
    assert.equal(i18n.formatTimecode(5.25), "0:05,250");
    i18n.setLanguageNow("en");
    assert.equal(i18n.formatTimecode(754.567), "12:34.567");
  });

  test("timecode rounds to the millisecond without carrying 1000", () => {
    assert.equal(i18n.formatTimecode(59.9996), "1:00.000");
    assert.equal(i18n.formatTimecode(0), "0:00.000");
  });

  test("durations", () => {
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatDuration(125.5), "2:05,5");
    i18n.setLanguageNow("en");
    assert.equal(i18n.formatDuration(125.5), "2:05.5");
  });

  test("absolute times are Helsinki time with the zone named, summer", () => {
    const summer = new Date("2026-07-01T16:45:00Z"); // 19:45 EEST
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatAbsoluteTime(summer), "19.45 (Helsinki)");
    i18n.setLanguageNow("en");
    assert.equal(i18n.formatAbsoluteTime(summer), "7:45 pm Helsinki");
  });

  test("absolute times are Helsinki time with the zone named, winter", () => {
    const winter = new Date("2026-12-01T16:45:00Z"); // 18:45 EET
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatAbsoluteTime(winter), "18.45 (Helsinki)");
    i18n.setLanguageNow("en");
    assert.equal(i18n.formatAbsoluteTime(winter), "6:45 pm Helsinki");
  });

  test("Helsinki midnight and noon in English", () => {
    i18n.setLanguageNow("en");
    assert.equal(i18n.formatAbsoluteTime(new Date("2026-07-01T21:05:00Z")), "12:05 am Helsinki");
    assert.equal(i18n.formatAbsoluteTime(new Date("2026-07-01T09:00:00Z")), "12:00 pm Helsinki");
  });

  test("accepts an ISO string with its offset", () => {
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatAbsoluteTime("2026-07-01T16:45:00Z"), "19.45 (Helsinki)");
  });
});

describe("key names", () => {
  test("Mod is the command key on a Mac and Ctrl elsewhere", () => {
    assert.equal(i18n.formatShortcut("Mod+Z", "mac"), "⌘Z");
    assert.equal(i18n.formatShortcut("Mod+Z", "other"), "Ctrl+Z");
    assert.equal(i18n.formatShortcut("Mod+Shift+Z", "mac"), "⇧⌘Z");
    assert.equal(i18n.formatShortcut("Mod+Shift+Z", "other"), "Ctrl+Shift+Z");
    assert.equal(i18n.formatShortcut("Alt+W", "mac"), "⌥W");
  });

  test("off the Mac the named keys keep their words", () => {
    assert.equal(i18n.formatShortcut("Mod+Backspace", "other"), "Ctrl+Backspace");
    assert.equal(i18n.formatShortcut("Delete", "other"), "Delete");
  });

  test("named keys follow the language", () => {
    assert.equal(i18n.formatShortcut("Space", "other"), "Space");
    i18n.setLanguageNow("fi");
    assert.equal(i18n.formatShortcut("Space", "other"), "Välilyönti");
    assert.equal(i18n.formatShortcut("Mod+Shift+Space", "other"), "Ctrl+Vaihto+Välilyönti");
    assert.equal(i18n.formatShortcut("Mod+Space", "mac"), "⌘Välilyönti");
    assert.equal(i18n.keyName("ArrowLeft", "other"), "←");
    // A Mac names these keys by their glyphs (Backspace is the Mac's Delete key, ⌫).
    for (const [key, glyph] of [
      ["Backspace", "⌫"],
      ["Delete", "⌦"],
      ["Enter", "↩"],
      ["Tab", "⇥"],
      ["Escape", "⎋"],
    ])
      assert.equal(i18n.keyName(key, "mac"), glyph);
    assert.equal(i18n.formatShortcut("Mod+Backspace", "mac"), "⌘⌫");
  });

  test("detectPlatform reads the browser's own words", () => {
    assert.equal(i18n.detectPlatform({ platform: "MacIntel" }), "mac");
    assert.equal(i18n.detectPlatform({ userAgentData: { platform: "macOS" } }), "mac");
    assert.equal(i18n.detectPlatform({ platform: "Win32" }), "other");
    assert.equal(i18n.detectPlatform({}), "other");
  });
});

describe("the language", () => {
  test("detectLanguage takes the first shipped language, else English", () => {
    assert.equal(i18n.detectLanguage({ languages: ["sv-FI", "fi-FI", "en"] }), "fi");
    assert.equal(i18n.detectLanguage({ languages: ["de"] }), "en");
    assert.equal(i18n.detectLanguage({ language: "fi" }), "fi");
    assert.equal(i18n.detectLanguage({}), "en");
  });

  test("switching language needs no reload and tells listeners", async () => {
    const seen = [];
    const off = i18n.onLanguageChange((lang) =>
      seen.push([lang, i18n.t("error.edit.no_selection")]),
    );
    await i18n.setLanguage("fi");
    assert.equal(i18n.getLanguage(), "fi");
    assert.equal(seen.length, 1);
    assert.equal(seen[0][0], "fi");
    assert.equal(seen[0][1], i18n.t("error.edit.no_selection"));
    assert.notEqual(seen[0][1], catalog("en")["error.edit.no_selection"]);
    off();
    await i18n.setLanguage("en");
    assert.equal(seen.length, 1);
  });

  test("setLanguage loads a missing catalog from the server first", async () => {
    i18n.setCatalogs({});
    const asked = [];
    i18n.setCatalogLoader(async (lang) => {
      asked.push(lang);
      return catalog(lang);
    });
    await i18n.setLanguage("fi");
    assert.deepEqual(asked.sort(), ["en", "fi"]);
    assert.match(i18n.t("error.edit.no_clip", { clip_id: "x" }), /x/);
  });

  test("setLanguage asks for the source and the target catalogs together, not in turn", async () => {
    i18n.setCatalogs({});
    const asked = [];
    const release = [];
    i18n.setCatalogLoader(
      (lang) =>
        new Promise((resolve) => {
          asked.push(lang);
          release.push(() => resolve(catalog(lang)));
        }),
    );
    const switching = i18n.setLanguage("fi");
    await Promise.resolve(); // both requests are out before either answer
    assert.deepEqual(asked.sort(), ["en", "fi"]);
    for (const go of release) go();
    await switching;
    assert.equal(i18n.getLanguage(), "fi");
  });

  test("a catalog already on its way is not fetched again", async () => {
    i18n.setCatalogs({ en: catalog("en") });
    const asked = [];
    i18n.setCatalogLoader(async (lang) => {
      asked.push(lang);
      await Promise.resolve();
      return catalog(lang);
    });
    const first = i18n.ensureCatalog("fi"); // e.g. the page warming the browser's language up
    const second = i18n.setLanguage("fi");
    await Promise.all([first, second]);
    assert.deepEqual(asked, ["fi"]);
    assert.equal(i18n.getLanguage(), "fi");
  });

  test("a failed load is forgotten so the next try asks again", async () => {
    i18n.setCatalogs({ en: catalog("en") });
    let calls = 0;
    i18n.setCatalogLoader(async () => {
      calls++;
      if (calls === 1) throw new Error("offline");
      return catalog("fi");
    });
    await assert.rejects(i18n.setLanguage("fi"), /offline/);
    await i18n.setLanguage("fi");
    assert.equal(calls, 2);
    assert.equal(i18n.getLanguage(), "fi");
  });

  test("a language that cannot be loaded changes nothing and says so", async () => {
    i18n.setCatalogs({ en: catalog("en") });
    i18n.setCatalogLoader(async () => {
      throw new Error("offline");
    });
    await assert.rejects(i18n.setLanguage("fi"), /offline/);
    assert.equal(i18n.getLanguage(), "en");
  });

  test("an unshipped language is English", async () => {
    await i18n.setLanguage("sv");
    assert.equal(i18n.getLanguage(), "en");
  });

  test("the document follows the language", async () => {
    const doc = { documentElement: { lang: "" } };
    i18n.setDocument(doc);
    await i18n.setLanguage("fi");
    assert.equal(doc.documentElement.lang, "fi");
    i18n.setDocument(null);
  });
});

describe("another language's text (Help search finds both names)", () => {
  test("tIn reads a loaded catalog without changing the language; a missing one gives undefined", () => {
    assert.equal(i18n.tIn("fi", "cmd.edit.undo"), "Kumoa");
    assert.equal(i18n.getLanguage(), "en");
    assert.equal(i18n.tIn("fi", "no.such.key"), undefined);
    i18n.setCatalogs({ en: { a: "A" } });
    assert.equal(i18n.tIn("fi", "a"), undefined);
  });

  test("ensureCatalog loads a catalog that is missing, once", async () => {
    let loads = 0;
    i18n.setCatalogs({ en: { a: "A" } });
    i18n.setCatalogLoader(async (lang) => {
      loads++;
      return { a: `A in ${lang}` };
    });
    await i18n.ensureCatalog("fi");
    await i18n.ensureCatalog("fi");
    assert.equal(loads, 1);
    assert.equal(i18n.tIn("fi", "a"), "A in fi");
  });
});
