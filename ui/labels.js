// Clip labels that say something, and how clips of one recording relate
// (owner, 2026-10-18). Pure: the timeline, the prototype and the tests use
// the same rules. Spec: docs/design/GUI-DESIGN.md, "Clip labels" and
// "Recordings, sessions, speakers". A label is never identity: the content
// hash is.

/**
 * Label templates by available width (px). Tokens: {person} {interview}
 * {file} {take} {in} {out} {words} {part}. The user may change them in
 * settings (WP27/WP35); a template whose tokens are all empty draws nothing.
 */
export const DEFAULT_TEMPLATES = {
  xs: "",
  s: "{person}",
  m: "{person} {take}",
  l: "{person} {take} · {in}–{out}",
  xl: "{person} {take} · {in}–{out} · “{words}”",
};
/** Minimum widths of the tiers; below `s` only the file mark is drawn. */
export const TIERS = [
  ["xl", 400],
  ["l", 170],
  ["m", 100],
  ["s", 48],
  ["xs", 0],
];
const PADDING_PX = 8;
const FIRST_WORDS = 5;

const stem = (name) => String(name ?? "").replace(/\.[^.]+$/, "");

function clock(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/**
 * What we know about a clip, as label tokens. `words` are timeline words
 * ({start, end, text} in project frames). `in`/`out` are on the recording's
 * own clock (the source range), so two clips cut from one file read as
 * consecutive or gapped.
 */
export function labelFacts(project, clip, words = []) {
  const rate = project?.rate || 48_000;
  const media = project?.media?.find((m) => m.id === clip.media) ?? {};
  const file = stem(media.name);
  const person =
    project?.people?.find((p) => p.id === media.person)?.name ||
    project?.interviews?.find((i) => i.id === media.interview)?.title ||
    file;
  const numbers = file.match(/(\d+)(?!.*\d)/);
  const end = clip.start + clip.length;
  const under = words
    .filter((word) => word.start >= clip.start && word.start < end)
    .slice(0, FIRST_WORDS)
    .map((word) => word.text)
    .join(" ");
  return {
    name: clip.name ?? "",
    person,
    interview: project?.interviews?.find((i) => i.id === media.interview)?.title ?? "",
    file,
    take: numbers ? numbers[1] : "",
    in: clock(clip.offset / rate),
    out: clock((clip.offset + clip.length) / rate),
    words: under,
    part: "",
  };
}

function fill(template, facts) {
  return template
    .replace(/\{(\w+)\}/g, (_, token) => String(facts[token] ?? ""))
    .replace(/“”/g, "")
    .replace(/\s*·\s*(?=·|$)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The label for a clip `width` px wide. A manual name (Clip.name) wins
 * whenever it fits. Otherwise the widest tier whose text fits is used,
 * stepping down a tier rather than overflowing. `measure(text)` -> px.
 */
export function clipLabel(facts, width, { measure, templates = DEFAULT_TEMPLATES } = {}) {
  const room = width - PADDING_PX;
  const fits = (text) => measure(text) <= room;
  const start = TIERS.findIndex(([, min]) => width >= min);
  if (facts.name) {
    if (fits(facts.name)) return facts.name;
    return start >= 0 && width >= TIERS.at(-2)[1] ? truncateToFit(facts.name, fits) : "";
  }
  for (let i = Math.max(0, start); i < TIERS.length; i += 1) {
    const text = fill(templates[TIERS[i][0]] ?? "", facts);
    if (text === "") return "";
    if (fits(text)) return text;
  }
  return "";
}

function truncateToFit(text, fits) {
  for (let n = text.length - 1; n > 3; n -= 1) {
    const cut = truncateMiddle(text, n);
    if (fits(cut)) return cut;
  }
  return "";
}

/**
 * Shorten a file name in the middle to about `max` characters, keeping a
 * trailing number whole ("haast…ille_12"): numbers tell takes apart, so they
 * are never cut. Finnish names run long; this keeps both ends readable.
 */
export function truncateMiddle(text, max) {
  if (text.length <= max) return text;
  const tail = text.match(/[^\d]{0,4}\d+$/)?.[0] ?? "";
  const keepEnd = Math.max(tail.length, Math.floor(max / 2));
  const keepStart = Math.max(1, max - keepEnd - 1);
  return `${text.slice(0, keepStart)}…${text.slice(text.length - keepEnd)}`;
}

/** Each clip of a recording, numbered by its position in the source: id -> {n, of}. */
export function recordingParts(project, mediaId) {
  const clips = [];
  for (const track of project?.tracks ?? []) {
    for (const clip of track.clips) if (clip.media === mediaId) clips.push(clip);
  }
  clips.sort((a, b) => a.offset - b.offset || a.start - b.start);
  return new Map(clips.map((clip, i) => [clip.id, { n: i + 1, of: clips.length }]));
}

/** The other clips of the selected clips' recordings, on any track (the "sibling" signal). */
export function siblingsOf(project, selection) {
  const media = new Set();
  for (const track of project?.tracks ?? []) {
    for (const clip of track.clips) if (selection.has(clip.id)) media.add(clip.media);
  }
  const out = new Set();
  if (media.size === 0) return out;
  for (const track of project.tracks) {
    for (const clip of track.clips) {
      if (media.has(clip.media) && !selection.has(clip.id)) out.add(clip.id);
    }
  }
  return out;
}
