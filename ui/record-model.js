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

/**
 * What a take replaced on the tracks it went on ("Olli 12.0 s"), or null when nothing: the
 * stop notice says it, so a punch-in is never a surprise. Slivers under 0.1 s are left out.
 */
export function replacedMessage(result, rate, t) {
  const parts = (result?.replaced ?? [])
    .filter((entry) => rate > 0 && entry.frames / rate >= 0.1)
    .map((entry) => `${entry.track} ${(entry.frames / rate).toFixed(1)} s`);
  return parts.length === 0 ? null : t("ui.record.replaced", { what: parts.join(", ") });
}

/**
 * The tracks clips played from the cart may go on: none, a new track, and every track that no
 * switched-on channel records onto (a track the take records onto cannot be it).
 */
export function cartTrackChoices(project, rows) {
  const recorded = new Set(rows.filter((r) => r.on && r.target !== "new").map((r) => r.target));
  return [
    { value: "", name: null },
    { value: "new", name: null },
    ...(project?.tracks ?? [])
      .filter((track) => !recorded.has(track.id))
      .map((track) => ({ value: track.id, name: track.name })),
  ];
}

/** Does the chosen cart track already hold audio from `at` on (the clips played would overwrite it)? */
export function cartTrackWarning(project, trackId, at) {
  if (!trackId || trackId === "new") return false;
  const track = project?.tracks?.find((item) => item.id === trackId);
  return (track?.clips ?? []).some((clip) => clip.start + clip.length > at);
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

/**
 * The body of POST /api/record/start. Several channels (WP12b): `lanes`, from selectedLanes;
 * the one-channel form (`channel`, `target` a track id or "new", `name`) still works.
 */
export function startRequest({
  device,
  lanes,
  channel,
  target,
  name,
  at,
  cartTrack,
  playOthers = false,
  latencyMs = 0,
}) {
  const body = {
    device: device ? { index: device.index, name: device.name } : null,
    at: Math.max(0, Math.round(Number(at) || 0)),
    // Where clips played from the cart go while the take records: a track, "new", or none.
    cart_track: cartTrack || null,
    // Play the tracks the take does not record onto, from its start (headphones), and the
    // delay between what is heard and what is captured, cut from the take's head (ms).
    play_others: Boolean(playOthers),
    latency_ms: Math.min(2000, Math.max(0, Number(latencyMs) || 0)),
  };
  if (lanes) return { ...body, channels: lanes };
  return {
    ...body,
    channel: Number(channel) || 1,
    track_id: target === "new" ? null : target,
    name: (name ?? "").trim(),
  };
}

// -- several channels of one device (WP12b) -------------------------------------------------
// A row is one device channel: whether to record it and onto which track ("new" or a track id,
// with the name a new track gets). The rows that are on are the take's lanes, in channel order:
// the order the recorder lists them, meters them and compares them to an armed listener.

/** The channels of `device` as rows; `remembered` (channel numbers) are on, else channel 1. */
export function initialRows(device, remembered) {
  const channels = channelChoices(device);
  const wanted = (remembered ?? []).filter((n) => channels.includes(n));
  const on = wanted.length > 0 ? wanted : [1];
  return channels.map((channel) => ({
    channel,
    on: on.includes(channel),
    target: "new",
    name: "",
  }));
}

/** The rows that are on as the request's lanes, in channel order. */
export function selectedLanes(rows) {
  return rows
    .filter((r) => r.on)
    .sort((a, b) => a.channel - b.channel)
    .map((r) => ({
      channel: r.channel,
      track_id: r.target === "new" ? null : r.target,
      name: (r.name ?? "").trim(),
    }));
}

/** What stops Record before it is asked of the server: a catalog key, or null. */
export function startProblem(rows) {
  const lanes = selectedLanes(rows);
  if (lanes.length === 0) return "ui.record.no_channel";
  const tracks = lanes.map((l) => l.track_id).filter((id) => id !== null);
  if (new Set(tracks).size !== tracks.length) return "error.record.same_track";
  return null;
}

/** One level meter's label per lane (`plan.lanes` of the server's status). */
export function meterLabels(lanes, t) {
  return (lanes ?? []).map((lane) => ({
    channel: lane.channel,
    text: t("ui.record.level_of", { name: lane.track_name }),
  }));
}

/** A level frame as `count` readings; a channel the frame lacks reads as silence. */
export function channelPeaks(frame, count) {
  return Array.from({ length: count }, (_, i) => ({
    db: frame?.peak_dbfs?.[i] ?? -120,
    clipped: Boolean(frame?.clipped?.[i]),
  }));
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
export function importedMessage(result, t, formatNumber = (value) => String(value)) {
  let message;
  if (result.failed_channels?.length > 0)
    message = t("ui.record.imported_failed", {
      take: result.take,
      names: result.failed_channels.join(", "),
    });
  else if (result.interrupted) message = t("ui.record.imported_interrupted", { take: result.take });
  else if (result.gaps > 0)
    message = t("ui.record.imported_gaps", {
      take: result.take,
      count: result.gaps,
    });
  else
    message = t("ui.record.imported", {
      take: result.take,
      count: result.clips,
    });

  const health = [];
  const overflows = Math.max(0, Number(result.overflows) || 0);
  const dropouts = Math.max(0, Number(result.dropouts) || 0);
  if (overflows > 0) health.push(t("ui.record.health_overflows", { count: overflows }));
  if (dropouts > 0)
    health.push(
      t("ui.record.health_dropouts", {
        count: dropouts,
        seconds: formatNumber(Math.max(0, Number(result.dropout_seconds) || 0), { digits: 1 }),
      }),
    );
  return health.length > 0
    ? t("ui.record.imported_health", { message, details: health.join(" ") })
    : message;
}

/** Imported notices with capture problems stay visible until the user dismisses them. */
export function importedNoticeOptions(result) {
  return {
    undo: true,
    sticky: Number(result?.overflows) > 0 || Number(result?.dropouts) > 0,
  };
}

// -- the take's live transcript (owner, 2026-11-01) ----------------------------------------
// While a take records, its newest seconds are transcribed on the server and the words are
// searchable here during the take; the last words land briefly after the stop ("flushing").

/** The take-so-far as one flowing line: the newest `maxWords` words joined, "" when none. */
export function liveTail(words, maxWords = 30) {
  const list = (words ?? []).map((w) => String(w.w ?? "").trim()).filter(Boolean);
  return list.slice(-Math.max(1, maxWords)).join(" ");
}

/** One search hit for the list: the word, its track's name, its time in seconds (flicks in). */
export function liveHits(words, trackNames, flicksPerSecond) {
  const names = trackNames ?? {};
  const fps = flicksPerSecond > 0 ? flicksPerSecond : 1;
  return (words ?? []).map((w) => ({
    word: String(w.w ?? ""),
    track: names[w.track] ?? "",
    seconds: Math.max(0, Number(w.s) || 0) / fps,
  }));
}

/** The panel shows while a take records or while its last words still land after the stop. */
export function liveTranscriptVisible(phase, flushing) {
  return phase === "recording" || Boolean(flushing);
}
