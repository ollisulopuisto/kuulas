// Transcribe on Colab (WP78): the pure parts. The dialogs are colab-dialog.js; the job runs on
// the server (src/kuulas/colab_transcribe.py).

import { formatWords, parseWords } from "./automix-model.js";

/** The user preference (prefs.js, "kuulas.colab.consent") that skips the upload question. */
export const CONSENT_KEY = "colab.consent";

/**
 * Must the user be asked before audio is uploaded? Once per session, unless they chose
 * "Do not ask again" (a stored preference). kuulas never uploads on its own: the question
 * only exists because the user started a Colab transcription.
 */
export const consentNeeded = ({ remembered, session }) => !(remembered || session);

export const rememberedConsent = (prefs) => prefs.get(CONSENT_KEY) === "always";

/** -> whether it was stored (false when storage is blocked: then it is asked each session). */
export const rememberConsent = (prefs) => prefs.set(CONSENT_KEY, "always");

/** The form's texts for the resolved settings GET /api/settings/colab answers. */
export function colabForm(resolved) {
  return {
    command: formatWords(resolved.command),
    cwd: resolved.cwd ?? "",
    extra: formatWords(resolved.extra_args),
    model: resolved.model ?? "",
    language: resolved.language ?? "",
    noDrive: resolved.no_drive === true,
    align: resolved.align !== false,
  };
}

/** The body for PUT /api/settings/colab: empty fields are left out so the defaults apply. */
export function colabSettingsBody(form) {
  const body = {};
  const command = parseWords(form.command);
  if (command.length > 0) body.command = command;
  if (form.cwd.trim()) body.cwd = form.cwd.trim();
  body.extra_args = parseWords(form.extra);
  body.no_drive = Boolean(form.noDrive);
  body.align = form.align !== false;
  if (form.model.trim()) body.model = form.model.trim();
  if (form.language.trim()) body.language = form.language.trim();
  return body;
}

/**
 * What the notice says about a Colab transcription job (as /api/jobs lists it):
 * { kind, text, sticky, cancel }. `names` are the recordings, for the done message. While the
 * tool has printed no PROGRESS line there is no number, only its last line.
 */
export function colabNotice(job, t, names = "") {
  // WP79: every transcription is a background job; a local one has its own words.
  const p = job.backend === "local" ? "ui.transcribe" : "ui.colab";
  if (job.state === "completed") {
    return { kind: "ok", text: t(`${p}.done`, { names }), sticky: false, cancel: false };
  }
  if (job.state === "failed") {
    return { kind: "error", text: job.error?.text ?? "", sticky: false, cancel: false };
  }
  if (job.state === "interrupted") {
    return { kind: "error", text: t("ui.colab.interrupted"), sticky: false, cancel: false };
  }
  if (job.state === "cancelled") {
    return { kind: "ok", text: t(`${p}.cancelled`), sticky: false, cancel: false };
  }
  let text;
  if (job.indeterminate) {
    text = job.message ? t(`${p}.running_line`, { line: job.message }) : t(`${p}.running`);
  } else {
    text = t(`${p}.running_percent`, {
      percent: Math.round((job.progress ?? 0) * 100),
      line: job.message ?? "",
    });
  }
  return { kind: "ok", text, sticky: true, cancel: true };
}

/**
 * The background transcription job (WP79) a reopened window should follow again: the first
 * transcription job that is still waiting or running, or undefined.
 */
export const resumableJob = (jobs) =>
  jobs.find(
    (job) =>
      job.background === true &&
      job.kind === "transcribe" &&
      (job.state === "queued" || job.state === "running"),
  );
