// The transcript panel's pure parts (WP7): paragraphs, which paragraphs to draw,
// the word under the play cursor, the word selection, and what the delete and cut
// commands send. No DOM here; transcript.js draws what these return.
//
// A word is what GET /api/words gives: { w, spk, person, s, e (frames), track, clip,
// media, index, muted, conf? }. The array is in time order, and the position in it
// is the word's reference for `cut_words`. Never patch it locally: it is derived.

export const PAUSE_SECONDS = 1.5;
/**
 * View > "Break paragraphs at pauses over": the choices, by id (the id is what is
 * remembered per user and what the commands are named after). 3 s is the default: at
 * 1.5 s a thinking pause already splits a speaker's turn into many short paragraphs.
 */
export const PAUSE_CHOICES = [
  { id: "1_5", seconds: PAUSE_SECONDS },
  { id: "3", seconds: 3 },
  { id: "6", seconds: 6 },
  { id: "never", seconds: Number.POSITIVE_INFINITY },
];
export const DEFAULT_PAUSE_CHOICE = "3";
/** A pause shorter than this is not worth a marker between paragraphs. */
export const MARKER_MIN_SECONDS = 1;

/** The stored choice if it is one of ours, else the default (the value is not trusted). */
export function pauseChoiceId(stored) {
  return PAUSE_CHOICES.some((choice) => choice.id === stored) ? stored : DEFAULT_PAUSE_CHOICE;
}

/** The pause length, in seconds, that splits paragraphs for a choice id. */
export function pauseSecondsOf(id) {
  return PAUSE_CHOICES.find((choice) => choice.id === pauseChoiceId(id)).seconds;
}

/** Words below this confidence are dotted (the transcripts do not carry one yet). */
export const LOW_CONFIDENCE = 0.5;
const SCAN_BACK = 16;

/** The name a paragraph carries: the mapped person, else the track's speaker, else its name. */
export function speakerName(track, trackById, people = {}, person = "") {
  const named = person ? people[person] : "";
  if (named) return named;
  const found = trackById.get(track);
  return found?.speaker || found?.name || track;
}

/**
 * Paragraphs: a new one whenever the track changes or the pause since the previous
 * word is longer than `pauseSeconds`. A paragraph is a slice of `words`
 * (first..last, inclusive), so drawing one never copies words.
 */
export function buildParagraphs(
  words,
  { rate, tracks = [], people = {}, pauseSeconds = PAUSE_SECONDS },
) {
  const trackById = new Map(tracks.map((track) => [track.id, track]));
  const pause = pauseSeconds * rate;
  const out = [];
  let open = null;
  words.forEach((word, i) => {
    const previous = open ? words[i - 1] : null;
    if (!open || word.track !== open.track || word.s - previous.e > pause) {
      open = {
        id: `p${i}`,
        first: i,
        last: i,
        track: word.track,
        name: speakerName(word.track, trackById, people, word.person),
        start: word.s,
        end: word.e,
        chars: 0,
      };
      out.push(open);
    }
    open.last = i;
    open.end = Math.max(open.end, word.e);
    open.chars += word.w.length + 1;
  });
  return out;
}

/**
 * The silences to show between paragraphs: Map of paragraph index -> { start, end,
 * seconds }, for a paragraph that follows the same track's previous paragraph (a
 * pause split it, not a speaker change) after at least MARKER_MIN_SECONDS of silence.
 * `start`/`end` (frames) run from the previous word's end to this paragraph's first word.
 */
export function pauseMarkers(words, paragraphs, rate) {
  const out = new Map();
  for (let index = 1; index < paragraphs.length; index++) {
    const p = paragraphs[index];
    const previous = words[p.first - 1];
    if (!previous || previous.track !== p.track) continue;
    const start = previous.e;
    const end = words[p.first].s;
    const seconds = (end - start) / rate;
    if (seconds >= MARKER_MIN_SECONDS) out.set(index, { start, end, seconds });
  }
  return out;
}

/** Which paragraph holds word `i` (binary search); -1 for none. */
export function paragraphOf(paragraphs, i) {
  let lo = 0;
  let hi = paragraphs.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (i < paragraphs[mid].first) hi = mid - 1;
    else if (i > paragraphs[mid].last) lo = mid + 1;
    else return mid;
  }
  return -1;
}

/**
 * The word being spoken at `frame`: the latest-starting word with s <= frame < e, or -1
 * in a pause. Binary search for the start, then a short look back, since words of two
 * speakers overlap.
 */
export function wordAtTime(words, frame) {
  let lo = 0;
  let hi = words.length - 1;
  let at = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].s <= frame) {
      at = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  for (let i = at; i >= 0 && i > at - SCAN_BACK; i--) if (words[i].e > frame) return i;
  return -1;
}

/** The last word that has started by `frame` (0 before the first): where to scroll to in a pause. */
export function wordBefore(words, frame) {
  let lo = 0;
  let hi = words.length - 1;
  let at = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].s <= frame) {
      at = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return words.length === 0 ? -1 : at;
}

// -- which paragraphs to draw -------------------------------------------------------------

/** A paragraph's height before it is measured: its wrapped lines plus its gap. */
export function estimateHeight(paragraph, { charsPerLine, lineHeight, gap }) {
  const lines = Math.max(1, Math.ceil(paragraph.chars / Math.max(1, charsPerLine)));
  return lines * lineHeight + gap;
}

/** Prefix sums: offsets[i] is the top of paragraph i, offsets[n] the whole height. */
export function offsetsOf(heights) {
  const offsets = new Array(heights.length + 1);
  offsets[0] = 0;
  for (let i = 0; i < heights.length; i++) offsets[i + 1] = offsets[i] + heights[i];
  return offsets;
}

/**
 * The paragraphs to draw: those touching [scrollTop - margin, scrollTop + viewHeight +
 * margin). Returns { from, to } (to is exclusive); an empty list gives 0..0.
 */
export function visibleRange(offsets, scrollTop, viewHeight, margin) {
  const count = offsets.length - 1;
  if (count <= 0) return { from: 0, to: 0 };
  const top = scrollTop - margin;
  const bottom = scrollTop + viewHeight + margin;
  // from: the last paragraph that starts at or before `top`
  let lo = 0;
  let hi = count - 1;
  let from = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (offsets[mid] <= top) {
      from = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  // to: the first paragraph that starts at or after `bottom`
  lo = from;
  hi = count;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (offsets[mid] < bottom) lo = mid + 1;
    else hi = mid;
  }
  return { from, to: Math.max(lo, from + 1) };
}

// -- the word cursor and the selection --------------------------------------------------------

/** { cursor, anchor }: the cursor is the word you are on; the selection runs anchor..cursor. */
export const noSelection = () => ({ cursor: -1, anchor: null });

/** The selected word indices, ascending; empty without a selection. */
export function selectedIndices(sel) {
  if (!sel || sel.anchor === null || sel.cursor < 0) return [];
  const lo = Math.min(sel.anchor, sel.cursor);
  const hi = Math.max(sel.anchor, sel.cursor);
  return Array.from({ length: hi - lo + 1 }, (_, k) => lo + k);
}

/** [lo, hi] of the selection, or null. */
export function selectionBounds(sel) {
  if (!sel || sel.anchor === null || sel.cursor < 0) return null;
  return [Math.min(sel.anchor, sel.cursor), Math.max(sel.anchor, sel.cursor)];
}

/**
 * The selected words as in/out marks: the earliest start and latest end of the run, so the
 * range shows on the timeline (where it can be fine-tuned). Null without a usable selection.
 */
export function selectionFrames(words, sel) {
  const bounds = selectionBounds(sel);
  if (!bounds || bounds[0] < 0 || bounds[1] >= words.length) return null;
  let inPoint = Number.POSITIVE_INFINITY;
  let outPoint = Number.NEGATIVE_INFINITY;
  for (let i = bounds[0]; i <= bounds[1]; i += 1) {
    inPoint = Math.min(inPoint, words[i].s);
    outPoint = Math.max(outPoint, words[i].e);
  }
  return { inPoint, outPoint };
}

/** A plain click or a plain arrow: the cursor goes to `to`, nothing is selected. */
export const placeCursor = (to) => ({ cursor: to, anchor: null });

/**
 * Esc on the transcript with a word range selected: collapse it to the cursor and stop there
 * (owner, 2026-10-22: one layer per press). The key is stopped so the escape order (goHome) does
 * not also clear the clips and marks; the next Esc continues it. Returns whether it took the key.
 */
export function transcriptEscape(event, sel, setSelection) {
  if (event.key !== "Escape" || sel.anchor === null) return false;
  event.preventDefault();
  event.stopPropagation();
  setSelection(placeCursor(sel.cursor));
  return true;
}

/** Shift+click, drag, Shift+arrow: extend from the anchor (the cursor's old place if none). */
export function extendTo(sel, to) {
  const anchor = sel.anchor ?? (sel.cursor >= 0 ? sel.cursor : to);
  return { cursor: to, anchor };
}

/** Select exactly one word (double-click). */
export const selectWord = (i) => ({ cursor: i, anchor: i });

/** The source range a transcript correction can replace, or null for a mixed/gapped pick. */
export function correctableWordRange(words, indices) {
  if (indices.length === 0) return null;
  const picked = [...indices].sort((a, b) => a - b);
  const first = words[picked[0]];
  if (!first?.media || !Number.isInteger(first.index)) return null;
  for (let n = 0; n < picked.length; n++) {
    const word = words[picked[n]];
    if (
      !word ||
      word.media !== first.media ||
      word.index !== first.index + n ||
      word.spk !== first.spk ||
      word.person !== first.person
    )
      return null;
  }
  return { media: first.media, start: first.index, end: first.index + picked.length - 1 };
}

/**
 * The selection a right-click on word `i` (-1: none) works on: the picked words if `i` is one
 * of them, else just that word. With no word and nothing picked, null (no menu).
 */
export function rightClickPick(selection, i) {
  const picked = selectedIndices(selection);
  if (i < 0) return picked.length > 0 ? selection : null;
  return picked.includes(i) ? selection : selectWord(i);
}

/**
 * Where a key takes the cursor: one word, a paragraph start/end (Home/End), or a
 * paragraph (ArrowUp/ArrowDown = the previous/next paragraph's first word). Clamped.
 */
export function moveCursor(cursor, key, { count, paragraphs }) {
  if (count === 0) return -1;
  const at = Math.min(count - 1, Math.max(0, cursor < 0 ? 0 : cursor));
  switch (key) {
    case "ArrowRight":
      return cursor < 0 ? 0 : Math.min(count - 1, at + 1);
    case "ArrowLeft":
      return cursor < 0 ? 0 : Math.max(0, at - 1);
    case "ArrowDown":
    case "ArrowUp": {
      const p = paragraphOf(paragraphs, at);
      const next = Math.min(paragraphs.length - 1, Math.max(0, p + (key === "ArrowDown" ? 1 : -1)));
      return paragraphs[next].first;
    }
    case "Home":
      return paragraphs[Math.max(0, paragraphOf(paragraphs, at))].first;
    case "End":
      return paragraphs[Math.max(0, paragraphOf(paragraphs, at))].last;
    default:
      return at;
  }
}

/**
 * What a drag from word `from` to word `to` selects, in the order of the array:
 * a drag against the reading direction selects the same words.
 */
export const dragSelection = (from, to) => ({ cursor: to, anchor: from });

/**
 * Whether the pop-up over the selection shows. It hides while a word is being corrected, when
 * nothing is picked, and while the pointer drags the selection: the pop-up sits on the words the
 * drag is still passing over, so it comes back on release.
 */
export function popShown({ picked, editing, dragging }) {
  return picked.length > 0 && !editing && !dragging;
}

// -- delete and cut ------------------------------------------------------------------------------

/** The tracks that spoke the selected words, in order of first appearance. */
export function ownerTracks(words, indices) {
  return [...new Set(indices.map((i) => words[i]?.track).filter(Boolean))];
}

/**
 * The stretch to soft-cut on one track for the selected words: from the first to the
 * last of that track's selected words, each side extended to the middle of the pause to
 * that track's neighbouring word (as the ripple cut does, so one natural pause is left),
 * and to the word itself at the ends of the track's speech.
 */
export function deleteSpan(words, indices, track) {
  const mine = indices.filter((i) => words[i]?.track === track);
  if (mine.length === 0) return null;
  const first = Math.min(...mine.map((i) => words[i].s));
  const last = Math.max(...mine.map((i) => words[i].e));
  let before = null;
  let after = null;
  for (const word of words) {
    if (word.track !== track) continue;
    if (word.e <= first && (before === null || word.e > before)) before = word.e;
    if (word.s >= last && (after === null || word.s < after)) after = word.s;
  }
  const start = before === null ? first : Math.floor((before + first) / 2);
  const end = after === null ? last : Math.floor((last + after) / 2);
  return end > start ? { start, end } : null;
}

/**
 * The edit for Backspace: one `mute_range` per speaker (their own track only, the sync
 * group left alone), or null when there is nothing to delete.
 */
export function deleteWordsPlan(words, indices) {
  const edits = [];
  for (const track of ownerTracks(words, indices)) {
    const span = deleteSpan(words, indices, track);
    if (span) {
      edits.push({
        op: "mute_range",
        args: { ...span, track_ids: [track] },
      });
    }
  }
  return edits.length === 0 ? null : edits;
}

/**
 * The stretch X removes for these words, in frames: the same range the server's
 * `transcript.cut_range` computes (each side to the middle of the pause to the
 * neighbouring word, the word itself at the ends of the programme). Null for none.
 */
export function cutRange(words, indices) {
  if (indices.length === 0) return null;
  const first = Math.min(...indices.map((i) => words[i].s));
  const last = Math.max(...indices.map((i) => words[i].e));
  let before = null;
  let after = null;
  for (const word of words) {
    if (word.e <= first && (before === null || word.e > before)) before = word.e;
    if (word.s >= last && (after === null || word.s < after)) after = word.s;
  }
  return {
    start: before === null ? first : Math.floor((before + first) / 2),
    end: after === null ? last : Math.floor((last + after) / 2),
  };
}

/** The command for X: `cut_words` with the selected indices, or null. */
export function cutWordsPlan(indices) {
  return indices.length === 0 ? null : { name: "cut_words", args: { indices: [...indices] } };
}

// -- the crosstalk preview ------------------------------------------------------------------------

/** The word refs POST /api/cut-preview wants for the selected indices. */
export const wordRefs = (words, indices) =>
  indices.map((i) => ({ track: words[i].track, clip: words[i].clip, index: words[i].index }));

/** Word key: how the preview names a word, so its answer maps back to array indices. */
export const wordKey = (word) => `${word.track}|${word.clip}|${word.index}`;

/** The indices (into `words`) of the other speakers' words the preview says go too. */
export function alsoRemovedIndices(words, preview) {
  if (!preview?.other_words?.length) return new Set();
  const wanted = new Set(preview.other_words.map(wordKey));
  const out = new Set();
  words.forEach((word, i) => {
    if (wanted.has(wordKey(word))) out.add(i);
  });
  return out;
}

/**
 * The summary as parts: [{ track, name, words, seconds }] for every other track the cut
 * touches. A track with words reports its words; one with only audio (music, a muted
 * ramble) reports the seconds of audio. Empty: nothing else is removed.
 */
export function summaryParts(preview, { rate, nameOf }) {
  if (!preview) return [];
  const wordsBy = new Map();
  for (const word of preview.other_words ?? []) {
    wordsBy.set(word.track, (wordsBy.get(word.track) ?? 0) + 1);
  }
  const secondsBy = new Map();
  for (const [track, ranges] of Object.entries(preview.audio ?? {})) {
    secondsBy.set(track, ranges.reduce((sum, [a, b]) => sum + (b - a), 0) / rate);
  }
  const tracks = [...new Set([...wordsBy.keys(), ...secondsBy.keys()])];
  return tracks
    .map((track) => ({
      track,
      name: nameOf(track),
      words: wordsBy.get(track) ?? 0,
      seconds: secondsBy.get(track) ?? 0,
    }))
    .filter((part) => part.words > 0 || part.seconds > 0);
}

/**
 * The timeline's collateral band: the stretch and the tracks whose audio or words go
 * with the cut. Null when nothing else goes.
 */
export function collateralBand(preview) {
  if (!preview) return null;
  const tracks = [
    ...new Set([
      ...(preview.other_words ?? []).map((word) => word.track),
      ...Object.keys(preview.audio ?? {}),
    ]),
  ];
  if (tracks.length === 0) return null;
  return { range: [preview.span[0], preview.span[1]], tracks };
}

/**
 * Everything that decides a word's `muted` flag on the server (transcript.py): the tracks'
 * mute and solo, the buses' mute, each clip's mute and the size of a track's gate. Taken
 * from a server answer, never from a provisional project. "" for no project.
 */
export function mutedInputsKey(project) {
  if (!project) return "";
  const gateSize = (gate) => (Array.isArray(gate) ? gate.length : gate ? 1 : 0);
  return JSON.stringify([
    (project.tracks ?? []).map((track) => [
      track.id,
      Boolean(track.mute),
      Boolean(track.solo),
      track.bus ?? "",
      gateSize(track.gate),
      (track.clips ?? []).filter((clip) => clip.muted).map((clip) => clip.id),
    ]),
    (project.buses ?? []).map((bus) => [bus.id, Boolean(bus.mute)]),
  ]);
}

/**
 * Should the words be fetched now? The head alone is not enough: the server merges
 * a run of mute/unmute clicks on one track into one history step (session.py
 * _coalesce_key), so the head stays put while the flags change. The key of the inputs
 * that decide the flags is compared too, against what the last fetch was started for.
 * Called again when a fetch ends, so a change that came in flight is repeated.
 */
export function shouldLoadWords({ head, key, fetchedHead, fetchedKey, fetching, force = false }) {
  if (fetching || head === null) return false;
  return force || head !== fetchedHead || key !== fetchedKey;
}

/**
 * The recordings that have a transcript: the server's list (words anywhere on the
 * timeline, heard or not) plus the recordings of the words shown. The panel draws only
 * heard words, so a recording whose every word is muted would otherwise look untranscribed
 * and be offered for transcription again.
 */
export function transcribedMedia(state, words) {
  return [...new Set([...(state?.transcribed ?? []), ...words.map((word) => word.media)])];
}
