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
import { enhanceDialog } from "./dialog-keys.js";
import { createLiveTake } from "./live-take.js";
import { createPeakHold } from "./peak-hold.js";
import {
  ARM_KEEPALIVE_MS,
  armedNotice,
  armRequest,
  PREROLL_CHOICES,
  prerollChoice,
  prerollLabel,
} from "./preroll.js";
import {
  channelPeaks,
  formatElapsed,
  importedMessage,
  initialRows,
  meterLabels,
  pickDevice,
  recordKeyAction,
  recordPhase,
  replacedMessage,
  selectedLanes,
  startProblem,
  startRequest,
  stopLabel,
} from "./record-model.js";
import { CONFIRM_MS, createStopGesture, STOP_MODES, stopModeChoice } from "./stop-mode.js";

const STOP_MODE_KEY = "recordStopMode";
const DEVICE_KEY = "recordDevice";
const CHANNELS_KEY = "recordChannels"; // the channels last recorded, as a list of numbers
const PREROLL_KEY = "recordPreroll";
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
 * answer; `notify(text, kind, options)` is the app's notice; `chip` the toolbar's indicator;
 * `addMarker()` adds a marker at the take's place now (the Marker button; BUGS #106);
 * `onLive()` is called when the take drawn on the timeline (live-take.js) has changed.
 */
export function createRecordView({
  api,
  t,
  prefs,
  getState,
  apply,
  notify,
  chip,
  addMarker = () => {},
  onLive = () => {},
}) {
  let status = null;
  let devices = null;
  let deviceError = "";
  let preroll = prerollChoice(prefs.get(PREROLL_KEY));
  let armTimer = null;
  let stopMode = stopModeChoice(prefs.get(STOP_MODE_KEY));
  let gesture = createStopGesture({ mode: stopMode });
  let gestureView = gesture.tick(0);
  let stopping = false;
  let frame = null;
  let position = 0;
  // The take drawn on the timeline lanes while it records (owner, 2026-10-23).
  const liveTake = createLiveTake();
  const notices = [];
  // One level meter per channel (WP12b): the setup's while armed (by channel number) and the
  // take's while recording (in the recorder's order, which is channel order).
  let rows = [];
  let rowsDeviceKey = "";
  let rowsSig = null;
  const rowEls = [];
  const setupMeters = new Map();
  let liveMeters = [];
  let liveKey = "";

  /** A meter with its label and its own clip flag; `labelText` also names it for a screen reader. */
  function createMeter(labelText) {
    const row = el("div", "record-meter-row");
    const label = el("span", "record-meter-label", labelText);
    const box = el("div", "record-meter");
    box.setAttribute("role", "img");
    box.setAttribute("aria-label", labelText);
    const fill = el("i", "record-meter-fill");
    const hold = el("i", "record-meter-hold");
    box.append(fill, hold);
    const clip = el("button", "record-clip", t("ui.record.clip"));
    clip.type = "button";
    clip.title = t("ui.record.clip_title");
    clip.hidden = true;
    row.append(label, box, clip);
    const tracker = createPeakHold({ floorDb: FLOOR_DB });
    const meter = {
      row,
      label,
      fill,
      hold,
      clip,
      tracker,
      view: { bar: FLOOR_DB, peak: FLOOR_DB, clipped: false },
    };
    clip.addEventListener("click", () => {
      tracker.clearClip();
      meter.view = { ...meter.view, clipped: false };
      paintMeter(meter);
    });
    return meter;
  }

  function paintMeter(m) {
    const pct = (db) => `${Math.max(0, Math.min(100, ((db - FLOOR_DB) / -FLOOR_DB) * 100))}%`;
    m.fill.style.width = pct(m.view.bar);
    m.hold.style.left = pct(m.view.peak);
    m.fill.dataset.zone = m.view.bar > -6 ? "hot" : m.view.bar > -18 ? "warn" : "ok";
    m.clip.hidden = !m.view.clipped;
  }

  function feedMeter(m, reading) {
    m.view = m.tracker.update(reading.db, performance.now());
    if (reading.clipped) m.view = { ...m.view, clipped: true };
    paintMeter(m);
  }

  // -- the frame -----------------------------------------------------------------------
  const dialog = el("dialog", "cheatsheet record-view");
  dialog.setAttribute("aria-labelledby", "record-title");
  const heading = el("h2", "record-title");
  heading.id = "record-title";
  const body = el("div", "record-body");
  const monitoring = el("p", "record-monitoring");
  const footer = el("div", "cheatsheet-footer record-footer");
  const modeLabel = el("label", "record-mode footer-start");
  const modeText = el("span");
  const modeSelect = el("select");
  modeLabel.append(modeText, modeSelect);
  const hideButton = el("button", "button block");
  hideButton.type = "button";
  hideButton.dataset.dialogCancel = "";
  footer.append(modeLabel, hideButton);
  dialog.append(heading, body, monitoring, footer);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });

  const phase = () => (stopping ? "recording" : recordPhase(status));
  const recording = () => phase() === "recording";
  const rate = () => status?.rate ?? getState().project?.rate ?? 48000;
  /** The stop notice, with what the take replaced when it went over existing audio. */
  const withReplaced = (text, result) => {
    const extra = replacedMessage(result, rate(), t);
    return extra ? `${text} ${extra}` : text;
  };
  // The take's clock starts at the pre-roll; "Recorded" counts from where Record was pressed.
  const shownPosition = () => Math.max(0, position - (status?.preroll_frames ?? 0));

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
      const label = el("label", "record-field form-row");
      label.append(el("span", "record-label form-label", labelText), control);
      box.append(label);
      return control;
    };
    setup.device = row(t("ui.record.device"), el("select"));
    // Every channel of the input: whether to record it and onto which track (WP12b).
    setup.channels = el("fieldset", "record-channels");
    setup.channels.append(el("legend", "form-heading", t("ui.record.channels")));
    box.append(setup.channels);
    setup.preroll = row(t("ui.record.preroll"), el("select"));
    setup.armed = el("p", "record-armed");
    setup.armed.setAttribute("role", "status");
    setup.at = el("p", "record-at");
    setup.disk = el("p", "record-disk");
    setup.message = el("p", "record-message");
    setup.message.setAttribute("role", "status");
    setup.record = el("button", "button record-button", t("ui.record.record"));
    setup.record.type = "button";
    box.append(setup.armed, setup.at, setup.disk, setup.message, setup.record);
    setup.device.addEventListener("change", () => {
      const device = devices?.[Number(setup.device.value)];
      if (device) prefs.setJson(DEVICE_KEY, { index: device.index, name: device.name });
      fillSetup();
      void syncArm();
    });
    setup.preroll.addEventListener("change", () => setPreroll(setup.preroll.value));
    setup.record.addEventListener("click", () => void start());
    return box;
  }

  const chosenDevice = () => devices?.[Number(setup.device.value)] ?? null;
  const chosenChannels = () => selectedLanes(rows).map((lane) => lane.channel);

  /** One row per channel of the chosen input: use it, onto which track, named what. */
  function buildRows(tracks) {
    rowEls.length = 0;
    setupMeters.clear();
    const items = rows.map((r) => {
      const item = el("div", "record-channel");
      const use = el("label", "record-channel-use");
      const check = el("input");
      check.type = "checkbox";
      use.append(check, el("span", "", t("ui.record.channel_n", { n: r.channel })));
      const target = el("select");
      target.setAttribute("aria-label", t("ui.record.channel_track_label", { n: r.channel }));
      target.replaceChildren(
        new Option(t("ui.record.new_track"), "new"),
        ...tracks.map((track) => new Option(track.name, track.id)),
      );
      const name = el("input");
      name.type = "text";
      name.autocomplete = "off";
      name.placeholder = t("record.channel_track", { n: r.channel });
      name.setAttribute("aria-label", t("ui.record.channel_name_label", { n: r.channel }));
      const meter = createMeter(t("ui.record.level_of", { name: String(r.channel) }));
      meter.label.hidden = true;
      setupMeters.set(r.channel, meter);
      check.addEventListener("change", () => {
        r.on = check.checked;
        prefs.setJson(CHANNELS_KEY, chosenChannels());
        fillSetup();
        void syncArm();
      });
      target.addEventListener("change", () => {
        r.target = target.value;
        fillSetup();
      });
      name.addEventListener("input", () => {
        r.name = name.value;
      });
      item.append(use, target, name, meter.row);
      rowEls.push({ check, target, name, meter });
      return item;
    });
    setup.channels.replaceChildren(setup.channels.firstChild, ...items);
  }

  /** The rows' controls follow the model (and the armed state, for the meters). */
  function syncRows() {
    const armed = preroll > 0 && Boolean(status?.armed);
    rows.forEach((r, i) => {
      const e = rowEls[i];
      if (!e) return;
      e.check.checked = r.on;
      e.target.value = r.target;
      e.target.disabled = !r.on;
      e.name.value = r.name;
      e.name.disabled = !r.on || r.target !== "new";
      e.meter.row.hidden = !(armed && r.on);
    });
  }

  function fillRows() {
    const device = chosenDevice();
    const tracks = getState().project?.tracks ?? [];
    const deviceKey = `${device?.index}|${device?.name}|${device?.channels}`;
    if (deviceKey !== rowsDeviceKey) {
      const remembered = prefs.getJson(CHANNELS_KEY, null);
      rows = initialRows(device, Array.isArray(remembered) ? remembered : null);
      rowsDeviceKey = deviceKey;
      rowsSig = null;
    }
    const sig = tracks.map((track) => `${track.id}:${track.name}`).join("|");
    if (sig !== rowsSig) {
      rowsSig = sig;
      for (const r of rows)
        if (r.target !== "new" && !tracks.some((track) => track.id === r.target)) r.target = "new";
      buildRows(tracks);
    }
    syncRows();
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
    fillRows();
    setup.preroll.replaceChildren(
      ...PREROLL_CHOICES.map((s) => new Option(prerollLabel(s, t), String(s))),
    );
    setup.preroll.value = String(preroll);
    setup.armed.textContent = armedNotice(status, preroll, t);
    setup.armed.dataset.armed = preroll > 0 && status?.armed ? "on" : "off";
    setup.at.textContent = t("ui.record.at", {
      time: formatElapsed(state.playhead ?? 0, rate()),
    });
    renderDisk(setup.disk);
    let message = "";
    if (deviceError) message = deviceError;
    else if (devices === null) message = t("ui.record.loading");
    else if (list.length === 0) message = t("ui.record.no_devices");
    const problem = chosen ? startProblem(rows) : null;
    if (!message && problem) message = t(problem);
    setup.message.textContent = message;
    setup.record.disabled = !chosen || stopping || problem !== null;
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

  // -- pre-roll: listening while this view is open (WP12c) ---------------------------------
  // The recorder keeps the last N seconds in memory while armed and writes nothing. The view
  // arms it when it is open in setup with pre-roll on, repeats that as a keepalive (the recorder
  // lets go by itself after two minutes without), and disarms when it closes or pre-roll is off.
  // Calls queue, so a start right after a click on a channel waits for the arm that click sent
  // (an armed recorder refuses a take for other channels than the ones it listens to).
  let armQueue = Promise.resolve();
  function syncArm() {
    armQueue = armQueue.then(doArm);
    return armQueue;
  }
  async function doArm() {
    if (!dialog.open || phase() !== "setup" || stopping) return;
    const device = chosenDevice();
    try {
      if (preroll === 0 || !device) {
        if (status?.armed) setStatus(await api.disarmRecording());
        return;
      }
      const channels = chosenChannels();
      if (channels.length === 0) return;
      setStatus(await api.armRecording(armRequest({ device, channels, seconds: preroll })));
    } catch (error) {
      setup.message.textContent = error.message;
    }
    // Closed while the recorder was opening the input: let it go again.
    if (!dialog.open) void releaseArm();
  }

  function startKeepalive() {
    if (armTimer === null) armTimer = setInterval(() => void syncArm(), ARM_KEEPALIVE_MS);
  }

  async function releaseArm() {
    if (armTimer !== null) clearInterval(armTimer);
    armTimer = null;
    if (recording() || stopping || !status?.armed) return;
    try {
      setStatus(await api.disarmRecording());
    } catch {
      // The recorder lets go by itself after two minutes.
    }
  }
  dialog.addEventListener("close", () => void releaseArm());

  async function start() {
    const device = chosenDevice();
    if (startProblem(rows) !== null) return;
    setup.record.disabled = true;
    try {
      // Armed for these very settings, or the take would have no pre-roll.
      if (preroll > 0) await syncArm();
      const answer = await api.startRecording(
        startRequest({ device, lanes: selectedLanes(rows), at: getState().playhead ?? 0 }),
      );
      notices.length = 0;
      position = 0;
      liveMeters = [];
      liveKey = "";
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
    rec.meters = el("div", "record-meters");
    rec.disk = el("p", "record-disk");
    rec.preroll = el("p", "record-preroll-note");
    rec.notices = el("ul", "record-notices");
    rec.notices.setAttribute("aria-live", "assertive");
    rec.marker = el("button", "button record-marker", t("ui.record.add_marker"));
    rec.marker.type = "button";
    rec.marker.title = t("ui.record.add_marker_title");
    rec.marker.addEventListener("click", () => addMarker());
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
    box.append(
      rec.take,
      rec.elapsed,
      rec.preroll,
      rec.meters,
      rec.disk,
      rec.notices,
      rec.marker,
      rec.stop,
      rec.stopHelp,
    );
    return box;
  }

  /** The take's meters: one per recorded channel, labelled with its track (rebuilt when the lanes change). */
  function renderMeters() {
    const lanes =
      status?.plan?.lanes ??
      (status?.channels ?? []).map((c) => ({ channel: c.channel, track_name: c.name }));
    const key = lanes.map((l) => `${l.channel}:${l.track_name}`).join("|");
    if (key === liveKey) return;
    liveKey = key;
    liveMeters = meterLabels(lanes, t).map((m) => createMeter(m.text));
    rec.meters.replaceChildren(...liveMeters.map((m) => m.row));
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
    rec.elapsed.textContent = formatElapsed(shownPosition(), rate());
    const included = Math.round((status?.preroll_frames ?? 0) / rate());
    rec.preroll.textContent =
      included > 0 ? t("ui.record.preroll_included", { seconds: included }) : "";
    rec.preroll.hidden = included <= 0;
    renderDisk(rec.disk);
    renderMeters();
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
      if (imported)
        notify(withReplaced(importedMessage(imported, t), imported), "ok", { undo: true });
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
    chip.textContent = t("ui.record.indicator", { time: formatElapsed(shownPosition(), rate()) });
    chip.title = t("ui.record.indicator_title");
  }
  chip?.addEventListener("click", () => show());

  function setStatus(next) {
    const wasRecording = recording();
    status = next;
    if (next?.recording && next.ours) {
      position = Math.max(position, next.position_frames ?? 0);
      if (!liveTake.active) {
        liveTake.begin({
          at: next.plan?.at ?? 0,
          preroll: next.preroll_frames ?? 0,
          lanes: (next.plan?.lanes ?? []).map((lane) => ({ trackId: lane.track_id })),
        });
      }
      if (!wasRecording) {
        notices.splice(0, notices.length, ...(next.notices ?? []));
        newGesture();
      }
    } else if (!stopping) {
      position = 0;
      if (liveTake.active) {
        liveTake.reset();
        onLive();
      }
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
      setStatus(await api.getRecordStatus(chosenChannels().length));
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

  function setPreroll(seconds) {
    preroll = prerollChoice(seconds);
    prefs.set(PREROLL_KEY, preroll);
    render();
    void syncArm();
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
              notify(withReplaced(importedMessage(result, t), result), "ok", { undo: true });
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
    get preroll() {
      return preroll;
    },
    isRecording: recording,
    /** The take so far, as peaks per lane (live-take.js), for the timeline to draw. */
    liveTake,
    /** Where the take is on the timeline now (its start plus what was recorded, pre-roll
     *  not counted: where the take's clips will put this moment), or null when not recording. */
    liveFrame: () => (recording() ? (status?.plan?.at ?? 0) + shownPosition() : null),
    setStopMode,
    setPreroll,
    /** Ask the server again (after the live channel was down). */
    refresh: refreshStatus,
    /** Transport > Record…: the view, set up for a new take or showing the running one. */
    async open() {
      show();
      await refreshStatus();
      if (phase() === "setup") await loadDevices();
      show();
      if (phase() === "setup") {
        startKeepalive();
        void syncArm();
      }
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
        if (!recording()) {
          // Armed: every armed channel's meter shows the input before Record (the readings
          // come in the order of the channels the recorder was armed with).
          const armed = status?.armed_channels ?? [];
          if (status?.armed && setupMeters.size) {
            const readings = channelPeaks(message, armed.length);
            armed.forEach((channel, i) => {
              const meter = setupMeters.get(channel);
              if (meter) feedMeter(meter, readings[i]);
            });
          }
          return;
        }
        position = message.position_frames ?? position;
        liveTake.push(
          message.position_frames,
          Array.from({ length: message.peak_dbfs?.length ?? 0 }, (_, i) => message.peak_dbfs[i]),
        );
        onLive();
        const readings = channelPeaks(message, liveMeters.length);
        liveMeters.forEach((meter, i) => {
          feedMeter(meter, readings[i]);
        });
        if (rec.elapsed) rec.elapsed.textContent = formatElapsed(shownPosition(), rate());
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
          notify(withReplaced(importedMessage(message, t), message), "ok", { undo: true });
          if (dialog.open && !recording()) dialog.close();
        }
      } else if (message.kind === "pending") {
        offerPending(message.pending);
      }
    },
  };
}
