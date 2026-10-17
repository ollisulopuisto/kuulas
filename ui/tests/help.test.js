// Contextual help (WP48): the pure helpers, the topic files, and the drift checks
// that keep help, the keymap and the catalogs in step.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  bindingShortcuts,
  createTopicLoader,
  fold,
  formatHelpKey,
  HELP_COMMAND,
  HELP_TARGETS,
  helpBindings,
  helpChain,
  keymapTable,
  missingCommandText,
  parseTopic,
  renderHelpBody,
  searchHelp,
  shortcutsFor,
  topicFor,
  topicRefs,
} from "../help.js";
import { coreBindings } from "../keys.js";

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
// The keymap the app binds today: keys.js core bindings plus the help keys.
const KEYMAP = [
  ...keymapTable(coreBindings),
  ...keymapTable(helpBindings),
  { command: "track.rename", shortcut: "F2" },
];

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

describe("shortcuts come from the keymap, so remaps show", () => {
  test("bindings become shortcut strings", () => {
    assert.deepEqual(bindingShortcuts({ code: "KeyZ", shift: true }), ["Shift+Z"]);
    assert.deepEqual(bindingShortcuts({ code: "KeyX", mod: true, alt: true }), ["Mod+Alt+X"]);
    assert.deepEqual(bindingShortcuts({ code: "Space" }), ["Space"]);
  });

  test("a match binding is probed; the printed key needs no Shift in its name", () => {
    assert.deepEqual(shortcutsFor("view.zoom_in", KEYMAP), ["=", "+"]);
    assert.deepEqual(shortcutsFor(HELP_COMMAND, KEYMAP), ["F1", "?"]);
  });

  test("a remapped key shows as remapped", () => {
    const remapped = keymapTable((actions) => [
      { code: "KeyV", alt: true, run: () => actions.toggleView() },
    ]);
    assert.deepEqual(shortcutsFor("view.toggle", remapped), ["Alt+V"]);
  });

  test("drift: every bound key has a command id", () => {
    const unknown = KEYMAP.filter((row) => !row.command);
    assert.deepEqual(unknown, [], "add the action to ACTION_COMMANDS in help.js");
  });

  test("drift: every bound command has a label and a hint in English and Finnish", () => {
    const ids = [...new Set(KEYMAP.map((row) => row.command))];
    assert.deepEqual(missingCommandText(ids, CATALOGS), []);
  });

  test("missingCommandText names what is missing", () => {
    assert.deepEqual(missingCommandText(["x.y"], { en: { "command.x.y.label": "X" } }), [
      { id: "x.y", lang: "en", key: "command.x.y.hint" },
    ]);
  });
});

const ctx = {
  t: (key) => ({ "ui.help.show_me": "Show me", "ui.help.no_key": "no key" })[key] ?? key,
  shortcuts: (command) => shortcutsFor(command, KEYMAP),
  format: (shortcut) => shortcut.replace("Shift+", "⇧"),
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
    const format = (s) => s.replace("Mod+", "⌘");
    assert.equal(formatHelpKey("+", format), "+");
    assert.equal(formatHelpKey("Mod++", format), "⌘+");
    assert.equal(formatHelpKey("Mod+Z", format), "⌘Z");
  });

  test("keys are the live shortcuts, formatted; an unbound command says so", () => {
    assert.match(renderHelpBody("{key:view.fit}", ctx), /<kbd>⇧Z<\/kbd>/);
    assert.match(renderHelpBody("{key:edit.split}", ctx), /no key/);
  });

  test("links, Show me and Run", () => {
    const html = renderHelpBody("[[clip]] [[bus|väylä]] {show:view-menu} {run:view.fit}", ctx);
    assert.match(html, /data-topic="clip">T:clip<\/a>/);
    assert.match(html, /data-topic="bus">väylä<\/a>/);
    assert.match(html, /data-show="view-menu">Show me</);
    assert.match(html, /data-run="view.fit">command.view.fit.label</);
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

  test("every command a topic names has a label and a hint in both languages", () => {
    const ids = new Set();
    for (const topic of TOPICS.en) {
      for (const id of topic.commands) ids.add(id);
      for (const id of topicRefs(topic.body).commands) {
        ids.add(id);
        assert.ok(topic.commands.includes(id), `${topic.id}: list ${id} under commands`);
      }
    }
    assert.deepEqual(missingCommandText([...ids], CATALOGS), []);
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
