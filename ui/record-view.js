// Transport > Record… (WP12a part B): the big modal record view, and the "Recording" chip in
// the toolbar while a take runs. The recorder is its own program and the server owns the take
// (src/kuulas/record_session.py), so this page is only a viewer and a remote: closing it, Esc,
// a reload or a crash never stops a take. Reopening the page shows the running take again.
//
// Stopping (owner, 2026-10-19) is a user preference (stop-mode.js): two steps by default ("Stop
// recording? Press again"), one click, or a 2 s hold. The server refuses a stop without the
// gesture. No listening while recording: the view says monitoring is the interface's job.
//
// Decisions live in record-model.js and stop-mode.js (pure, tested); this file draws and wires.
import { createPeakHold } from "./peak-hold.js";
import {
  channelChoices,
  formatElapsed,
  importedMessage,
  pickDevice,
  recordKeyAction,
  recordPhase,
  startRequest,
  stopLabel,
} from "./record-model.js";
import { CONFIRM_MS, createStopGesture, STOP_MODES, stopModeChoice } from "./stop-mode.js";

const STOP_MODE_KEY = "recordStopMode";
const DEVICE_KEY = "recordDevice";
const CHANNEL_KEY = "recordChannel";
const FLOOR_DB = -60;
const RING = 2 * Math.PI * 52; // the stop ring's circumference (r = 52 in its 120 box)

const el = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
};

const SVG = "http://www.w3.org/2000/svg";
function svgNode(tag, attributes) {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  return node;
}

/** The stop button's face: a square inside a ring that fills (hold) or runs out (confirm). */
function stopIcon() {
  const svg = svgNode("svg", { viewBox: "0 0 120 120", "aria-hidden": "true" });
  svg.append(
    svgNode("circle", { class: "record-ring-track", cx: 60, cy: 60, r: 52 }),
    svgNode("circle", { class: "record-ring", cx: 60, cy: 60, r: 52 }),
    svgNode("rect", { class: "record-stop-square", x: 44, y: 44, width: 32, height: 32, rx: 4 }),
  );
  return svg;
}

/**
 * `api`: getRecordStatus, getRecordDevices, startRecording, stopRecording, importTakes.
 * `getState()` -> the app state (project, playhead); `apply(response)` takes a server state
 * answer; `notify(text, kind, options)` is the app's notice; `chip` the toolbar's indicator.
 */
export function createRecordView({ api, t, prefs, getState, apply, notify, chip }) {
  let status = null;
  let devices = null;
  let deviceError = "";
  let stopMode = stopModeChoice(prefs.get(STOP_MODE_KEY));
  let gesture = createStopGesture({ mode: stopMode });
  let gestureView = gesture.tick(0);
  let stopping = false;
  let frame = null;
  let position = 0;
  const notices = [];
  const meter = createPeakHold({ floorDb: FLOOR_DB });
  let meterView = { bar: FLOOR_DB, peak: FLOOR_DB, clipped: false };

  // -- the frame -----------------------------------------------------------------------
  const dialog = el("dialog", "cheatsheet record-view");
  dialog.setAttribute("aria-labelledby", "record-title");
  const heading = el("h2", "record-title");
  heading.id = "record-title";
  const body = el("div", "record-body");
  const monitoring = el("p", "record-monitoring");
  const footer = el("div", "cheatsheet-footer record-footer");
  const modeLabel = el("label", "record-mode");
  const modeText = el("span");
  const modeSelect = el("select");
  modeLabel.append(modeText, modeSelect);
  const hideButton = el("button", "button");
  hideButton.type = "button";
  footer.append(modeLabel, hideButton);
  dialog.append(heading, body, monitoring, footer);
  document.body.append(dialog);

  const phase = () => (stopping ? "recording" : recordPhase(status));
  const recording = () => phase() === "recording";
  const rate = () => status?.rate ?? getState().project?.rate ?? 48000;

  // Esc (the dialog's cancel) and Hide only hide the view: the take goes on, the chip shows it.
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    hide();
  });
  hideButton.addEventListener("click", () => hide());
  modeSelect.addEventListener("change", () => setStopMode(modeSelect.value));

  // -- setup: device, channel, track --------------------------------------------------
  const setup = {};
  function buildSetup() {
    const box = el("div", "record-setup");
    const row = (labelText, control) => {
      const label = el("label", "record-field");
      label.append(el("span", "record-label", labelText), control);
      box.append(label);
      return control;
    };
    setup.device = row(t("ui.record.device"), el("select"));
    setup.channel = row(t("ui.record.channel"), el("select"));
    setup.track = row(t("ui.record.track"), el("select"));
    setup.name = row(t("ui.record.name"), el("input"));
    setup.name.type = "text";
    setup.name.autocomplete = "off";
    setup.at = el("p", "record-at");
    setup.disk = el("p", "record-disk");
    setup.message = el("p", "record-message");
    setup.message.setAttribute("role", "status");
    setup.record = el("button", "button record-button", t("ui.record.record"));
    setup.record.type = "button";
    box.append(setup.at, setup.disk, setup.message, setup.record);
    setup.device.addEventListener("change", () => {
      const device = devices?.[Number(setup.device.value)];
      if (device) prefs.setJson(DEVICE_KEY, { index: device.index, name: device.name });
      fillChannels();
    });
    setup.channel.addEventListener("change", () => prefs.set(CHANNEL_KEY, setup.channel.value));
    setup.track.addEventListener("change", () => {
      setup.name.disabled = setup.track.value !== "new";
    });
    setup.record.addEventListener("click", () => void start());
    return box;
  }

  function fillChannels() {
    const device = devices?.[Number(setup.device.value)];
    const remembered = Number(prefs.get(CHANNEL_KEY)) || 1;
    setup.channel.replaceChildren(
      ...channelChoices(device).map((n) => new Option(t("ui.record.channel_n", { n }), String(n))),
    );
    if (channelChoices(device).includes(remembered)) setup.channel.value = String(remembered);
  }

  function fillSetup() {
    const state = getState();
    const list = devices ?? [];
    const chosen = pickDevice(list, prefs.getJson(DEVICE_KEY, null));
    setup.device.replaceChildren(
      ...list.map(
        (d, i) =>
          new Option(
            d.default ? t("ui.record.default_device", { name: d.name }) : d.name,
            String(i),
          ),
      ),
    );
    if (chosen) setup.device.value = String(list.indexOf(chosen));
    fillChannels();
    const tracks = state.project?.tracks ?? [];
    const before = setup.track.value;
    setup.track.replaceChildren(
      new Option(t("ui.record.new_track"), "new"),
      ...tracks.map((track) => new Option(track.name, track.id)),
    );
    setup.track.value = tracks.some((track) => track.id === before) ? before : "new";
    setup.name.disabled = setup.track.value !== "new";
    setup.at.textContent = t("ui.record.at", {
      time: formatElapsed(state.playhead ?? 0, rate()),
    });
    renderDisk(setup.disk);
    let message = "";
    if (deviceError) message = deviceError;
    else if (devices === null) message = t("ui.record.loading");
    else if (list.length === 0) message = t("ui.record.no_devices");
    setup.message.textContent = message;
    setup.record.disabled = !chosen || stopping;
  }

  function renderDisk(node) {
    const disk = status?.disk;
    node.dataset.state = disk?.state ?? "ok";
    node.textContent =
      disk?.seconds_left == null
        ? t("ui.record.disk_unknown")
        : t("ui.record.disk_left", { time: disk.text });
  }

  async function loadDevices() {
    deviceError = "";
    try {
      devices = (await api.getRecordDevices()).devices;
    } catch (error) {
      devices = [];
      deviceError = error.message;
    }
    if (phase() === "setup") fillSetup();
  }

  async function start() {
    const device = devices?.[Number(setup.device.value)] ?? null;
    setup.record.disabled = true;
    try {
      const answer = await api.startRecording(
        startRequest({
          device,
          channel: setup.channel.value,
          target: setup.track.value,
          name: setup.name.value,
          at: getState().playhead ?? 0,
        }),
      );
      notices.length = 0;
      position = 0;
      meter.reset();
      setStatus(answer);
    } catch (error) {
      setup.message.textContent = error.message;
      setup.record.disabled = false;
    }
  }

  // -- recording: time, meter, warnings, the stop control --------------------------------
  const rec = {};
  function buildRecording() {
    const box = el("div", "record-live");
    rec.take = el("p", "record-take");
    rec.elapsed = el("output", "record-elapsed");
    rec.elapsed.setAttribute("aria-label", t("ui.record.elapsed"));
    const meterBox = el("div", "record-meter");
    meterBox.setAttribute("role", "img");
    meterBox.setAttribute("aria-label", t("ui.record.level"));
    rec.fill = el("i", "record-meter-fill");
    rec.hold = el("i", "record-meter-hold");
    meterBox.append(rec.fill, rec.hold);
    rec.clip = el("button", "record-clip", t("ui.record.clip"));
    rec.clip.type = "button";
    rec.clip.title = t("ui.record.clip_title");
    rec.clip.hidden = true;
    rec.clip.addEventListener("click", () => {
      meter.clearClip();
      meterView = { ...meterView, clipped: false };
      rec.clip.hidden = true;
    });
    const meterRow = el("div", "record-meter-row");
    meterRow.append(meterBox, rec.clip);
    rec.disk = el("p", "record-disk");
    rec.notices = el("ul", "record-notices");
    rec.notices.setAttribute("aria-live", "assertive");
    rec.stop = el("button", "record-stop");
    rec.stop.type = "button";
    rec.stop.append(stopIcon());
    rec.ring = rec.stop.querySelector(".record-ring");
    rec.stopText = el("span", "record-stop-text");
    rec.stop.append(rec.stopText);
    rec.stopHelp = el("p", "record-stop-help", t("ui.record.stop_keys"));
    rec.stop.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      rec.stop.setPointerCapture?.(event.pointerId);
      press();
    });
    for (const type of ["pointerup", "pointercancel"])
      rec.stop.addEventListener(type, () => release());
    rec.stop.addEventListener("lostpointercapture", () => release());
    box.append(rec.take, rec.elapsed, meterRow, rec.disk, rec.notices, rec.stop, rec.stopHelp);
    return box;
  }

  function renderMeter() {
    if (!rec.fill) return;
    const pct = (db) => `${Math.max(0, Math.min(100, ((db - FLOOR_DB) / -FLOOR_DB) * 100))}%`;
    rec.fill.style.width = pct(meterView.bar);
    rec.hold.style.left = pct(meterView.peak);
    rec.fill.dataset.zone = meterView.bar > -6 ? "hot" : meterView.bar > -18 ? "warn" : "ok";
    rec.clip.hidden = !meterView.clipped;
  }

  function renderStop() {
    if (!rec.stop) return;
    const v = gestureView;
    rec.stopText.textContent = stopping ? t("ui.record.stopping") : stopLabel(v, stopMode, t);
    rec.stop.dataset.state = stopping ? "stopped" : v.state;
    rec.stop.setAttribute("aria-label", rec.stopText.textContent);
    let fill = 0;
    if (v.state === "holding") fill = v.progress;
    if (v.state === "confirming") fill = v.remaining ?? 1;
    rec.ring.style.strokeDasharray = `${RING}`;
    rec.ring.style.strokeDashoffset = `${RING * (1 - fill)}`;
    rec.stop.disabled = stopping;
  }

  function renderNotices() {
    if (!rec.notices) return;
    rec.notices.replaceChildren(
      ...notices.slice(-6).map((n) => {
        const item = el("li", `record-notice ${n.level}`, t(n.key, n.params));
        if (n.level === "alarm") item.setAttribute("role", "alert");
        return item;
      }),
    );
  }

  function renderRecording() {
    rec.take.textContent = t("ui.record.recording", { take: status?.take ?? "" });
    rec.elapsed.textContent = formatElapsed(position, rate());
    renderDisk(rec.disk);
    renderMeter();
    renderStop();
    renderNotices();
  }

  // -- the stop gesture ---------------------------------------------------------------
  const now = () => performance.now();
  function step() {
    frame = null;
    gestureView = withRemaining(gesture.tick(now()));
    renderStop();
    if (gestureView.stopped) {
      void stop(gestureView.heldMs);
      return;
    }
    if (gestureView.state === "confirming" || gestureView.state === "holding")
      frame = requestAnimationFrame(step);
  }
  // The confirm ring empties as the window runs out (seconds are whole; the ring is smooth).
  let confirmStart = 0;
  function withRemaining(v) {
    if (v.state !== "confirming") return v;
    return { ...v, remaining: Math.max(0, 1 - (now() - confirmStart) / CONFIRM_MS) };
  }
  function press() {
    if (!recording() || stopping) return;
    const before = gestureView.state;
    gestureView = gesture.press(now());
    if (gestureView.state === "confirming" && before !== "confirming") confirmStart = now();
    gestureView = withRemaining(gestureView);
    renderStop();
    if (gestureView.stopped) void stop(gestureView.heldMs);
    else if (frame === null) frame = requestAnimationFrame(step);
  }
  function release() {
    if (!recording() || stopping) return;
    gestureView = withRemaining(gesture.release(now()));
    renderStop();
  }
  function newGesture() {
    gesture = createStopGesture({ mode: stopMode });
    gestureView = gesture.tick(now());
  }

  async function stop(heldMs) {
    stopping = true;
    renderStop();
    try {
      const response = await api.stopRecording({ mode: stopMode, held_ms: heldMs ?? 0 });
      apply(response);
      stopping = false;
      const imported = response.record?.imported;
      if (imported) notify(importedMessage(imported, t), "ok", { undo: true });
      newGesture();
      setStatus(await api.getRecordStatus());
      if (dialog.open) dialog.close();
    } catch (error) {
      stopping = false;
      newGesture();
      notify(error.message);
      await refreshStatus();
    }
  }

  // Space and Esc while a take runs (record-model.recordKeyAction): captured before the
  // editor's keymap, so no editing key reaches the timeline while the view shows.
  const inField = (target) =>
    target instanceof Element && target.closest("input, select, textarea");
  window.addEventListener(
    "keydown",
    (event) => {
      if (!recording()) return;
      const action = recordKeyAction(
        {
          key: event.key,
          repeat: event.repeat,
          metaKey: event.metaKey,
          inField: Boolean(inField(event.target)),
        },
        { visible: dialog.open },
      );
      if (action === "pass") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (action === "press") press();
      else if (action === "show") show();
      else if (action === "hide") hide();
    },
    true,
  );
  window.addEventListener(
    "keyup",
    (event) => {
      if (recording() && dialog.open && (event.key === " " || event.key === "Spacebar")) {
        event.preventDefault();
        event.stopImmediatePropagation();
        release();
      }
    },
    true,
  );
  window.addEventListener("beforeunload", (event) => {
    if (!recording()) return;
    // The take goes on whatever the user answers; the browser only asks to be sure.
    event.preventDefault();
    event.returnValue = t("ui.record.unload_warning");
  });

  // -- drawing the whole view ----------------------------------------------------------
  // Built on the first render, not at load: the catalogs are not loaded when app.js makes this.
  let setupBox = null;
  let liveBox = null;
  const elsewhere = el("p", "record-elsewhere");

  function render() {
    setupBox ??= buildSetup();
    liveBox ??= buildRecording();
    heading.textContent = t("ui.record.title");
    monitoring.textContent = t("ui.record.monitoring");
    modeText.textContent = t("ui.record.stop_mode");
    modeSelect.replaceChildren(
      ...STOP_MODES.map((m) => new Option(t(`ui.record.stop_mode.${m}`), m)),
    );
    modeSelect.value = stopMode;
    const p = phase();
    hideButton.textContent = p === "recording" ? t("ui.record.hide") : t("ui.record.close");
    if (p === "recording") {
      if (body.firstChild !== liveBox) body.replaceChildren(liveBox);
      renderRecording();
    } else if (p === "elsewhere") {
      elsewhere.textContent = t("ui.record.elsewhere", { take: status.take });
      body.replaceChildren(elsewhere);
    } else {
      if (body.firstChild !== setupBox) body.replaceChildren(setupBox);
      fillSetup();
    }
    renderChip();
  }

  function renderChip() {
    if (!chip) return;
    chip.hidden = !recording();
    chip.textContent = t("ui.record.indicator", { time: formatElapsed(position, rate()) });
    chip.title = t("ui.record.indicator_title");
  }
  chip?.addEventListener("click", () => show());

  function setStatus(next) {
    const wasRecording = recording();
    status = next;
    if (next?.recording && next.ours) {
      position = Math.max(position, next.position_frames ?? 0);
      if (!wasRecording) {
        notices.splice(0, notices.length, ...(next.notices ?? []));
        newGesture();
      }
    } else if (!stopping) {
      position = 0;
      if (wasRecording) {
        // Over without us (another window, a full disk): the view has nothing left to show.
        newGesture();
        if (dialog.open) dialog.close();
      }
    }
    render();
  }

  async function refreshStatus() {
    try {
      setStatus(await api.getRecordStatus());
    } catch (error) {
      notify(error.message);
    }
  }

  function show() {
    render();
    if (!dialog.open) dialog.showModal();
    if (recording()) rec.stop.focus();
    else setup.record.focus();
  }

  function hide() {
    if (dialog.open) dialog.close();
    gesture.reset();
    gestureView = gesture.tick(now());
    renderChip();
  }

  function setStopMode(mode) {
    stopMode = stopModeChoice(mode);
    prefs.set(STOP_MODE_KEY, stopMode);
    newGesture();
    render();
  }

  function offerPending(pending) {
    if (!pending?.length) return;
    notify(t("ui.record.pending", { count: pending.length }), "error", {
      sticky: true,
      action: {
        label: t("ui.record.import_pending"),
        run: async () => {
          try {
            const response = await api.importTakes(pending.map((p) => p.take));
            apply(response);
            for (const result of response.imported ?? [])
              notify(importedMessage(result, t), "ok", { undo: true });
          } catch (error) {
            notify(error.message);
          }
        },
      },
    });
  }

  return {
    element: dialog,
    get stopMode() {
      return stopMode;
    },
    isRecording: recording,
    setStopMode,
    /** Ask the server again (after the live channel was down). */
    refresh: refreshStatus,
    /** Transport > Record…: the view, set up for a new take or showing the running one. */
    async open() {
      show();
      await refreshStatus();
      if (phase() === "setup") await loadDevices();
      show();
    },
    /** At page load: a take of ours running shows the view again; left-over takes are offered. */
    async start() {
      try {
        const first = await api.getRecordStatus();
        setStatus(first);
        if (recording()) show();
        offerPending(first.pending);
      } catch {
        // No recorder information: the editor works on; Record… asks again.
      }
    },
    /** A `{type: "record"}` frame from the live channel. */
    live(message) {
      if (message.kind === "level") {
        if (!recording()) return;
        position = message.position_frames ?? position;
        meterView = meter.update(message.peak_dbfs?.[0] ?? FLOOR_DB, now());
        if (message.clipped?.[0]) meterView = { ...meterView, clipped: true };
        if (rec.elapsed) rec.elapsed.textContent = formatElapsed(position, rate());
        renderMeter();
        renderChip();
      } else if (message.kind === "status") {
        if (!stopping) setStatus(message.status);
      } else if (message.kind === "notice") {
        notices.push({ key: message.key, level: message.level, params: message.params });
        renderNotices();
        if (!dialog.open && message.level !== "info") notify(t(message.key, message.params));
      } else if (message.kind === "imported") {
        // A take that ended by itself (disk full) or was stopped from another window.
        if (!stopping) {
          notify(importedMessage(message, t), "ok", { undo: true });
          if (dialog.open && !recording()) dialog.close();
        }
      } else if (message.kind === "pending") {
        offerPending(message.pending);
      }
    },
  };
}
