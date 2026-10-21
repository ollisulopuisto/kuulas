import { etaLabel, etaVisible } from "./eta-label.js";

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
  // "1": mix only the In/Out range (a quick preview), while the marks allow it.
  onlyRange: "",
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
    ...(fields.remote ? { remote: remoteBody(fields.remote) } : {}),
  };
}

/** The "Run on another Mac" settings (`remote` in PUT /api/settings/automixer): empty fields
 * are left out so the server's defaults apply. */
export function remoteBody(fields) {
  const body = { enabled: fields.enabled === true };
  for (const [key, value] of [
    ["host", fields.host],
    ["cwd", fields.cwd],
    ["work_dir", fields.workDir],
  ]) {
    const text = String(value ?? "").trim();
    if (text) body[key] = text;
  }
  return body;
}

/** The one line the Mix dialog shows when the render runs elsewhere; empty when it does not. */
export function remoteNote(remote, t) {
  return remote?.enabled && remote.host
    ? t("ui.automix.remote_runs_on", { host: remote.host })
    : "";
}

/**
 * The rows of a connection test (POST /api/settings/automixer/remote-test): one per check,
 * `{ id, label, status: "ok" | "warn" | "failed", statusText, detail }`.
 */
export function remoteRows(result, t) {
  if (!Array.isArray(result?.checks)) return [];
  return result.checks.map((check) => {
    const status = !check.ok ? "failed" : check.warn ? "warn" : "ok";
    let detail = check.detail ?? "";
    if (check.id === "disk" && status === "warn") {
      detail = t("ui.automix.remote_low_disk", { free: detail });
    }
    if (check.id === "flags" && Array.isArray(check.missing) && check.missing.length > 0) {
      detail = t("ui.automix.remote_missing", { flags: check.missing.join(", ") });
    }
    return {
      id: check.id,
      label: t(`ui.automix.remote_check.${check.id}`),
      status,
      statusText: t(`ui.automix.remote_${status}`),
      detail,
    };
  });
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
 * { kind, text, sticky, cancel, reveal, log }. `log`: the log file is there to show (the
 * job kept one, also when it failed). While the tool runs there is no number, only its
 * last line (job.message).
 */
export function automixNotice(job, t) {
  if (job.state === "completed") {
    const summary = (job.result?.summary ?? []).join(" \u00b7 ");
    const done = t("ui.automix.done", { path: job.result?.path ?? "" });
    return {
      kind: "ok",
      text: summary ? `${done} \u2014 ${summary}` : done,
      sticky: true,
      cancel: false,
      reveal: true,
      log: Boolean(job.result?.log_file),
    };
  }
  if (job.state === "failed") {
    return {
      kind: "error",
      text: job.error?.text ?? "",
      sticky: Boolean(job.error?.params?.log_file),
      cancel: false,
      log: Boolean(job.error?.params?.log_file),
    };
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
  if (!job.indeterminate) {
    const percent = Math.round(progress * 100);
    const label = etaVisible(percent) ? etaLabel(job.eta) : null;
    if (label) text += ` \u00b7 ${t(label.key, label.params)}`;
  }
  return { kind: "ok", text, sticky: true, cancel: true, reveal: false };
}
