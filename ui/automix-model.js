// Mix with the automixer (WP68): pure parts of the dialog and its notice. The dialog itself
// is automix-dialog.js; the job runs on the server (src/kuulas/automix.py).

/** Writing the stems is this much of the bar (STEMS_SHARE in automix.py); then it is indeterminate. */
export const STEMS_SHARE = 0.4;
export const LUFS_RANGE = [-40, 0];
/** Loudness presets: the key labels a button, the value goes in the field. */
export const LUFS_PRESETS = Object.freeze([
  { lufs: "-16", key: "ui.automix.preset_podcast" },
  { lufs: "-14", key: "ui.automix.preset_louder" },
  { lufs: "-23", key: "ui.automix.preset_broadcast" },
]);
export const DEFAULT_AUTOMIX = Object.freeze({
  targetLufs: LUFS_PRESETS[0].lufs,
  adBreak: "",
  adSpot: "",
  adDuration: "",
});

const number = (text) => {
  const trimmed = String(text ?? "")
    .trim()
    .replace(",", ".");
  return trimmed === "" ? null : Number(trimmed);
};

/**
 * "1200", "20:00", "1:02:03" or "0:07.5" -> seconds; null when it is not a time.
 * Minutes and seconds after the first part must be below 60.
 */
export function parseTimestamp(text) {
  const parts = String(text ?? "")
    .trim()
    .replace(",", ".")
    .split(":");
  if (parts.length > 3 || parts.some((part) => !/^\d+(\.\d+)?$/.test(part))) return null;
  const numbers = parts.map(Number);
  if (numbers.slice(1).some((n) => n >= 60)) return null;
  return numbers.reduce((total, n) => total * 60 + n, 0);
}

/** Seconds as m:ss or h:mm:ss (a fraction is kept: 0:07.5). */
export function formatTimestamp(seconds) {
  const whole = Math.floor(seconds);
  const fraction = seconds - whole;
  const pad = (n) => String(n).padStart(2, "0");
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const tail = fraction > 0 ? String(Math.round(fraction * 100) / 100).slice(1) : "";
  const rest = pad(whole % 60) + tail;
  return h > 0 ? `${h}:${pad(m)}:${rest}` : `${m}:${rest}`;
}

/**
 * The whole form checked at once (for inline messages): { ok, errors: { field: messageKey },
 * body }. The ad fields only count while the ad break box is on; the length is optional.
 */
export function validateAutomix(form) {
  const errors = {};
  const body = {};
  const lufs = number(form.targetLufs);
  if (lufs === null || !Number.isFinite(lufs) || lufs < LUFS_RANGE[0] || lufs > LUFS_RANGE[1]) {
    errors.targetLufs = "ui.automix.bad_target_lufs";
  } else {
    body.target_lufs = lufs;
  }
  if (form.adBreak) {
    const spot = parseTimestamp(form.adSpot);
    if (spot === null) errors.adSpot = "ui.automix.bad_ad_spot";
    else body.ad_spot = spot;
    const duration = number(form.adDuration);
    if (duration !== null) {
      if (!Number.isFinite(duration) || duration <= 0) {
        errors.adDuration = "ui.automix.bad_ad_duration";
      } else {
        body.ad_duration = duration;
      }
    }
  }
  return { ok: Object.keys(errors).length === 0, errors, body };
}

/**
 * The request body for POST /api/automix from the form's texts, or { ok: false, field, key }
 * naming the first field to mark and the message key.
 */
export function automixRequest(form) {
  const { ok, errors, body } = validateAutomix(form);
  if (ok) return { ok, body };
  const [field] = Object.keys(errors);
  return { ok: false, field, key: errors[field] };
}

/** A remembered form (any older shape, or null) as a full form. */
export function migrateForm(stored) {
  const form = { ...DEFAULT_AUTOMIX };
  const old = stored && typeof stored === "object" ? stored : {};
  for (const key of Object.keys(form)) if (typeof old[key] === "string") form[key] = old[key];
  if (typeof old.adBreak !== "string" && form.adSpot.trim() !== "") form.adBreak = "1";
  return form;
}

/** The settings body (PUT /api/settings/automixer) from the Advanced and Output fields. */
export function advancedBody(fields) {
  const words = parseWords(fields.command);
  return {
    command: words.length > 0 ? words : undefined,
    cwd: fields.cwd.trim() || undefined,
    temp_dir: fields.tempDir.trim() || undefined,
    output_dir: fields.outputDir.trim() || undefined,
    extra_args: parseWords(fields.extra),
  };
}

/** The name the mix gets (automix.py: "<project> automixer YYYY-MM-DD HH-MM-SS.wav", local
 * time; "<project> - <edit>" when the edit is not the main one). */
export function fileNamePreview(title, when = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  const day = `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`;
  const time = `${pad(when.getHours())}-${pad(when.getMinutes())}-${pad(when.getSeconds())}`;
  return `${title} automixer ${day} ${time}.wav`;
}

/** "uv run "my tool" --x" -> ["uv", "run", "my tool", "--x"]; quotes keep a word together. */
export function parseWords(text) {
  const words = [];
  for (const match of String(text ?? "").matchAll(/"([^"]*)"|(\S+)/g)) {
    words.push(match[1] ?? match[2]);
  }
  return words;
}

/** The inverse of parseWords: words with a space are quoted. */
export const formatWords = (words) =>
  (words ?? []).map((word) => (/\s/.test(word) ? `"${word}"` : word)).join(" ");

/**
 * What the notice says about an automix job (as /api/jobs lists it):
 * { kind, text, sticky, cancel, reveal }. While the tool runs there is no number, only its
 * last line (job.message).
 */
export function automixNotice(job, t) {
  if (job.state === "completed") {
    return {
      kind: "ok",
      text: t("ui.automix.done", { path: job.result?.path ?? "" }),
      sticky: true,
      cancel: false,
      reveal: true,
    };
  }
  if (job.state === "failed") {
    return { kind: "error", text: job.error?.text ?? "", sticky: false, cancel: false };
  }
  if (job.state === "cancelled") {
    return { kind: "ok", text: t("ui.automix.cancelled"), sticky: false, cancel: false };
  }
  const progress = job.progress ?? 0;
  let text;
  if (job.indeterminate) {
    // The tool has not printed a PROGRESS line yet: only its last line.
    text = job.message
      ? t("ui.automix.running_line", { line: job.message })
      : t("ui.automix.running");
  } else if (progress <= STEMS_SHARE) {
    const percent = Math.round(Math.min(1, progress / STEMS_SHARE) * 100);
    text = t("ui.automix.preparing", { percent });
  } else {
    text = t("ui.automix.running_percent", {
      percent: Math.round(progress * 100),
      line: job.message ?? "",
    });
  }
  return { kind: "ok", text, sticky: true, cancel: true, reveal: false };
}
