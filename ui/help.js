// Contextual help (WP48): pure helpers, no DOM and no imports, so the
// prototype embeds this file as-is (docs/design/sync-tokens.mjs) and
// `node --test` runs it.
//
// Help content is data: one Markdown file per topic and language under
// ui/help/<lang>/<id>.md, with front matter (id, title, applies-to, commands,
// related). ui/help/index.json lists the topic ids. The help panel
// (help-panel.js) asks `helpChain` what the user is looking at, picks the
// first topic that applies (`topicFor`), and renders its body with
// `renderHelpBody`, which fills in the live shortcuts, so a remapped key shows
// as remapped. GUI-DESIGN.md "Contextual help" has the whole design.

/** The command that opens help. The keymap binds it (helpBindings). */
export const HELP_COMMAND = "help.open";

/** What help can be about. A topic's `applies-to` names one or more of these. */
export const HELP_TARGETS = [
  "timeline",
  "clip",
  "track",
  "bus",
  "transcript",
  "history",
  "candidates",
  "inspector",
  "palette",
  "empty",
  "error",
  "index",
];

const FRONT_LISTS = new Set(["applies-to", "commands", "related"]);

/**
 * "---\nid: clip\napplies-to: [clip]\n---\nBody" -> { id, title, appliesTo, commands, related, body }.
 * Lists are written [a, b]; missing lists are []. Throws on a file without front matter,
 * because a topic nobody can find is worse than a failing test.
 */
export function parseTopic(text) {
  const match = String(text)
    .replace(/\r\n/g, "\n")
    .match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!match) throw new Error("help topic: no front matter");
  const meta = { "applies-to": [], commands: [], related: [] };
  for (const line of match[1].split("\n")) {
    const at = line.indexOf(":");
    if (at < 0 || !line.trim()) continue;
    const key = line.slice(0, at).trim();
    const raw = line.slice(at + 1).trim();
    meta[key] = FRONT_LISTS.has(key)
      ? raw
          .replace(/^\[|\]$/g, "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : raw;
  }
  return {
    id: meta.id ?? "",
    title: meta.title ?? "",
    appliesTo: meta["applies-to"],
    commands: meta.commands,
    related: meta.related,
    body: match[2].trim(),
  };
}

/**
 * What the user is looking at, most specific first, ending in "timeline" and
 * "index" so there is always an answer. `context`: { control, palette, error,
 * empty, panel, inHeaders, selection (count), focusBus, focusTrack }.
 */
export function helpChain(context = {}) {
  const chain = [];
  if (context.control) chain.push(context.control);
  if (context.palette) chain.push("palette");
  if (context.error) chain.push("error");
  if (context.empty) chain.push("empty");
  const object = () => {
    if (context.selection > 0) return "clip";
    if (context.focusBus) return "bus";
    if (context.focusTrack) return "track";
    return null;
  };
  const panel = context.panel ?? "timeline";
  if (context.inHeaders) chain.push(context.focusBus ? "bus" : "track");
  else if (panel === "timeline") {
    if (context.selection > 0) chain.push("clip");
    else if (context.focusBus) chain.push("bus");
  } else if (panel === "inspector") chain.push("inspector", object());
  else chain.push(panel);
  chain.push("timeline", "index");
  return [...new Set(chain.filter(Boolean))];
}

/** The first topic (from `topics`, any order) whose applies-to meets the chain; else null. */
export function topicFor(chain, topics) {
  for (const target of chain) {
    const hit = topics.find((topic) => topic.appliesTo.includes(target));
    if (hit) return hit;
  }
  return null;
}

// -- shortcuts from the keymap ---------------------------------------------------------------------

// Printable keys tried against `match` bindings (zoom's "=" and "+").
const PROBE_KEYS = ["=", "+", "-", "?", "/", ".", ","];

function keyFromCode(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit\d$/.test(code)) return code.slice(5);
  return code;
}

/**
 * The shortcuts a keys.js binding answers to, as "Mod+Alt+Shift+Z" strings
 * (i18n.formatShortcut turns them into ⌥⇧⌘Z or Ctrl+Alt+Shift+Z). A `match`
 * binding is probed with printable keys; it may answer to more than one.
 */
export function bindingShortcuts(binding) {
  const mods = [binding.mod && "Mod", binding.alt && "Alt", binding.shift && "Shift"].filter(
    Boolean,
  );
  let keys = [];
  if (binding.code) keys = [keyFromCode(binding.code)];
  else if (binding.key !== undefined) keys = [binding.key];
  else if (binding.match) {
    keys = PROBE_KEYS.filter((key) =>
      binding.match({
        key,
        code: "",
        shiftKey: Boolean(binding.shift),
        altKey: Boolean(binding.alt),
        ctrlKey: false,
        metaKey: Boolean(binding.mod),
      }),
    );
  }
  // A probed key is named as it prints ("?", "+"): the Shift that makes it is not named twice.
  const named = binding.match ? mods.filter((m) => m !== "Shift") : mods;
  return keys.map((key) => [...named, key].join("+"));
}

/** Which command an action call is: "togglePlay" or "cyclePanel:1" -> a command id. */
export const ACTION_COMMANDS = {
  togglePlay: "transport.play",
  goHome: "panel.home",
  "cyclePanel:1": "panel.next",
  "cyclePanel:-1": "panel.previous",
  toggleView: "view.toggle",
  fitView: "view.fit",
  viewBack: "view.back",
  viewForward: "view.forward",
  "zoomStep:1": "view.zoom_in",
  "zoomStep:-1": "view.zoom_out",
  openHelp: HELP_COMMAND,
};

/**
 * The keymap as data: [{ command, shortcut }], one row per shortcut, in binding
 * order (so the first row of a command is its primary key). `makeBindings` is
 * keys.js coreBindings or helpBindings: each binding is run against a recorder
 * to learn which action it calls. A binding whose action has no command id
 * gives command null, which the drift test refuses.
 */
export function keymapTable(makeBindings, actionCommands = ACTION_COMMANDS) {
  const calls = [];
  const recorder = new Proxy(
    {},
    {
      get:
        (_target, name) =>
        (...args) => {
          calls.push(args.length ? `${String(name)}:${args[0]}` : String(name));
        },
    },
  );
  const rows = [];
  for (const binding of makeBindings(recorder)) {
    calls.length = 0;
    binding.run({ preventDefault() {} });
    const command = actionCommands[calls[0]] ?? actionCommands[calls[0]?.split(":")[0]] ?? null;
    for (const shortcut of bindingShortcuts(binding))
      rows.push({ command, shortcut, call: calls[0] });
  }
  return rows;
}

/** The shortcuts of one command, primary first: ["Shift+Z"] or ["=", "+"]. */
export function shortcutsFor(command, table) {
  return [...new Set(table.filter((row) => row.command === command).map((row) => row.shortcut))];
}

/** The help keys: F1 everywhere (also in a text field), "?" when not typing. */
export function helpBindings(actions) {
  return [
    { code: "F1", inText: true, run: () => actions.openHelp() },
    { match: (event) => event.key === "?", shift: true, run: () => actions.openHelp() },
  ];
}

/** Message keys a command needs: a label (menus, palette) and a one-line hint. */
export const commandKeys = (id) => [`command.${id}.label`, `command.${id}.hint`];

/** Commands that lack a label or hint in any catalog: [{ id, lang, key }]. Empty = no drift. */
export function missingCommandText(ids, catalogs) {
  const missing = [];
  for (const id of ids)
    for (const [lang, catalog] of Object.entries(catalogs))
      for (const key of commandKeys(id))
        if (typeof catalog[key] !== "string" || !catalog[key].trim())
          missing.push({ id, lang, key });
  return missing;
}

// -- rendering ---------------------------------------------------------------------------------------

const escapeHtml = (text) =>
  String(text).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

/**
 * The inline marks a topic body may use, besides **bold** and `code`:
 *   {key:command.id}   the command's current shortcut(s), from the keymap
 *   {run:command.id}   a button that runs the command, labelled with its label
 *   {show:control-id}  "Show me": highlights the control (data-help-id) on screen
 *   [[topic-id]]       a link to another topic, labelled with its title
 *   [[topic-id|text]]  the same link with its own words (for grammar: "the track's [[bus|bus]]")
 */
export const INLINE_MARKS = /\{(key|run|show):([\w.-]+)\}|\[\[([\w-]+)(?:\|([^\]]+))?\]\]/g;

function inline(text, ctx) {
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(INLINE_MARKS)) {
    parts.push(plain(text.slice(last, m.index)));
    last = m.index + m[0].length;
    if (m[3]) {
      parts.push(
        `<a href="#help:${m[3]}" class="help-link" data-topic="${m[3]}">${escapeHtml(m[4] ?? ctx.title(m[3]))}</a>`,
      );
    } else if (m[1] === "key") {
      const keys = ctx.shortcuts(m[2]);
      parts.push(
        keys.length
          ? keys.map((k) => `<kbd>${escapeHtml(ctx.format(k))}</kbd>`).join(" ")
          : `<span class="help-nokey">${escapeHtml(ctx.t("ui.help.no_key"))}</span>`,
      );
    } else if (m[1] === "run") {
      parts.push(
        `<button type="button" class="button small help-run" data-run="${m[2]}">${escapeHtml(ctx.t(`command.${m[2]}.label`))}</button>`,
      );
    } else {
      parts.push(
        `<button type="button" class="button small help-show" data-show="${m[2]}">${escapeHtml(ctx.t("ui.help.show_me"))}</button>`,
      );
    }
  }
  parts.push(plain(text.slice(last)));
  return parts.join("");
}

function plain(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

/**
 * A topic body (a small Markdown subset: "## " headings, "- " lists, paragraphs)
 * as HTML. `ctx`: { t(key), shortcuts(command) -> ["Shift+Z"], format(shortcut)
 * -> "⇧Z", title(topicId) }. All text is escaped; nothing in a topic can inject markup.
 */
export function renderHelpBody(body, ctx) {
  const out = [];
  let para = [];
  let items = null;
  const flush = () => {
    if (para.length) out.push(`<p>${inline(para.join(" "), ctx)}</p>`);
    if (items)
      out.push(`<ul>${items.map((item) => `<li>${inline(item, ctx)}</li>`).join("")}</ul>`);
    para = [];
    items = null;
  };
  for (const line of String(body).split("\n")) {
    if (!line.trim()) flush();
    else if (line.startsWith("## ")) {
      flush();
      out.push(`<h3>${inline(line.slice(3).trim(), ctx)}</h3>`);
    } else if (line.startsWith("- ")) {
      if (para.length) flush();
      items ??= [];
      items.push(line.slice(2).trim());
    } else if (items && /^\s/.test(line)) items[items.length - 1] += ` ${line.trim()}`;
    else {
      if (items) flush();
      para.push(line.trim());
    }
  }
  flush();
  return out.join("\n");
}

/**
 * formatShortcut for help: also names a bare "+" key ("Mod++" -> "⌘+"), which
 * a split on "+" would lose. `format` is i18n.formatShortcut.
 */
export function formatHelpKey(shortcut, format) {
  if (shortcut === "+") return "+";
  if (shortcut.endsWith("++")) return `${format(`${shortcut.slice(0, -2)}+X`).slice(0, -1)}+`;
  return format(shortcut);
}

/** Every {key:}/{run:} command, {show:} control and [[link]] a body refers to. */
export function topicRefs(body) {
  const refs = { commands: new Set(), controls: new Set(), topics: new Set() };
  for (const m of String(body).matchAll(INLINE_MARKS)) {
    if (m[3]) refs.topics.add(m[3]);
    else if (m[1] === "show") refs.controls.add(m[2]);
    else refs.commands.add(m[2]);
  }
  return refs;
}

// -- search ------------------------------------------------------------------------------------------

/** Lower case without accents, for matching only: "Äänitys" and "aanitys" meet. */
export const fold = (text) => String(text).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

/**
 * Rank `items` ({ id, title, text }) for `query`: every word must occur; a word
 * in the title counts 3, at the start of a title word 1 more, in the text 1.
 * Ties go by title. An empty query lists everything by title.
 */
export function searchHelp(items, query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  const scored = [];
  for (const item of items) {
    const title = fold(item.title);
    const text = fold(item.text ?? "");
    let score = 0;
    let all = true;
    for (const word of words) {
      const inTitle = title.includes(word);
      const inText = text.includes(word);
      if (!inTitle && !inText) {
        all = false;
        break;
      }
      score += (inTitle ? 3 : 0) + (inText ? 1 : 0);
      if (new RegExp(`(^|\\s)${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(title)) score++;
    }
    if (all) scored.push({ item, score });
  }
  scored.sort((a, b) => b.score - a.score || a.item.title.localeCompare(b.item.title));
  return scored.map((s) => s.item);
}

// -- loading -----------------------------------------------------------------------------------------

/**
 * A cached loader: load(id, lang) -> topic. A topic missing in `lang` falls back
 * to English and says so (`fallback: true`), so a new topic can ship before its
 * translation without a blank panel. `fetchText(path)` returns the file's text.
 */
export function createTopicLoader(fetchText) {
  const cache = new Map();
  const read = (path) => {
    if (!cache.has(path))
      cache.set(
        path,
        Promise.resolve().then(() => fetchText(path)),
      );
    return cache.get(path);
  };
  return {
    async index() {
      return JSON.parse(await read("help/index.json")).topics;
    },
    async load(id, lang) {
      try {
        return { ...parseTopic(await read(`help/${lang}/${id}.md`)), lang, fallback: false };
      } catch (error) {
        if (lang === "en") throw error;
        return { ...parseTopic(await read(`help/en/${id}.md`)), lang: "en", fallback: true };
      }
    },
  };
}
