// WP75: finding a command by typing. Pure (no DOM), shared by Help search (the field in the
// Help menu, the panel in the desktop window) and the command palette, so the two never
// disagree about what a query finds or in which order.
//
// A command is found by its name in the UI language or the other one (people remember the
// English name from other programs, and Finnish users type Finnish), by a word of its one-line
// hint, and by a synonym from command-synonyms.js. Accents and case are ignored and every word
// of the query must match.

import { fold as foldText, searchHelp } from "./help.js";

export const fold = foldText;

/** Matching form: folded, every run of non-letters one space. */
const norm = (text) =>
  fold(text)
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();

/** How many results a search shows in all (commands first, then help topics). */
export const RESULT_LIMIT = 12;
/** Help topics keep this much of the list; commands fill the rest. */
export const TOPIC_LIMIT = 3;

// Tiers, best first. A tier is only ever compared with another tier, never mixed into a
// fuzzy score, so "exact name beats a hint match" holds whatever the lengths are.
const T_EXACT = 100;
const T_PREFIX = 80;
const T_NAME_WORD = 60;
const T_NAME_INSIDE = 50;
// A curated synonym that is exactly what was typed ("remove" for Delete) is better evidence
// than the word turning up somewhere in another command's hint sentence, so it ranks above
// hints; a synonym that merely contains the words stays below them (owner's order otherwise).
const T_SYNONYM_EXACT = 45;
const T_HINT = 40;
const T_SYNONYM = 30;
const T_MIXED = 20;

const wordsOf = (text) => (text ? text.split(" ") : []);
const hasWordStart = (field, token) => wordsOf(field).some((word) => word.startsWith(token));
/** Short tokens must start a word ("as" is not in "massa"); longer ones may sit inside one. */
const hasToken = (field, token, minInside) =>
  hasWordStart(field, token) || (token.length >= minInside && field.includes(token));

/**
 * Does `record` match `query`? -> { tier, score } or null. `record`: { names: [UI-language
 * name, other-language names...], hints: [...], synonyms: [...] }, all plain text.
 */
export function matchCommand(record, query) {
  const q = norm(query);
  if (!q) return null;
  const tokens = q.split(" ");
  const names = record.names.map(norm).filter(Boolean);
  const hints = (record.hints ?? []).map(norm).filter(Boolean);
  const synonyms = (record.synonyms ?? []).map(norm).filter(Boolean);
  const length = names[0]?.length ?? 0;
  // The shorter the name, the nearer it is to what was typed; the UI-language name wins a tie.
  const score = (tier, nameIndex = 0) =>
    tier * 1000 + (nameIndex === 0 ? 20 : 0) - Math.min(length, 400) * 0.5;

  let best = null;
  names.forEach((name, index) => {
    let tier = 0;
    if (name === q) tier = T_EXACT;
    else if (name.startsWith(q)) tier = T_PREFIX;
    else if (tokens.every((token) => hasWordStart(name, token))) tier = T_NAME_WORD;
    else if (tokens.every((token) => hasToken(name, token, 3))) tier = T_NAME_INSIDE;
    if (tier && (!best || score(tier, index) > best.score))
      best = { tier, score: score(tier, index) };
  });
  if (best) return best;

  if (synonyms.includes(q)) return { tier: T_SYNONYM_EXACT, score: score(T_SYNONYM_EXACT) };

  const some = (fields, token, minInside) =>
    fields.some((field) => hasToken(field, token, minInside));
  if (tokens.every((token) => some(names, token, 3) || some(hints, token, 4))) {
    return { tier: T_HINT, score: score(T_HINT) };
  }
  if (synonyms.some((synonym) => tokens.every((token) => hasWordStart(synonym, token)))) {
    return { tier: T_SYNONYM, score: score(T_SYNONYM) };
  }
  if (
    tokens.every(
      (token) => some(names, token, 3) || some(hints, token, 4) || some(synonyms, token, 99),
    )
  ) {
    return { tier: T_MIXED, score: score(T_MIXED) };
  }
  return null;
}

/**
 * Where each command sits in the menus: Map id -> [top-level menu title, submenu titles...],
 * outermost first, the item's own name not included. A command the menu shows through its twin
 * (`aliases`: twin -> shown) gets the twin's place. Commands in no menu are absent.
 */
export function menuPaths({ menu, aliases = {}, label }) {
  const paths = new Map();
  const walk = (items, trail) => {
    for (const entry of items) {
      if (entry.kind === "submenu") walk(entry.items, [...trail, label(entry.labelKey)]);
      else if (
        (entry.kind === "item" || entry.kind === "search") &&
        entry.id &&
        !paths.has(entry.id)
      ) {
        paths.set(entry.id, trail);
      }
    }
  };
  for (const top of menu) walk(top.items, [label(top.labelKey)]);
  for (const [twin, shown] of Object.entries(aliases)) {
    if (paths.has(shown) && !paths.has(twin)) paths.set(twin, paths.get(shown));
  }
  return paths;
}

/**
 * One searchable record per command.
 * entries: the user's keymap (resolveKeymap); menu/aliases: menu-model.js; label(key): the UI
 * language; otherLabels: functions for the other languages (undefined for a key they lack);
 * synonymsFor(id) -> [words]; reasons: { planned, noProject, unavailable } texts for greyed ones.
 */
export function commandRecords({
  entries,
  registry,
  state,
  menu,
  aliases = {},
  label,
  otherLabels = [],
  format,
  platform,
  synonymsFor = () => [],
  reasons = {},
}) {
  const paths = menuPaths({ menu, aliases, label });
  const seen = new Set();
  const records = [];
  for (const entry of entries) {
    if (seen.has(entry.id)) continue;
    seen.add(entry.id);
    const texts = (key) => {
      if (!key) return [];
      const all = [label(key), ...otherLabels.map((other) => other(key))];
      return [...new Set(all.filter((text) => typeof text === "string" && text && text !== key))];
    };
    const names = texts(entry.labelKey);
    if (names.length === 0) names.push(entry.id);
    const path = paths.get(entry.id) ?? null;
    const planned = registry.status(entry.id) !== "ready";
    const enabled = !planned && registry.can(entry.id, state);
    let reason = null;
    if (planned) reason = reasons.planned ?? null;
    else if (!enabled) reason = (state?.project ? reasons.unavailable : reasons.noProject) ?? null;
    const keys = entry.raw.map((combo) => format(combo, platform));
    records.push({
      id: entry.id,
      name: names[0],
      names,
      hint: texts(registry.hintKey(entry.id))[0] ?? "",
      hints: texts(registry.hintKey(entry.id)),
      synonyms: synonymsFor(entry.id),
      keys,
      noKey: keys.length === 0,
      path,
      where: path ? [...path, names[0]].join(" > ") : null,
      paletteOnly: path === null,
      enabled,
      planned,
      reason,
      order: records.length,
    });
  }
  return records;
}

/** Records that match `query`, best first; ties keep the keymap order. Empty query: nothing. */
export function searchCommands(records, query, { limit = Number.POSITIVE_INFINITY } = {}) {
  const rows = [];
  for (const record of records) {
    const match = matchCommand(record, query);
    if (match) {
      // Within a tier, what has a place in the menus and a key is what people mean (Delete, not
      // the fifteenth "Poista ..."); the per-format exports that only the palette has come last.
      const bonus = (record.paletteOnly ? 0 : 15) + (record.noKey ? 0 : 8);
      rows.push({ ...record, tier: match.tier, score: match.score + bonus });
    }
  }
  rows.sort((a, b) => b.score - a.score || a.order - b.order);
  return rows.slice(0, limit);
}

/** The first plain sentence of a help body, without its marks: a one-line gist. */
function gist(body) {
  const line =
    String(body ?? "")
      .split("\n")
      .map((l) => l.trim())
      .find((l) => l && !l.startsWith("#")) ?? "";
  const plain = line
    .replace(/\{(?:key|run|show):[\w.-]+\}/g, "")
    .replace(/\[\[[\w-]+\|([^\]]+)\]\]/g, "$1")
    .replace(/\[\[([\w-]+)\]\]/g, "$1")
    .replace(/[*`]/g, "")
    .trim();
  return plain.length > 110 ? `${plain.slice(0, 107).trimEnd()}…` : plain;
}

/**
 * Everything one typed query finds: { commands, topics, recent }. Commands first (best
 * first), then matching help topics (title and body); about RESULT_LIMIT in all. An empty
 * query lists the recent commands that still exist (`recent`: ids, newest first), or nothing.
 */
export function searchAll({ records, topics = [], query, recent = [], limit = RESULT_LIMIT }) {
  if (!norm(query)) {
    const byId = new Map(records.map((record) => [record.id, record]));
    const commands = [...new Set(recent)]
      .filter((id) => byId.has(id))
      .map((id) => byId.get(id))
      .slice(0, limit);
    return { commands, topics: [], recent: commands.length > 0 };
  }
  const found = searchHelp(
    topics.map((topic) => ({ ...topic, text: topic.body })),
    query,
  )
    .slice(0, TOPIC_LIMIT)
    .map((topic) => ({ id: topic.id, title: topic.title, gist: gist(topic.body) }));
  const commands = searchCommands(records, query, { limit: limit - found.length });
  return { commands, topics: found, recent: false };
}
