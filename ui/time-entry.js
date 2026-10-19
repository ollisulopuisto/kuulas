// Typing a time like in Final Cut (owner, M1 testing). Pure, no DOM.
// Digits fill in from the RIGHT and the whole timestamp stays visible: 1 is 0:00:01, 110 is
// 0:01:10, 1234 is 0:12:34, 10000 is 1:00:00. Kuulas is audio, so the smallest unit typed this
// way is the second (no frames). A comma or period starts a fraction; its digits then fill
// from the left, up to milliseconds. Backspace removes the last digit.
// A field over 59 ("99" -> 0:00:99) is shown as typed and added up on the jump (99 s).
// Signs, colons, units and pasted timestamps are not handled here: the clock switches to
// plain text for them (time-jump.js).

export const MAX_DIGITS = 8;
export const MAX_FRACTION = 3;

/** Nothing typed yet. `digits` has no leading zeros; `frac` is null until a separator. */
export function emptyEntry() {
  return { digits: "", frac: null };
}

/** True for text that is only digits (a paste that fills in like typing). */
export function isDigits(text) {
  return /^\d+$/.test(text);
}

/** Bare digits as if typed one by one. */
export function entryFromDigits(text) {
  return [...text].reduce((entry, key) => typeKey(entry, key), emptyEntry());
}

/** The entry after one key. Keys that mean nothing here change nothing. */
export function typeKey(entry, key) {
  if (/^\d$/.test(key)) {
    if (entry.frac !== null) {
      return entry.frac.length < MAX_FRACTION ? { ...entry, frac: entry.frac + key } : entry;
    }
    const digits = (entry.digits + key).replace(/^0+/, "");
    return digits.length <= MAX_DIGITS ? { ...entry, digits } : entry;
  }
  if (key === "," || key === ".") {
    return entry.frac === null ? { ...entry, frac: "" } : entry;
  }
  if (key === "Backspace") {
    if (entry.frac !== null) {
      return { ...entry, frac: entry.frac === "" ? null : entry.frac.slice(0, -1) };
    }
    return { ...entry, digits: entry.digits.slice(0, -1) };
  }
  return entry;
}

/** What was typed, as plain text ("12,5"): what the field keeps when it turns to free text. */
export function rawText(entry) {
  return entry.digits + (entry.frac === null ? "" : `,${entry.frac}`);
}

/** The whole timestamp, h:mm:ss with the fraction as typed. `decimal` is "," or ".". */
export function entryText(entry, decimal) {
  const padded = entry.digits.padStart(5, "0");
  const seconds = padded.slice(-2);
  const minutes = padded.slice(-4, -2);
  const hours = padded.slice(0, -4).replace(/^0+(?=\d)/, "");
  const fraction = entry.frac === null ? "" : `${decimal}${entry.frac}`;
  return `${hours}:${minutes}:${seconds}${fraction}`;
}

/** Seconds the entry names; fields over 59 are added up. */
export function entrySeconds(entry) {
  const padded = entry.digits.padStart(5, "0");
  const seconds = Number(padded.slice(-2));
  const minutes = Number(padded.slice(-4, -2));
  const hours = Number(padded.slice(0, -4));
  const fraction = entry.frac ? Number(`0.${entry.frac}`) : 0;
  return hours * 3600 + minutes * 60 + seconds + fraction;
}

// -- the field -------------------------------------------------------------------------------
// What the clock's input holds. `shown` is the time it opened with (untouched); `entry` is the
// digits typed since (null until the first key); `free` is plain text, once a sign, a colon or
// a unit is typed or a full timestamp is pasted: the browser then edits the text, `text` is it.

const FREE_KEYS = /^[+\-−:msMS]$/;

/** The field as it opens: the current time, selected, nothing typed. */
export function openField(shown) {
  return { shown, entry: null, free: false, text: shown };
}

/** What the input shows. */
export function fieldText(field, decimal) {
  if (field.free) return field.text;
  return field.entry ? entryText(field.entry, decimal) : field.shown;
}

/** The text to hand to resolveTime on Enter: plain seconds for digits, the text otherwise. */
export function fieldValue(field) {
  if (field.free) return field.text;
  if (!field.entry) return field.shown;
  return String(Math.round(entrySeconds(field.entry) * 1000) / 1000);
}

/**
 * A key in the field -> { field, handled }. `handled`: the caller must preventDefault and show
 * `fieldText`; false: leave the key to the browser (arrows, copy, editing plain text).
 */
export function fieldKey(field, key, modified = false) {
  if (field.free || modified) return { field, handled: false };
  if (/^\d$/.test(key) || key === "," || key === "." || key === "Backspace" || key === "Delete") {
    const base = field.entry ?? emptyEntry();
    const entry = typeKey(base, key === "Delete" ? "Backspace" : key);
    return { field: { ...field, entry }, handled: true };
  }
  if (FREE_KEYS.test(key)) {
    const typed = field.entry ? rawText(field.entry) : "";
    return { field: { ...field, free: true, text: typed + key }, handled: true };
  }
  // A printable key that is no part of a time is swallowed; the rest (arrows, Tab) is not.
  return { field, handled: key.length === 1 };
}

/** Pasted text: bare digits fill in like typing, anything else is plain text. */
export function fieldPaste(field, pasted) {
  const text = String(pasted).trim();
  if (isDigits(text)) return { ...field, free: false, entry: entryFromDigits(text) };
  return { ...field, free: true, text };
}
