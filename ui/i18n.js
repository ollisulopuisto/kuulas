// Translated text and locale-aware formatting for the UI (WP33b, R39).
//
// One catalog serves Python and the UI: src/kuulas/locales/<lang>.json, sent
// by GET /api/locales/<lang>. English is the source; a key missing in the
// current language falls back to English, then to the key itself, because
// text is made on error paths and a second failure there would hide the first.
//
// Nothing here touches the DOM except an optional <html lang> update, so the
// module runs under `node --test`. Other modules call t(...) when they render
// and listen with onLanguageChange(...) to render again after a switch; there
// is no reload.

export const SOURCE = "en";
export const LANGUAGES = ["en", "fi"];
// Absolute times are Helsinki time whatever the browser's zone (the owner's rule).
const ZONE = "Europe/Helsinki";

const catalogs = {};
let current = SOURCE;
let loader = async (lang) => {
  const response = await fetch(`/api/locales/${lang}`);
  if (!response.ok) throw new Error(`/api/locales/${lang}: ${response.status}`);
  return response.json();
};
let doc = null;
const events = new EventTarget();

// -- the language ------------------------------------------------------------

/** "fi-FI", "fi_FI.UTF-8" -> "fi"; a language kuulas does not ship -> "en". */
export function normalise(lang) {
  const primary = String(lang ?? "")
    .toLowerCase()
    .replace(/_/g, "-")
    .split(/[-.]/)[0];
  return LANGUAGES.includes(primary) ? primary : SOURCE;
}

/** The first browser language kuulas ships, else English. */
export function detectLanguage(nav = globalThis.navigator ?? {}) {
  const wanted = nav.languages?.length ? nav.languages : [nav.language];
  for (const tag of wanted) {
    const primary = String(tag ?? "")
      .toLowerCase()
      .split("-")[0];
    if (LANGUAGES.includes(primary)) return primary;
  }
  return SOURCE;
}

export function getLanguage() {
  return current;
}

/** Test and start-up hook: use these catalogs instead of asking the server. */
export function setCatalogs(byLanguage) {
  for (const lang of Object.keys(catalogs)) delete catalogs[lang];
  Object.assign(catalogs, byLanguage);
}

/** Replace how a catalog is fetched (default: GET /api/locales/<lang>). */
export function setCatalogLoader(fn) {
  loader = fn;
}

/** The document whose <html lang> follows the language; null for none. */
export function setDocument(document) {
  doc = document;
  if (doc) doc.documentElement.lang = current;
}

function announce() {
  if (doc) doc.documentElement.lang = current;
  events.dispatchEvent(new CustomEvent("languagechange", { detail: { language: current } }));
}

/** Switch at once; the catalog must already be loaded (see setLanguage). */
export function setLanguageNow(lang) {
  const next = normalise(lang);
  if (next === current) return;
  current = next;
  announce();
}

/**
 * Switch the language without a reload: load what is missing, then change and
 * tell listeners. If loading fails nothing changes and the error is thrown, so
 * the caller can say so.
 */
export async function setLanguage(lang) {
  const next = normalise(lang);
  // Both at once: in turn, a Finnish start paid two round trips here (en, then fi).
  await Promise.all([...new Set([SOURCE, next])].map(catalog));
  setLanguageNow(next);
}

// Catalogs on their way, by language: a second asker (the page warms the browser's
// language up while the server's choice is still being read) shares the one request.
const loading = {};

/** The catalog of `lang` (normalised): what is loaded, else one fetch shared by all askers. */
function catalog(lang) {
  if (catalogs[lang]) return Promise.resolve(catalogs[lang]);
  loading[lang] ??= loader(lang)
    .then((found) => {
      catalogs[lang] = found;
      return found;
    })
    .finally(() => {
      delete loading[lang]; // a failure is forgotten, so the next try asks again
    });
  return loading[lang];
}

/** Load a catalog without switching to it (once); a failure is swallowed, the language is absent. */
export async function ensureCatalog(lang) {
  try {
    await catalog(normalise(lang));
  } catch {
    // Search then knows only the names in the current language: not worth an error.
  }
}

/** A plain message of another language, undefined when that catalog or key is missing. */
export function tIn(lang, key) {
  const entry = catalogs[lang]?.[key];
  return typeof entry === "string" ? entry : undefined;
}

/** Choose the start-up language (default: the browser's) and load its catalog. */
export async function initI18n({ language = detectLanguage(), document = null } = {}) {
  if (document) setDocument(document);
  await setLanguage(language);
}

/** fn(language) runs after every change. Returns the function that stops it. */
export function onLanguageChange(fn) {
  const listener = (event) => fn(event.detail.language);
  events.addEventListener("languagechange", listener);
  return () => events.removeEventListener("languagechange", listener);
}

// -- t -----------------------------------------------------------------------

function entryFor(lang, key, count) {
  const entry = catalogs[lang]?.[key];
  if (entry !== null && typeof entry === "object") {
    // Plurals are objects of CLDR categories; "other" is always there.
    const category = new Intl.PluralRules(lang).select(Number(count));
    return entry[category] ?? entry.other;
  }
  return entry;
}

function bare(key, values) {
  const extra = Object.entries(values)
    .map(([name, value]) => `${name}=${value}`)
    .join(", ");
  return extra ? `${key} (${extra})` : key;
}

/** The message for `key` in the current language. Never throws. */
export function t(key, values = {}) {
  let template = entryFor(current, key, values.count);
  if (template === undefined && current !== SOURCE) template = entryFor(SOURCE, key, values.count);
  if (typeof template !== "string") return bare(key, values);
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    Object.hasOwn(values, name) ? String(values[name]) : whole,
  );
}

// -- numbers and times ---------------------------------------------------------

function separator() {
  return new Intl.NumberFormat(current).formatToParts(1.1).find((p) => p.type === "decimal").value;
}

/** A number in the UI language: decimal comma in Finnish. Options: digits. */
export function formatNumber(value, { digits = 0 } = {}) {
  const text = new Intl.NumberFormat(current, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
  // Finnish Intl already writes U+2212; English writes a hyphen. One minus for both.
  return text.replace("-", "−");
}

/** "−2,5 dB" (fi) or "−2.5 dB" (en): one decimal, a real minus sign. */
export function formatDb(value) {
  return t("format.db", { value: formatNumber(value, { digits: 1 }) });
}

// Seconds as h:mm:ss with `digits` decimals. Rounded as whole units first, so
// 59.9996 s is "1:00.000" and never "0:59.1000".
function clock(seconds, digits) {
  const unit = 10 ** digits;
  const negative = seconds < 0;
  const total = Math.round(Math.abs(seconds) * unit);
  const whole = Math.floor(total / unit);
  const fraction = String(total % unit).padStart(digits, "0");
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = String(whole % 60).padStart(2, "0");
  const head = h > 0 ? `${h}:${String(m).padStart(2, "0")}` : String(m);
  const tail = digits > 0 ? `${separator()}${fraction}` : "";
  return `${negative ? "−" : ""}${head}:${s}${tail}`;
}

/** A clock with `digits` decimals (0 for whole seconds); ruler labels use it. */
export function formatClock(seconds, digits = 0) {
  return clock(seconds, digits);
}

/** A position: "12:34,567", "1:02:03,500" (fi); the point is a dot in English. */
export function formatTimecode(seconds) {
  return clock(seconds, 3);
}

/** A length: "2:05,5", one decimal. */
export function formatDuration(seconds) {
  return clock(seconds, 1);
}

/**
 * A moment in Helsinki time with the zone named: "19.45 (Helsinki)" (fi),
 * "7:45 pm Helsinki" (en). Takes a Date or anything Date accepts; stored times
 * are UTC and are converted here, at the edge.
 */
export function formatAbsoluteTime(moment) {
  const date = moment instanceof Date ? moment : new Date(moment);
  let time;
  if (current === "en") {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: ZONE,
      hour: "numeric",
      minute: "2-digit",
      hourCycle: "h12",
    }).formatToParts(date);
    const part = (type) => parts.find((p) => p.type === type).value;
    time = `${part("hour")}:${part("minute")} ${part("dayPeriod").toLowerCase()}`;
  } else {
    time = new Intl.DateTimeFormat(current === "fi" ? "fi-FI" : current, {
      timeZone: ZONE,
      hour: "numeric",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(date);
  }
  return t("format.time", { time, zone: t("format.zone") });
}

// -- key names -----------------------------------------------------------------

/** "mac" or "other", from the browser's own report. */
export function detectPlatform(nav = globalThis.navigator ?? {}) {
  const platform = nav.userAgentData?.platform ?? nav.platform ?? "";
  return /mac/i.test(platform) ? "mac" : "other";
}

const MAC_MODIFIERS = { Mod: "⌘", Ctrl: "⌃", Alt: "⌥", Shift: "⇧" };
// Apple's order: control, option, shift, command.
// The Mac names these keys by their glyphs, as its own menus do: Backspace is its Delete key.
const MAC_KEYS = { Backspace: "⌫", Delete: "⌦", Enter: "↩", Tab: "⇥", Escape: "⎋" };
const MAC_ORDER = ["Ctrl", "Alt", "Shift", "Mod"];
const NAMED = {
  Space: "key.space",
  Enter: "key.enter",
  Escape: "key.escape",
  Backspace: "key.backspace",
  Delete: "key.delete",
  Tab: "key.tab",
  Shift: "key.shift",
  Ctrl: "key.ctrl",
  Mod: "key.ctrl",
  Alt: "key.alt",
};
const ARROWS = {
  ArrowLeft: "←",
  ArrowRight: "→",
  ArrowUp: "↑",
  ArrowDown: "↓",
  Comma: ",", // Mod+Comma is matched by position (keys.js), shown as the comma it is
};

/** One key's label: "⌘" on a Mac for Mod, "Ctrl" elsewhere, "Välilyönti" for Space in fi. */
export function keyName(key, platform = detectPlatform()) {
  if (platform === "mac" && key in MAC_MODIFIERS) return MAC_MODIFIERS[key];
  if (platform === "mac" && key in MAC_KEYS) return MAC_KEYS[key];
  if (key in ARROWS) return ARROWS[key];
  if (key in NAMED) return t(NAMED[key]);
  return key.length === 1 ? key.toUpperCase() : key;
}

/** "Mod+Shift+Z" -> "⇧⌘Z" on a Mac, "Ctrl+Shift+Z" elsewhere (names per language). */
export function formatShortcut(shortcut, platform = detectPlatform()) {
  const keys = shortcut.split("+");
  if (platform !== "mac") return keys.map((k) => keyName(k, platform)).join("+");
  const modifiers = MAC_ORDER.filter((m) => keys.includes(m));
  const rest = keys.filter((k) => !MAC_ORDER.includes(k));
  return [...modifiers, ...rest].map((k) => keyName(k, platform)).join("");
}
