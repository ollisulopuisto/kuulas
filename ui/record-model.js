// The record view's decisions (WP12a part B), pure: record-view.js draws and wires them.
// The server owns the recording (src/kuulas/record_session.py); the page only shows it and
// sends start and stop, so everything here is a function of what the server said.

/** "loading" (nothing heard yet), "setup", "recording" (ours) or "elsewhere" (another project). */
export function recordPhase(status) {
  if (!status) return "loading";
  if (status.recording && status.ours) return "recording";
  if (status.recording) return "elsewhere";
  return "setup";
}

/** Recorded time: "M:SS" under an hour, "H:MM:SS" above. */
export function formatElapsed(frames, rate) {
  const seconds = rate > 0 && Number.isFinite(frames) && frames > 0 ? Math.floor(frames / rate) : 0;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** The device to offer first: the remembered one by name (indexes change after a replug), else
 * the system default, else the first; null when there is none. */
export function pickDevice(devices, remembered) {
  if (!devices?.length) return null;
  const byName = remembered?.name && devices.find((d) => d.name === remembered.name);
  return byName || devices.find((d) => d.default) || devices[0];
}

/** The device's channels, 1-based. */
export function channelChoices(device) {
  const n = Math.max(1, Number(device?.channels) || 1);
  return Array.from({ length: n }, (_, i) => i + 1);
}

/** The body of POST /api/record/start. `target` is a track id or "new". */
export function startRequest({ device, channel, target, name, at }) {
  return {
    device: device ? { index: device.index, name: device.name } : null,
    channel: Number(channel) || 1,
    track_id: target === "new" ? null : target,
    name: (name ?? "").trim(),
    at: Math.max(0, Math.round(Number(at) || 0)),
  };
}

/** What the stop button says for the gesture's state (stop-mode.js). */
export function stopLabel(view, mode, t) {
  if (view.state === "stopped") return t("ui.record.stopping");
  if (view.state === "confirming")
    return t("ui.record.stop_confirm", { seconds: view.secondsLeft });
  if (mode === "hold") return t("ui.record.stop_hold");
  return t("ui.record.stop");
}

/**
 * What a keydown does while a take records (owner: nothing stops a take by accident).
 * -> "press" (the stop control), "show" (bring the view back), "hide", "pass" (let the editor or
 *    the browser have it) or "swallow" (nothing at all).
 * In the view: Space presses the stop control (an auto-repeat is not a second press), Esc only
 * hides the view, Tab moves focus, everything else is swallowed. With the view hidden the editor
 * works as usual, except Space: no playback while recording, so it shows the view instead.
 */
export function recordKeyAction(event, { visible }) {
  const space = event.key === " " || event.key === "Spacebar";
  if (!visible) return space && !event.inField ? "show" : "pass";
  if (event.inField) return event.key === "Escape" ? "hide" : "pass";
  if (space) return event.repeat ? "swallow" : "press";
  if (event.key === "Escape") return "hide";
  if (event.key === "Tab") return "pass";
  return "swallow";
}

/** The notice after a take is on the timeline. */
export function importedMessage(result, t) {
  if (result.interrupted) return t("ui.record.imported_interrupted", { take: result.take });
  if (result.gaps > 0)
    return t("ui.record.imported_gaps", { take: result.take, count: result.gaps });
  return t("ui.record.imported", { take: result.take, count: result.clips });
}
