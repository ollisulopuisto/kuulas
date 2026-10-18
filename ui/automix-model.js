// Mix with the automixer (WP68): pure parts of the dialog and its notice. The dialog itself
// is automix-dialog.js; the job runs on the server (src/kuulas/automix.py).

/** Writing the stems is this much of the bar (STEMS_SHARE in automix.py); then it is indeterminate. */
export const STEMS_SHARE = 0.4;
export const LUFS_RANGE = [-40, 0];
export const DEFAULT_AUTOMIX = Object.freeze({ targetLufs: "-16", adSpot: "", adDuration: "" });

const number = (text) => {
  const trimmed = String(text ?? "").trim();
  return trimmed === "" ? null : Number(trimmed);
};

/**
 * The request body for POST /api/automix from the form's texts, or { ok: false, field, key }
 * naming the field to mark and the message key. The duration only counts with a spot.
 */
export function automixRequest(form) {
  const lufs = number(form.targetLufs);
  if (lufs === null || !Number.isFinite(lufs) || lufs < LUFS_RANGE[0] || lufs > LUFS_RANGE[1]) {
    return { ok: false, field: "targetLufs", key: "ui.automix.bad_target_lufs" };
  }
  const body = { target_lufs: lufs };
  const spot = number(form.adSpot);
  if (spot !== null) {
    if (!Number.isFinite(spot) || spot < 0) {
      return { ok: false, field: "adSpot", key: "ui.automix.bad_ad_spot" };
    }
    body.ad_spot = spot;
    const duration = number(form.adDuration);
    if (duration !== null) {
      if (!Number.isFinite(duration) || duration <= 0) {
        return { ok: false, field: "adDuration", key: "ui.automix.bad_ad_duration" };
      }
      body.ad_duration = duration;
    }
  }
  return { ok: true, body };
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
  let text;
  if (job.indeterminate || (job.progress ?? 0) >= STEMS_SHARE) {
    text = job.message
      ? t("ui.automix.running_line", { line: job.message })
      : t("ui.automix.running");
  } else {
    const percent = Math.round(Math.min(1, (job.progress ?? 0) / STEMS_SHARE) * 100);
    text = t("ui.automix.preparing", { percent });
  }
  return { kind: "ok", text, sticky: true, cancel: true, reveal: false };
}
