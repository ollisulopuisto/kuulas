// Contextual help (WP48): the pure helpers, the topic files, and the drift checks
// that keep help, the keymap and the catalogs in step.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { registerAppCommands } from "../app-commands.js";
import { registerCandidateCommands } from "../candidate-commands.js";
import { cheatSheetData } from "../cheatsheet.js";
import { createRegistry } from "../commands.js";
import { registerEditCommands } from "../edit-commands.js";
import { PANELS } from "../focus.js";
import {
  commandLabelKey,
  createTopicLoader,
  fold,
  HELP_COMMAND,
  HELP_TARGETS,
  helpChain,
  INLINE_MARKS,
  missingCommandText,
  parseTopic,
  renderHelpBody,
  searchHelp,
  shortcutsFor,
  topicFor,
  topicForCommand,
  topicRefs,
} from "../help.js";
import { formatCombo, resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, menuTargets } from "../menu-model.js";
import { paletteRows } from "../palette.js";
import { CONTEXT_OF_PANEL } from "../shell-keys.js";
import { registerTranscriptCommands } from "../transcript-commands.js";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
const catalog = (lang) =>
  JSON.parse(readFileSync(at(`../../src/kuulas/locales/${lang}.json`), "utf8"));
const CATALOGS = { en: catalog("en"), fi: catalog("fi") };
const INDEX = JSON.parse(readFileSync(at("../help/index.json"), "utf8")).topics;
const topicFile = (lang, id) => at(`../help/${lang}/${id}.md`);
const TOPICS = Object.fromEntries(
  ["en", "fi"].map((lang) => [
    lang,
    INDEX.map((id) => parseTopic(readFileSync(topicFile(lang, id), "utf8"))),
  ]),
);
// The keymap the app has: the default data, and the registry the app builds.
const PLATFORM = "other";
const entriesWith = (overrides = {}) => resolveKeymap(DEFAULT_KEYMAP, overrides, PLATFORM);
const KEYMAP = entriesWith();
const stub = new Proxy({}, { get: () => () => {} });
const REGISTRY = createRegistry();
registerAppCommands(REGISTRY, { actions: stub, app: stub });
registerEditCommands(REGISTRY, { app: stub, t: (key) => key, formatSeconds: String });
registerTranscriptCommands(REGISTRY, { app: stub, t: (key) => key });
registerCandidateCommands(REGISTRY, { app: stub, t: (key) => key });
REGISTRY.planMissing(DEFAULT_KEYMAP.map((entry) => entry.id));
const READY = REGISTRY.ids().filter((id) => REGISTRY.status(id) === "ready");

describe("the keyboard focus model", () => {
  test("every keyboard panel, and the help panel, gives a keymap context", () => {
    for (const panel of PANELS) assert.ok(CONTEXT_OF_PANEL[panel], panel);
    // Help is docked in the sidebar: the timeline's letters and arrows must not fire in it.
    assert.equal(CONTEXT_OF_PANEL.help, "side");
  });

  test("F1 works in every context, so inside the help panel too", () => {
    const entry = DEFAULT_KEYMAP.find((e) => e.id === HELP_COMMAND);
    assert.ok(["global", "text-field"].includes(entry.context));
  });
});

describe("parseTopic", () => {
  test("reads front matter lists and the body", () => {
    const topic = parseTopic(
      "---\nid: clip\ntitle: A clip\napplies-to: [clip, inspector]\ncommands: [edit.split]\n---\nBody.\n",
    );
    assert.deepEqual(topic, {
      id: "clip",
      title: "A clip",
      appliesTo: ["clip", "inspector"],
      commands: ["edit.split"],
      related: [],
      body: "Body.",
    });
  });

  test("a file without front matter is an error, not an empty topic", () => {
    assert.throws(() => parseTopic("Just text"), /front matter/);
  });
});

describe("helpChain: what help is about", () => {
  test("a selected clip on the timeline asks for the clip first", () => {
    assert.deepEqual(helpChain({ panel: "timeline", selection: 2 }), ["clip", "timeline", "index"]);
  });

  test("nothing selected: the timeline", () => {
    assert.deepEqual(helpChain({ panel: "timeline", focusTrack: "t1" }), ["timeline", "index"]);
  });

  test("a track header: the track; a bus row in the headers: the bus", () => {
    assert.equal(helpChain({ inHeaders: true, focusTrack: "t1" })[0], "track");
    assert.equal(helpChain({ inHeaders: true, focusBus: "b1" })[0], "bus");
  });

  test("the inspector names itself, then what it shows", () => {
    assert.deepEqual(helpChain({ panel: "inspector", focusBus: "b1" }).slice(0, 2), [
      "inspector",
      "bus",
    ]);
  });

  test("a focused control, the palette, an error and an empty project come first, in that order", () => {
    assert.deepEqual(
      helpChain({ control: "view-menu", palette: true, error: true, empty: true }).slice(0, 4),
      ["view-menu", "palette", "error", "empty"],
    );
  });

  test("panels name themselves", () => {
    for (const panel of ["transcript", "history", "candidates"])
      assert.equal(helpChain({ panel })[0], panel);
  });

  test("topicFor takes the first target that has a topic", () => {
    const chain = helpChain({ panel: "inspector", selection: 1 });
    assert.equal(topicFor(chain, TOPICS.en).id, "clip"); // no inspector topic yet
    assert.equal(topicFor(["nothing"], TOPICS.en), null);
  });
});

describe("shortcuts come from the keymap data, so remaps show", () => {
  test("a command's keys are its entry's keys, primary first", () => {
    assert.deepEqual(shortcutsFor("view.zoom_in", KEYMAP), ["=", "+"]);
    assert.deepEqual(shortcutsFor("view.fit", KEYMAP), ["Shift+Z"]);
    assert.deepEqual(shortcutsFor("help.keys", KEYMAP), ["?"]);
    assert.deepEqual(shortcutsFor("nope", KEYMAP), []);
  });

  test("help opens on F1 and F1 is not '?', which stays the cheat sheet", () => {
    assert.equal(HELP_COMMAND, "help.open");
    assert.deepEqual(shortcutsFor(HELP_COMMAND, KEYMAP), ["F1"]);
    assert.ok(!shortcutsFor(HELP_COMMAND, KEYMAP).includes("?"));
    assert.equal(DEFAULT_KEYMAP.find((e) => e.id === HELP_COMMAND).context, "text-field");
  });

  test("a remapped key shows as remapped, a freed one as no key", () => {
    assert.deepEqual(shortcutsFor("view.toggle", entriesWith({ "view.toggle": "Alt+V" })), [
      "Alt+V",
    ]);
    assert.deepEqual(shortcutsFor(HELP_COMMAND, entriesWith({ [HELP_COMMAND]: "F3" })), ["F3"]);
    assert.deepEqual(shortcutsFor(HELP_COMMAND, entriesWith({ [HELP_COMMAND]: null })), []);
  });

  test("modifier alternates are their own commands with their own keys", () => {
    assert.deepEqual(shortcutsFor("nav.back", KEYMAP), ["ArrowLeft"]);
    assert.deepEqual(shortcutsFor("nav.back_far", KEYMAP), ["Shift+ArrowLeft"]);
    assert.deepEqual(shortcutsFor("nav.back_fine", KEYMAP), ["Alt+ArrowLeft"]);
    assert.deepEqual(shortcutsFor("view.back", KEYMAP), ["Alt+Z"]);
  });

  test("help formats keys like the cheat sheet does", () => {
    const sheet = cheatSheetData({
      entries: KEYMAP,
      registry: REGISTRY,
      label: (key) => key,
      format: formatCombo,
      platform: PLATFORM,
    });
    const row = sheet.flatMap((group) => group.rows).find((r) => r.id === HELP_COMMAND);
    assert.deepEqual(
      row?.keys,
      shortcutsFor(HELP_COMMAND, KEYMAP).map((k) => formatCombo(k, PLATFORM)),
    );
    assert.ok(row?.keys.length);
  });

  test("help.open is in the registry, always available, and in the palette and the menu", () => {
    assert.equal(REGISTRY.status(HELP_COMMAND), "ready");
    assert.equal(REGISTRY.can(HELP_COMMAND, {}), true);
    assert.equal(REGISTRY.can(HELP_COMMAND, undefined), true);
    const rows = paletteRows({
      entries: KEYMAP,
      registry: REGISTRY,
      state: {},
      query: "",
      label: (key) => key,
      format: formatCombo,
      platform: PLATFORM,
    });
    assert.ok(rows.some((row) => row.id === HELP_COMMAND));
    const ids = menuTargets(MENU);
    assert.ok(ids.includes(HELP_COMMAND));
    assert.ok(ids.includes("help.keys"), "Keyboard shortcuts stays");
  });

  test("a command's label key follows the keymap data", () => {
    for (const entry of DEFAULT_KEYMAP) assert.equal(entry.labelKey, commandLabelKey(entry.id));
  });

  test("drift: every ready command that is bound has a label and a hint in en and fi", () => {
    const bound = DEFAULT_KEYMAP.map((e) => e.id);
    const ids = READY.filter((id) => bound.includes(id));
    assert.ok(ids.length > 40);
    assert.deepEqual(missingCommandText(ids, CATALOGS), []);
    for (const id of ids) assert.equal(REGISTRY.hintKey(id), `cmd.${id}.hint`, id);
  });

  test("missingCommandText names what is missing", () => {
    assert.deepEqual(missingCommandText(["x.y"], { en: { "cmd.x.y": "X" } }), [
      { id: "x.y", lang: "en", key: "cmd.x.y.hint" },
    ]);
  });

  test("topicForCommand: the first topic that lists the command, else null", () => {
    assert.equal(topicForCommand("edit.split", TOPICS.en)?.id, "clip");
    assert.equal(topicForCommand("help.open", TOPICS.en)?.id, "timeline");
    assert.equal(topicForCommand("rename", TOPICS.en)?.id, "track");
    assert.equal(topicForCommand("keymap.reset", TOPICS.en), null);
    assert.equal(topicForCommand(null, TOPICS.en), null);
  });
});

const ctx = {
  t: (key) => ({ "ui.help.show_me": "Show me", "ui.help.no_key": "no key" })[key] ?? key,
  shortcuts: (command) => shortcutsFor(command, KEYMAP),
  format: (shortcut) => formatCombo(shortcut, "mac"),
  title: (id) => `T:${id}`,
};

describe("renderHelpBody", () => {
  test("headings, paragraphs, lists with continued lines", () => {
    const html = renderHelpBody("## Head\n\nOne\ntwo.\n\n- a\n  more\n- b", ctx);
    assert.equal(html, "<h3>Head</h3>\n<p>One two.</p>\n<ul><li>a more</li><li>b</li></ul>");
  });

  test("a heading directly followed by a list, without a blank line", () => {
    assert.equal(
      renderHelpBody("## H\n- a\n- b\nAfter.", ctx),
      "<h3>H</h3>\n<ul><li>a</li><li>b</li></ul>\n<p>After.</p>",
    );
  });

  test("a bare + key keeps its name", () => {
    assert.equal(formatCombo("+", "mac"), "+");
    assert.equal(formatCombo("Mod++", "mac"), "⌘+");
  });

  test("keys are the live shortcuts, formatted; an unbound command says so", () => {
    assert.match(renderHelpBody("{key:view.fit}", ctx), /<kbd>⇧Z<\/kbd>/);
    assert.match(renderHelpBody("{key:edit.cut_track}", ctx), /<kbd>/);
    assert.match(renderHelpBody("{key:no.such}", ctx), /no key/);
  });

  test("links, Show me and Run", () => {
    const html = renderHelpBody("[[clip]] [[bus|väylä]] {show:view-menu} {run:view.fit}", ctx);
    assert.match(html, /data-topic="clip">T:clip<\/a>/);
    assert.match(html, /data-topic="bus">väylä<\/a>/);
    assert.match(html, /data-show="view-menu">Show me</);
    assert.match(html, /data-run="view.fit">cmd.view.fit</);
  });

  test("nothing in a topic can inject markup", () => {
    const html = renderHelpBody('<img src=x onerror="alert(1)"> **b** `c`', ctx);
    assert.doesNotMatch(html, /<img/);
    assert.match(html, /&lt;img/);
    assert.match(html, /<strong>b<\/strong> <code>c<\/code>/);
  });
});

describe("the topic files", () => {
  const controls = new Set(
    [...readFileSync(at("../index.html"), "utf8").matchAll(/data-help-id="([\w-]+)"/g)].map(
      (m) => m[1],
    ),
  );

  test("every indexed topic exists in English and Finnish, named by its id", () => {
    for (const lang of ["en", "fi"])
      for (const id of INDEX) {
        assert.ok(existsSync(topicFile(lang, id)), `${lang}/${id}.md`);
        assert.equal(TOPICS[lang].find((t) => t.id === id)?.id, id);
      }
  });

  test("the six sample topics cover their targets", () => {
    for (const target of ["timeline", "clip", "track", "bus", "transcript", "history"])
      assert.ok(topicFor([target], TOPICS.en)?.appliesTo.includes(target), target);
  });

  test("translations match their source: same targets, commands, links and controls", () => {
    for (const en of TOPICS.en) {
      const fi = TOPICS.fi.find((t) => t.id === en.id);
      assert.ok(fi.title && fi.title !== en.title, `${en.id}: Finnish title`);
      for (const key of ["appliesTo", "commands", "related"])
        assert.deepEqual(fi[key], en[key], `${en.id} ${key}`);
      const [a, b] = [topicRefs(en.body), topicRefs(fi.body)];
      for (const key of ["commands", "controls", "topics"])
        assert.deepEqual([...b[key]].sort(), [...a[key]].sort(), `${en.id} ${key}`);
    }
  });

  test("every target is known, every link resolves, every Show me control is on screen", () => {
    for (const topic of TOPICS.en) {
      for (const target of topic.appliesTo) assert.ok(HELP_TARGETS.includes(target), target);
      const refs = topicRefs(topic.body);
      for (const id of [...topic.related, ...refs.topics]) assert.ok(INDEX.includes(id), id);
      for (const id of refs.controls) assert.ok(controls.has(id), `data-help-id="${id}"`);
    }
  });

  test("every command a topic names is in the registry, with a label and a hint in both languages", () => {
    const ids = new Set();
    for (const topic of TOPICS.en) {
      for (const id of topic.commands) ids.add(id);
      for (const id of topicRefs(topic.body).commands) {
        ids.add(id);
        assert.ok(topic.commands.includes(id), `${topic.id}: list ${id} under commands`);
      }
    }
    for (const id of ids) assert.ok(REGISTRY.has(id), `${id} is not a registered command`);
    assert.deepEqual(missingCommandText([...ids], CATALOGS), []);
  });

  test("no topic names a key by hand: keys come from {key:}", () => {
    const handTyped =
      /\b(F\d{1,2}|Esc|Escape|Ctrl|Cmd|Command|Option|Shift|Alt|Backspace|Return|Enter)\b|[⌘⌥⇧⌃]|<kbd>/;
    for (const lang of ["en", "fi"])
      for (const topic of TOPICS[lang]) {
        // A modifier held while clicking is a mouse gesture, not a key of the keymap.
        const prose = topic.body.replace(INLINE_MARKS, "").replace(/\w+\+(click|napsautus)/gi, "");
        assert.doesNotMatch(prose, handTyped, `${lang}/${topic.id}`);
      }
  });

  test("the help panel's own words exist in both catalogs", () => {
    const keys = Object.keys(CATALOGS.en).filter((k) => k.startsWith("ui.help."));
    assert.ok(keys.length >= 10);
    for (const key of keys) assert.ok(CATALOGS.fi[key], key);
  });
});

describe("searchHelp", () => {
  const items = [
    { id: "a", title: "Väylä", text: "kokoaa raidat" },
    { id: "b", title: "Raita", text: "väylän kisko" },
    { id: "c", title: "Aikajana", text: "zoom" },
  ];

  test("title hits outrank text hits; accents do not matter", () => {
    assert.deepEqual(
      searchHelp(items, "vayla").map((i) => i.id),
      ["a", "b"],
    );
  });

  test("every word must match; an empty query lists all by title", () => {
    assert.deepEqual(searchHelp(items, "raita zoom"), []);
    assert.deepEqual(
      searchHelp(items, " ").map((i) => i.id),
      ["c", "b", "a"],
    );
  });

  test("fold", () => assert.equal(fold("ÄÄNITYS"), "aanitys"));
});

describe("createTopicLoader", () => {
  const files = {
    "help/index.json": '{"topics":["clip","new"]}',
    "help/en/clip.md": "---\nid: clip\ntitle: A clip\n---\nEN",
    "help/fi/clip.md": "---\nid: clip\ntitle: Leike\n---\nFI",
    "help/en/new.md": "---\nid: new\ntitle: New\n---\nEN only",
  };
  const fetched = [];
  const loader = createTopicLoader(async (path) => {
    fetched.push(path);
    if (!(path in files)) throw new Error(`404 ${path}`);
    return files[path];
  });

  test("loads the language asked for, and caches", async () => {
    assert.deepEqual(await loader.index(), ["clip", "new"]);
    assert.equal((await loader.load("clip", "fi")).title, "Leike");
    await loader.load("clip", "fi");
    assert.equal(fetched.filter((p) => p === "help/fi/clip.md").length, 1);
  });

  test("an untranslated topic falls back to English and says so", async () => {
    const topic = await loader.load("new", "fi");
    assert.equal(topic.body, "EN only");
    assert.equal(topic.fallback, true);
  });
});
