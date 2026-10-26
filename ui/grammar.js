// The visual grammar: every signal kuulas draws on a clip, a lane or a
// group, in one place. Each signal uses ONE channel, and each channel
// carries ONE meaning, so a glance reads the same way everywhere:
//
//   hue, tone   identity: who speaks (track hue), which file (tone step)
//   opacity     audibility: not heard because of solo, unused
//   fill        silence: a FILLED waveform sounds, an OUTLINE-only one is silent (muted clip,
//               stretch closed by Auto-Silence); never hatched (docs/design/SILENCE-VISUALS.md)
//   weight      selection: the 2 px neutral outline
//   dash        reality: dashed = not real audio yet (placeholder, pending)
//   scope       edit scope: what the next time-shifting edit takes along
//   pattern     absent or maybe absent: cut candidate, damaged, removed
//   strip       role: speech, music (top edge; off on the timeline)
//   badge       facts: sync group, drift, free, file mark, takes, label
//   cap         level: clipping
//   seam        joins: clean split (hairline) or jump cut (notch)
//   bar         change since a checkpoint (WP31): added
//   spine, band grouping: the bus a track belongs to
//   line        attachment: connected clip tether (WP19b)
//   notch       annotation: a note or marker on the clip
//   bracket     relation: corner brackets on clips of the same recording
//   ribbon      activity: who sounds when, inside a collapsed bus
//   enclosure   unity: one outline round the members of a clip group
//
// Colours are never written here: each signal names its semantic tokens
// (tokens.css), and resolvePalette reads them once per theme change for the
// canvases. CSS uses the same token names. Spec: docs/design/GUI-DESIGN.md,
// "The visual grammar"; tests: ui/tests/grammar.test.js.

export const CHANNELS = [
  "hue",
  "tone",
  "opacity",
  "fill",
  "weight",
  "dash",
  "scope",
  "pattern",
  "strip",
  "badge",
  "cap",
  "seam",
  "bar",
  "spine",
  "band",
  "line",
  "notch",
  "bracket",
  "ribbon",
  "enclosure",
];

export const SPEAKER_HUE_COUNT = 6;
/** Eight bus hues (nested buses need more than four); the letter is the twin. */
export const BUS_HUES = 8;
export const LABEL_COLOURS = 6;
const TRACK_HUE_NAMES = [
  ...Array.from({ length: SPEAKER_HUE_COUNT }, (_, i) => String(i)),
  "music",
];
const TRACK_PARTS = ["wave", "body", "body-alt", "edge", "label"];
const BUS_PARTS = ["spine", "band", "text"];

const trackTokens = (part) => TRACK_HUE_NAMES.map((n) => `--track-${n}-${part}`);
const busTokens = () =>
  Array.from({ length: BUS_HUES }, (_, i) => BUS_PARTS.map((p) => `--bus-${i + 1}-${p}`)).flat();

/**
 * Every signal. `priority`: lower is more important. `always`: never dropped
 * by pickSignals (identity, selection, alarms); the rest compete for at most
 * three places on a clip. `twin`: how the signal reads without colour.
 * `status`: "built" in the editor today, "prototype" (designed and shown in
 * the prototype, built with its work package), "planned".
 */
export const SIGNALS = [
  {
    id: "speaker",
    channel: "hue",
    meaning: "identity",
    priority: 0,
    atRest: true,
    always: true,
    tokens: [
      ...trackTokens("wave"),
      ...trackTokens("body"),
      ...trackTokens("edge"),
      ...trackTokens("label"),
    ],
    twin: "track name in the header and file name on the clip; the header swatch is a short pill",
    when: "always",
    key: "",
    status: "built",
  },
  {
    id: "file-zebra",
    channel: "tone",
    meaning: "identity",
    priority: 0,
    atRest: true,
    always: true,
    tokens: trackTokens("body-alt"),
    twin: "file mark chip and file name on each clip; a seam marks every change of file",
    when: "neighbouring clips on one track come from different files",
    key: "",
    status: "built",
  },
  {
    id: "selected",
    channel: "weight",
    meaning: "selection",
    priority: 0,
    atRest: true,
    always: true,
    tokens: ["--signal-selected"],
    twin: "2 px outline (shape), plus the inspector shows the clip",
    when: "the clip is selected",
    key: "click, Tab, Mod+A",
    status: "built",
  },
  {
    id: "muted",
    channel: "fill",
    meaning: "silence",
    priority: 1,
    atRest: true,
    always: true,
    tokens: ["--signal-silent-body"],
    twin: "the waveform loses its fill and shows only its outline, the body toned down a little; no lock (that is the one difference from a gated stretch); the context menu says 'Unmute'",
    when: "the clip is muted",
    key: "N",
    status: "built",
  },
  {
    id: "unheard",
    channel: "opacity",
    meaning: "audibility",
    priority: 1,
    atRest: true,
    always: true,
    tokens: ["--signal-unheard-opacity"],
    twin: "header says 'not heard: solo' in its tooltip and the M button turns dashed",
    when: "another track is soloed, or this track is muted",
    key: "Shift+S, Shift+M",
    status: "prototype",
  },
  {
    id: "gate",
    channel: "fill",
    meaning: "silence",
    priority: 1,
    atRest: true,
    always: true,
    tokens: ["--signal-silent-body", "--signal-gate-lock"],
    twin: "the waveform under the stretch is outline only (like a muted clip) and a padlock sits at the left of its visible part (the shape is the cue, the amber colour the twin); no hatch, so clip borders stay visible; hover says 'Mic closed by Auto-Silence' and offers 'Open this stretch'",
    when: "Auto-Silence: one merged gate per track closes the mic (WP44); a per-lane toggle shows or hides it",
    key: "Alt+Mod+P runs Auto-Silence",
    status: "prototype",
  },
  {
    id: "clip_group",
    channel: "enclosure",
    meaning: "unity",
    priority: 2,
    atRest: true,
    tokens: ["--signal-group"],
    twin: "one 1 px rounded outline just outside all the members (across tracks), plus the group badge on each clip; unlike the selection (2 px on the clip's own border) and a closed stretch's dashed amber edges",
    when: "clips grouped with Edit > Group (Clip.group)",
    key: "Mod+G groups, Shift+Mod+G ungroups",
    status: "built",
  },
  {
    id: "ungated",
    channel: "badge",
    meaning: "facts",
    priority: 2,
    atRest: true,
    tokens: ["--signal-gate-open"],
    twin: "an open padlock after the clip name (the pair of the gate's closed padlock); its waveform is simply filled; the context menu says 'Let Auto-Silence gate the clips again'",
    when: "the clip keeps the mic open (Clip.ungated): Auto-Silence never closes under it",
    key: "context menu: Keep the mic open under clips",
    status: "built",
  },
  {
    id: "unused",
    channel: "opacity",
    meaning: "audibility",
    priority: 6,
    atRest: false,
    whenNotAtRest: "only in the clip bin and on cards",
    always: false,
    tokens: ["--signal-unused-opacity"],
    twin: "the clip bin lists it under 'not in the programme'",
    when: "clip bin and cards: material not used in the open edit",
    key: "",
    status: "planned",
  },
  {
    id: "placeholder",
    channel: "dash",
    meaning: "reality",
    priority: 0,
    atRest: true,
    always: true,
    tokens: ["--signal-placeholder"],
    twin: "dashed outline, no waveform, the script text in italics inside",
    when: "narration placeholder (WP43)",
    key: "T",
    status: "prototype",
  },
  {
    id: "provisional",
    channel: "dash",
    meaning: "reality",
    priority: 2,
    atRest: false,
    whenNotAtRest: "only after 150 ms without the engine's confirmation",
    always: true,
    tokens: ["--signal-provisional"],
    twin: "short dashes (2 on, 2 off) on the outline",
    when: "an edit is shown but the engine has not confirmed it after 150 ms",
    key: "",
    status: "prototype",
  },
  {
    id: "partner",
    channel: "scope",
    meaning: "edit scope",
    priority: 2,
    atRest: false,
    whenNotAtRest: "only while a clip is selected",
    always: true,
    tokens: ["--signal-partner"],
    twin: "dashed 1 px outline inset 2 px, neutral",
    when: "a clip is selected: its sync partners that a move takes along (WP19a)",
    key: "A toggles all tracks / selected tracks",
    status: "prototype",
  },
  {
    id: "candidate",
    channel: "pattern",
    meaning: "absence",
    priority: 1,
    atRest: true,
    always: true,
    tokens: ["--signal-candidate", "--signal-candidate-fill"],
    twin: "diagonal stripes across the group's lanes and a 'cut?' flag in the ruler",
    when: "an open cut candidate (WP18)",
    key: "D, Alt+Down / Alt+Up, Enter, Backspace",
    status: "prototype",
  },
  {
    id: "soft-cut",
    channel: "pattern",
    meaning: "absence",
    priority: 1,
    atRest: true,
    always: true,
    tokens: ["--signal-soft-cut", "--signal-soft-cut-fill"],
    twin: "hatch plus a solid 2 px edge at each end in the cut colour, and the word 'cut' when wide enough; the context menu says 'Restore'",
    when: "Delete (Backspace): audio removed in place, the gap kept, restorable; 'Show cuts' (on by default) hides or shows them",
    key: "Backspace (Delete); Restore from the menu or the palette",
    status: "prototype",
  },
  {
    id: "damaged",
    channel: "pattern",
    meaning: "absence",
    priority: 0,
    atRest: true,
    always: true,
    tokens: ["--signal-damaged", "--signal-damaged-fill"],
    twin: "cross-hatch, a '!' badge with the word 'damaged', and the reason on hover",
    when: "media that cannot be read there (plays silence)",
    key: "",
    status: "prototype",
  },
  {
    id: "removed",
    channel: "pattern",
    meaning: "absence",
    priority: 1,
    atRest: false,
    whenNotAtRest: "only in the changes view (WP31)",
    always: true,
    tokens: ["--signal-removed", "--signal-removed-fill"],
    twin: "a ghost outline with hatch and a '−' glyph",
    when: "changes view (WP31): audio in A that is gone in B",
    key: "Alt+Mod+D, Alt+Down / Alt+Up",
    status: "planned",
  },
  {
    id: "role",
    channel: "strip",
    meaning: "role",
    priority: 9,
    atRest: false,
    whenNotAtRest: "only in the clip bin and on cards",
    always: false,
    tokens: ["--role-speech", "--role-music"],
    twin: "strip pattern: solid speech, dotted music; role icon in the header",
    when: "off on the timeline (the header says it); on in the clip bin and cards",
    key: "",
    status: "prototype",
  },
  {
    id: "drift",
    channel: "badge",
    meaning: "facts",
    priority: 0,
    atRest: true,
    always: true,
    tokens: ["--signal-drift", "--signal-drift-text"],
    twin: "solid badge with the offset in text ('−312 ms'), cause on hover",
    when: "undecided drift from the sync group (WP19a)",
    key: "R resyncs, U frees",
    status: "prototype",
  },
  {
    id: "clipping",
    channel: "cap",
    meaning: "level",
    priority: 2,
    atRest: true,
    always: false,
    tokens: ["--signal-clipping"],
    twin: "a 3 px block on top of the clipped column (shape) and a line in the inspector",
    when: "a peak at or above −0.1 dBFS",
    key: "",
    status: "built",
  },
  {
    id: "file-mark",
    channel: "badge",
    meaning: "facts",
    priority: 3,
    atRest: true,
    always: false,
    tokens: ["--signal-file-mark", "--signal-file-mark-text"],
    twin: "two characters from the content hash; the same on every track",
    when: "a track holds clips from more than one file",
    key: "",
    status: "built",
  },
  {
    id: "free",
    channel: "badge",
    meaning: "facts",
    priority: 4,
    atRest: true,
    always: false,
    tokens: ["--signal-free"],
    twin: "outlined badge with an unlinked-chain glyph and '+300 ms · free'",
    when: "a clip freed from its sync group on purpose (U)",
    key: "U",
    status: "prototype",
  },
  {
    id: "seam-jump",
    channel: "seam",
    meaning: "joins",
    priority: 4,
    atRest: true,
    always: false,
    tokens: ["--signal-seam"],
    twin: "a small V notch top and bottom at the join (shape)",
    when: "two clips of one file meet but audio between them was removed; hover offers 'Put back' (a ripple cut)",
    key: "Tab stops here",
    status: "built",
  },
  {
    id: "takes",
    channel: "badge",
    meaning: "facts",
    priority: 5,
    atRest: true,
    always: false,
    tokens: ["--signal-takes"],
    twin: "stacked top-right corner (two offset edges) and '2/3'",
    when: "a take set (WP19e)",
    key: "none yet (WP19e)",
    status: "prototype",
  },
  {
    id: "note",
    channel: "notch",
    meaning: "annotation",
    priority: 5,
    atRest: true,
    always: false,
    tokens: ["--signal-note"],
    twin: "a triangular notch in the top edge; the text on hover. On the ruler (WP19h): a pennant for a marker, a square flag for a chapter, a bar for a region, with the name beside it",
    when: "a note on the clip's audio, or a marker, chapter or region on the timeline",
    key: "M adds a marker, Alt+M makes a region from the in-out range",
    status: "prototype",
  },
  {
    id: "sync",
    channel: "badge",
    meaning: "facts",
    priority: 6,
    atRest: false,
    whenNotAtRest: "only on the selected clip and its partners",
    always: false,
    tokens: ["--signal-sync"],
    twin: "chain glyph and the group number ('⛓ 1')",
    when: "on the selected clip and its partners only; never on every clip",
    key: "Y marks in sync",
    status: "prototype",
  },
  {
    id: "tether",
    channel: "line",
    meaning: "attachment",
    priority: 6,
    atRest: true,
    always: false,
    tokens: ["--signal-tether"],
    twin: "a thin line from the clip's start down to its anchor, ending in a dot",
    when: "a connected clip (WP19b)",
    key: "Alt+Mod+C",
    status: "planned",
  },
  {
    id: "label",
    channel: "badge",
    meaning: "facts",
    priority: 7,
    atRest: true,
    always: false,
    tokens: Array.from({ length: LABEL_COLOURS }, (_, i) => `--label-${i + 1}`),
    twin: "a square flag in the top-right corner; its name on hover and in the inspector",
    when: "the user gave the clip a label colour (never set automatically)",
    key: "",
    status: "planned",
  },
  {
    id: "seam-split",
    channel: "seam",
    meaning: "joins",
    priority: 8,
    atRest: true,
    always: false,
    tokens: ["--signal-seam"],
    twin: "a 1 px hairline (shape)",
    when: "two clips of one file meet with nothing removed between them",
    key: "",
    status: "built",
  },
  {
    id: "added",
    channel: "bar",
    meaning: "change",
    priority: 1,
    atRest: false,
    whenNotAtRest: "only in the changes view (WP31)",
    always: true,
    tokens: ["--signal-added"],
    twin: "a 3 px bar on the clip's left and right edges and a '+' glyph",
    when: "changes view (WP31): audio in B that was not in A",
    key: "Alt+Mod+D, Alt+Down / Alt+Up",
    status: "planned",
  },
  {
    id: "bus",
    channel: "spine",
    meaning: "grouping",
    priority: 0,
    atRest: true,
    always: true,
    tokens: busTokens(),
    twin: "letter badge (A, B, C) in the bus header, the transcript and the inspector",
    when: "a track is on a bus: the spine runs from the bus header through its tracks",
    key: "",
    status: "built",
  },
  {
    id: "bus-band",
    channel: "band",
    meaning: "grouping",
    priority: 0,
    atRest: true,
    always: true,
    tokens: [],
    twin: "drawn only together with the spine (the band is a tint of the spine's colour)",
    when: "behind a bus's header and member lanes",
    key: "",
    status: "built",
  },
  {
    id: "sibling",
    channel: "bracket",
    meaning: "relation",
    priority: 3,
    atRest: false,
    whenNotAtRest: "while a clip is selected, or hovered with Alt held",
    always: true,
    tokens: ["--signal-sibling"],
    twin: "corner brackets on every other clip of the same recording, a tick in the overview, and 'part 2 of 5' in the inspector",
    when: "the selected clip's recording has other clips in the edit (any track)",
    key: "Alt+hover",
    status: "built",
  },
  {
    id: "collateral",
    channel: "pattern",
    meaning: "absence",
    priority: 0,
    atRest: false,
    whenNotAtRest: "only while words are selected in the transcript",
    always: true,
    tokens: ["--signal-collateral", "--signal-collateral-fill"],
    twin: "other speakers' words struck through with a wavy underline, 'also removed' in the word pop-up, the stretch hatched and the affected clips outlined on the timeline",
    when: "a transcript selection whose cut would also remove other tracks' words or audio",
    key: "X cuts on all tracks (ripple); Backspace deletes on this speaker only, keeping the gap",
    status: "built",
  },
  {
    id: "ribbons",
    channel: "ribbon",
    meaning: "activity",
    priority: 0,
    atRest: true,
    always: true,
    tokens: [],
    twin: "one strip per member in its position (top to bottom = header order), filled where the track has sound; the tooltip names the track and clip",
    when: "a collapsed bus with two or more members (one member keeps its summed waveform)",
    key: "Alt+Mod+← collapses, Alt+Mod+→ expands",
    status: "prototype",
  },
  {
    id: "preview",
    channel: "dash",
    meaning: "reality",
    priority: 0,
    atRest: false,
    whenNotAtRest: "only while the Compare bar or the Auto-Silence options panel is open",
    always: true,
    tokens: ["--signal-preview", "--signal-preview-fill"],
    twin: "Compare: a dashed top band over the compared range with the slot letter ('A', 'B') in it, and the Compare bar itself. Auto-Silence options: the waveform of each stretch that would close is outlined in the preview teal with dashed top and bottom edges (no veil, no hatch), the lane says 'preview' at its left edge, and the panel lists the numbers",
    when: "a Compare preview is playing, or the Auto-Silence options panel shows what it would close: nothing is committed until 'Keep this one' or Accept",
    key: "` flips, 1–4 pick a slot, Enter keeps, Esc discards",
    status: "prototype",
  },
];

/** Every semantic token the UI and the canvases may use. tokens.test.js checks
 *  that each is defined in every shipped theme, and that nothing else is. */
export const SEMANTIC_TOKENS = [
  "--surface-app",
  "--surface-lane",
  "--surface-lane-current",
  "--surface-panel",
  "--surface-raised",
  "--surface-sunken",
  "--surface-hover",
  "--surface-active",
  "--surface-scrim",
  "--border-subtle",
  "--border",
  "--border-strong",
  "--text",
  "--text-secondary",
  "--text-tertiary",
  "--text-disabled",
  "--text-on-accent",
  "--accent",
  "--accent-hover",
  "--accent-text",
  "--accent-subtle",
  "--focus-ring",
  "--warn",
  "--warn-text",
  "--warn-subtle",
  "--danger",
  "--danger-text",
  "--danger-subtle",
  "--ok",
  "--ok-text",
  "--shadow-raised",
  "--shadow-dialog",
  "--playhead",
  "--play-start",
  "--selection-range",
  "--gain-line",
  "--automation-line",
  "--ruler-text",
  "--ruler-tick",
  "--signal-selected",
  "--signal-clip-edge",
  "--signal-partner",
  "--signal-muted-hatch",
  "--signal-muted-opacity",
  "--signal-unheard-opacity",
  "--signal-unused-opacity",
  "--signal-placeholder",
  "--signal-provisional",
  "--signal-candidate",
  "--signal-candidate-fill",
  "--signal-soft-cut",
  "--signal-soft-cut-fill",
  "--signal-gate",
  "--signal-gate-opacity",
  "--signal-silent-body",
  "--signal-silent-hatch",
  "--signal-gate-lock",
  "--signal-gate-open",
  "--signal-group",
  "--signal-damaged",
  "--signal-damaged-fill",
  "--signal-removed",
  "--signal-removed-fill",
  "--signal-added",
  "--signal-drift",
  "--signal-drift-text",
  "--signal-clipping",
  "--signal-file-mark",
  "--signal-file-mark-text",
  "--signal-free",
  "--signal-seam",
  "--signal-takes",
  "--signal-note",
  "--signal-sync",
  "--signal-tether",
  "--signal-sibling",
  "--signal-collateral",
  "--signal-collateral-fill",
  "--signal-preview",
  "--signal-preview-fill",
  "--role-speech",
  "--role-music",
  ...TRACK_PARTS.flatMap((part) => trackTokens(part)),
  ...busTokens(),
  ...Array.from({ length: LABEL_COLOURS }, (_, i) => `--label-${i + 1}`),
];

/** Tokens holding a number (opacity), not a colour. */
export const NUMBER_TOKENS = SEMANTIC_TOKENS.filter((name) => name.endsWith("-opacity"));
/** Tokens holding a shadow list: themes may not override them from a manifest. */
const SHADOW_TOKENS = ["--shadow-raised", "--shadow-dialog"];

export function signalTokens() {
  return [...new Set(SIGNALS.flatMap((s) => s.tokens))];
}

const SIGNAL_BY_ID = new Map(SIGNALS.map((s) => [s.id, s]));
export const signal = (id) => SIGNAL_BY_ID.get(id);

/**
 * Which of a clip's active signals to draw. `always` signals are all kept;
 * the others compete for `max` places by priority (registry order breaks
 * ties). `hidden` is what did not fit: draw it as a "+2" badge, list it on hover.
 */
export function pickSignals(active, max = 3) {
  const known = active.map((id) => SIGNAL_BY_ID.get(id)).filter(Boolean);
  const order = (a, b) => a.priority - b.priority || SIGNALS.indexOf(a) - SIGNALS.indexOf(b);
  const ranked = known.filter((s) => !s.always).sort(order);
  const shown = [...known.filter((s) => s.always).sort(order), ...ranked.slice(0, max)];
  return { shown: shown.map((s) => s.id), hidden: ranked.slice(max).map((s) => s.id) };
}

/**
 * What the join between two clips on one track is, or null when they do not
 * touch. "split": same file, continuous in the source (a plain split: a
 * hairline). "jump": same file, audio between them removed (a notch; where
 * the auto crossfade goes). "file": a different file starts.
 */
export function seamKind(left, right) {
  if (left.start + left.length !== right.start) return null;
  if (left.media !== right.media) return "file";
  return left.offset + left.length === right.offset ? "split" : "jump";
}

/**
 * Body tone step (0 or 1) per clip id: the step flips whenever a clip comes
 * from a different file than the clip before it in time, so neighbours from
 * different files never share a tone. Clips of one file in a row keep theirs.
 */
export function zebraSteps(clips) {
  const steps = new Map();
  let step = 0;
  let previous = null;
  for (const clip of [...clips].sort((a, b) => a.start - b.start)) {
    if (previous !== null && clip.media !== previous) step = 1 - step;
    steps.set(clip.id, step);
    previous = clip.media;
  }
  return steps;
}

// No 0/O, 1/I, 2/Z, 5/S, 8/B: a mark is read at 10 px.
const MARK_ALPHABET = "ACDEFHJKLMNPRTUVWXY34679";
/** Two stable characters naming a file, from its SHA-256 (hex). */
export function fileMark(sha256) {
  if (!sha256 || sha256.length < 4) return "";
  const n = Number.parseInt(sha256.slice(0, 4), 16);
  const base = MARK_ALPHABET.length;
  return MARK_ALPHABET[Math.floor(n / base) % base] + MARK_ALPHABET[n % base];
}

/** File marks only where they tell files apart: a track with 2+ files. */
export function needsFileMark(track) {
  return new Set((track?.clips ?? []).map((clip) => clip.media)).size > 1;
}

/**
 * A collapsed bus with several members shows activity ribbons, one strip per
 * member in its own hue, instead of a summed waveform that hides who talks
 * when (owner, 2026-10-18). Strips are 8 px up to six members, thinner beyond
 * (never under 3 px); the row is capped at 48 px. One member: null (keep the
 * summed waveform).
 */
export function ribbonLayout(members) {
  if (members <= 1) return null;
  const strip = members <= 6 ? 8 : Math.max(3, Math.floor(40 / members));
  return { strip, height: Math.min(48, members * strip + 8) };
}

/** Bus hue number (1..BUS_HUES) per bus id, by bus order. */
export function busHues(project) {
  const hues = new Map();
  (project?.buses ?? []).forEach((bus, i) => {
    hues.set(bus.id, (i % BUS_HUES) + 1);
  });
  return hues;
}

/** The bus badge: A, B, … Z, AA, AB … (the non-colour twin of the bus hue). */
export function busLetter(index) {
  let n = index;
  let out = "";
  do {
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return out;
}

const camel = (name) =>
  name.replace(/^--(signal-)?/, "").replace(/-(\w)/g, (_, c) => c.toUpperCase());

/**
 * Everything the canvases draw with, read once per theme change.
 * `get(name)` returns a token's computed value (theme.js passes
 * getComputedStyle). Never call this per frame.
 */
export function resolvePalette(get) {
  const read = (name) => String(get(name) ?? "").trim();
  const tracks = TRACK_HUE_NAMES.map((n) => ({
    wave: read(`--track-${n}-wave`),
    body: read(`--track-${n}-body`),
    bodyAlt: read(`--track-${n}-body-alt`),
    edge: read(`--track-${n}-edge`),
    label: read(`--track-${n}-label`),
  }));
  const buses = Array.from({ length: BUS_HUES }, (_, i) => ({
    spine: read(`--bus-${i + 1}-spine`),
    band: read(`--bus-${i + 1}-band`),
    text: read(`--bus-${i + 1}-text`),
  }));
  const signals = {};
  const numbers = {};
  const marks = {};
  const surfaces = {};
  const roles = {};
  const labels = [];
  const done = new Set([
    ...TRACK_PARTS.flatMap((p) => trackTokens(p)),
    ...busTokens(),
    ...SHADOW_TOKENS,
  ]);
  for (const name of SEMANTIC_TOKENS) {
    if (done.has(name)) continue;
    const value = read(name);
    if (NUMBER_TOKENS.includes(name)) numbers[camel(name)] = Number.parseFloat(value);
    else if (name.startsWith("--signal-")) signals[camel(name)] = value;
    else if (name.startsWith("--role-")) roles[camel(name.replace("--role-", "--"))] = value;
    else if (name.startsWith("--label-")) labels.push(value);
    else if (/^--(playhead|play-start|selection-range|gain-line|automation-line|ruler-)/.test(name))
      marks[camel(name)] = value;
    else surfaces[camel(name)] = value;
  }
  return {
    tracks,
    buses,
    signals,
    numbers,
    marks,
    surfaces,
    roles,
    labels,
    font: read("--font-ui") || "system-ui, sans-serif",
    mono: read("--font-mono") || "ui-monospace, monospace",
  };
}

const HEX = /^#[0-9a-f]{6}$/i;
const RGBA = /^rgb\(\s*\d{1,3}\s+\d{1,3}\s+\d{1,3}\s*(\/\s*(0|1|0?\.\d+))?\s*\)$/i;

/**
 * A user theme from its manifest (docs/design/GUI-DESIGN.md, "Themes"):
 *   { name, base: "light" | "dark", density?: "comfortable" | "compact",
 *     tokens: { "--semantic-token": "#rrggbb" | "rgb(r g b / a)" | "0.35" } }
 * Returns { errors, attribute, base, density, css }. `css` is empty when
 * anything is wrong: a theme is applied whole or not at all.
 */
export function themeFromManifest(manifest) {
  const errors = [];
  const name = String(manifest?.name ?? "").trim();
  if (!name) errors.push("name is missing");
  const base = manifest?.base;
  if (base !== "light" && base !== "dark") errors.push(`base must be light or dark, not ${base}`);
  const density = manifest?.density ?? "comfortable";
  if (density !== "comfortable" && density !== "compact") errors.push(`unknown density ${density}`);
  const lines = [];
  for (const [token, raw] of Object.entries(manifest?.tokens ?? {})) {
    const value = String(raw).trim();
    if (!SEMANTIC_TOKENS.includes(token) || SHADOW_TOKENS.includes(token)) {
      errors.push(`${token} is not a theme token`);
      continue;
    }
    const isNumber = NUMBER_TOKENS.includes(token);
    const valid = isNumber ? /^(0|1|0?\.\d+)$/.test(value) : HEX.test(value) || RGBA.test(value);
    if (!valid) {
      errors.push(`${token}: ${value} is not a ${isNumber ? "number from 0 to 1" : "colour"}`);
      continue;
    }
    lines.push(`  ${token}: ${value};`);
  }
  const attribute = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const css = errors.length
    ? ""
    : `:root[data-user-theme="${attribute}"] {\n${lines.join("\n")}\n}\n`;
  return { errors, attribute, base, density, css };
}
