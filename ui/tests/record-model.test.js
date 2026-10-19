import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  channelChoices,
  channelPeaks,
  formatElapsed,
  importedMessage,
  initialRows,
  meterLabels,
  pickDevice,
  recordKeyAction,
  recordPhase,
  selectedLanes,
  startProblem,
  startRequest,
  stopLabel,
} from "../record-model.js";

const t = (key, params = {}) => `${key}${JSON.stringify(params)}`;

describe("phase", () => {
  test("from the server's status", () => {
    assert.equal(recordPhase(null), "loading");
    assert.equal(recordPhase({ available: false, recording: false }), "setup");
    assert.equal(recordPhase({ available: true, recording: true, ours: true }), "recording");
    assert.equal(recordPhase({ available: true, recording: true, ours: false }), "elsewhere");
    assert.equal(recordPhase({ available: true, recording: false }), "setup");
  });
});

describe("elapsed", () => {
  test("minutes and seconds under an hour, hours above", () => {
    assert.equal(formatElapsed(0, 48000), "0:00");
    assert.equal(formatElapsed(48000 * 75.9, 48000), "1:15");
    assert.equal(formatElapsed(48000 * 3725, 48000), "1:02:05");
  });
  test("nonsense reads as zero", () => {
    assert.equal(formatElapsed(-5, 48000), "0:00");
    assert.equal(formatElapsed(Number.NaN, 48000), "0:00");
    assert.equal(formatElapsed(100, 0), "0:00");
  });
});

describe("devices", () => {
  const devices = [
    { index: 0, name: "MacBook Mic", channels: 1, default: true },
    { index: 3, name: "Scarlett 2i2", channels: 2, default: false },
  ];
  test("the remembered device by name wins, though its index moved", () => {
    assert.equal(pickDevice(devices, { index: 7, name: "Scarlett 2i2" }).index, 3);
  });
  test("else the system default, else the first", () => {
    assert.equal(pickDevice(devices, { name: "Gone" }).index, 0);
    assert.equal(pickDevice([devices[1]], null).index, 3);
    assert.equal(pickDevice([], null), null);
  });
  test("channels are 1..n", () => {
    assert.deepEqual(channelChoices(devices[1]), [1, 2]);
    assert.deepEqual(channelChoices(null), [1]);
  });
});

describe("the start request", () => {
  test("a new track carries its name", () => {
    assert.deepEqual(
      startRequest({
        device: { index: 3, name: "Scarlett 2i2", channels: 2 },
        channel: 2,
        target: "new",
        name: "  Guest ",
        at: 4800.4,
      }),
      {
        device: { index: 3, name: "Scarlett 2i2" },
        channel: 2,
        track_id: null,
        name: "Guest",
        at: 4800,
      },
    );
  });
  test("an existing track by id; a negative playhead starts at 0", () => {
    const body = startRequest({ device: null, channel: 1, target: "t1", name: "", at: -3 });
    assert.equal(body.track_id, "t1");
    assert.equal(body.device, null);
    assert.equal(body.at, 0);
  });
});

describe("the stop button's words", () => {
  test("per mode and state", () => {
    assert.equal(stopLabel({ state: "recording" }, "two_step", t), "ui.record.stop{}");
    assert.equal(
      stopLabel({ state: "confirming", secondsLeft: 3 }, "two_step", t),
      'ui.record.stop_confirm{"seconds":3}',
    );
    assert.equal(stopLabel({ state: "recording" }, "hold", t), "ui.record.stop_hold{}");
    assert.equal(stopLabel({ state: "holding" }, "hold", t), "ui.record.stop_hold{}");
    assert.equal(stopLabel({ state: "recording" }, "one_click", t), "ui.record.stop{}");
    assert.equal(stopLabel({ state: "stopped" }, "two_step", t), "ui.record.stopping{}");
  });
});

describe("keys while recording", () => {
  test("Space presses the stop control only while the view shows", () => {
    assert.equal(recordKeyAction({ key: " " }, { visible: true }), "press");
    assert.equal(recordKeyAction({ key: " ", repeat: true }, { visible: true }), "swallow");
    // hidden: Space brings the view back, it never starts playback (no listening)
    assert.equal(recordKeyAction({ key: " " }, { visible: false }), "show");
  });
  test("Esc hides; Tab moves focus; the rest does nothing in the view", () => {
    assert.equal(recordKeyAction({ key: "Escape" }, { visible: true }), "hide");
    assert.equal(recordKeyAction({ key: "Tab" }, { visible: true }), "pass");
    assert.equal(recordKeyAction({ key: "Enter" }, { visible: true }), "swallow");
    assert.equal(recordKeyAction({ key: "z", metaKey: true }, { visible: true }), "swallow");
  });
  test("with the view hidden, editing keys work as usual", () => {
    assert.equal(recordKeyAction({ key: "z", metaKey: true }, { visible: false }), "pass");
    assert.equal(recordKeyAction({ key: "Escape" }, { visible: false }), "pass");
  });
  test("a keystroke in a form field of the view is the field's", () => {
    assert.equal(recordKeyAction({ key: " ", inField: true }, { visible: true }), "pass");
  });
});

describe("after the take", () => {
  test("the message says what happened", () => {
    assert.equal(
      importedMessage({ take: "Take 2", clips: 1, gaps: 0, interrupted: false }, t),
      'ui.record.imported{"take":"Take 2","count":1}',
    );
    assert.equal(
      importedMessage({ take: "Take 2", clips: 2, gaps: 1, interrupted: false }, t),
      'ui.record.imported_gaps{"take":"Take 2","count":1}',
    );
    assert.equal(
      importedMessage({ take: "Take 2", clips: 1, gaps: 0, interrupted: true }, t),
      'ui.record.imported_interrupted{"take":"Take 2"}',
    );
  });
});

describe("several channels (WP12b)", () => {
  const scarlett = { index: 3, name: "Scarlett 2i2", channels: 4 };
  test("a device's channels start with the remembered ones on, else channel 1", () => {
    assert.deepEqual(
      initialRows(scarlett, [2, 3]).map((r) => [r.channel, r.on]),
      [
        [1, false],
        [2, true],
        [3, true],
        [4, false],
      ],
    );
    assert.deepEqual(
      initialRows(scarlett, null).map((r) => r.on),
      [true, false, false, false],
    );
    // remembered channels this device lacks are no use: channel 1 then
    assert.deepEqual(
      initialRows({ channels: 2 }, [5, 6]).map((r) => r.on),
      [true, false],
    );
  });
  test("a row is a new track until the user picks one", () => {
    const [row] = initialRows(scarlett, null);
    assert.equal(row.target, "new");
    assert.equal(row.name, "");
  });
  test("the lanes are the rows that are on, in channel order", () => {
    const rows = initialRows(scarlett, [3, 1]);
    rows[2].name = " Guest ";
    rows[0].target = "t1";
    assert.deepEqual(selectedLanes(rows), [
      { channel: 1, track_id: "t1", name: "" },
      { channel: 3, track_id: null, name: "Guest" },
    ]);
  });
  test("the request carries every lane, and the one-channel form still works", () => {
    const rows = initialRows(scarlett, [1, 2]);
    const body = startRequest({ device: scarlett, lanes: selectedLanes(rows), at: 9.6 });
    assert.deepEqual(body.channels, [
      { channel: 1, track_id: null, name: "" },
      { channel: 2, track_id: null, name: "" },
    ]);
    assert.equal(body.at, 10);
    assert.equal("channel" in body, false);
  });
  test("nothing chosen, or one track chosen twice, is a problem before Record", () => {
    const rows = initialRows(scarlett, [1, 2]);
    assert.equal(startProblem(rows), null);
    rows[0].target = "t1";
    rows[1].target = "t1";
    assert.equal(startProblem(rows), "error.record.same_track");
    for (const r of rows) r.on = false;
    assert.equal(startProblem(rows), "ui.record.no_channel");
  });
  test("two new tracks may have the same name; the server numbers them", () => {
    const rows = initialRows(scarlett, [1, 2]);
    rows[0].name = "Mic";
    rows[1].name = "Mic";
    assert.equal(startProblem(rows), null);
  });
  test("meters are labelled with the track each channel goes to", () => {
    const lanes = [
      { channel: 1, track_name: "Host" },
      { channel: 3, track_name: "Guest" },
    ];
    assert.deepEqual(
      meterLabels(lanes, t).map((m) => m.text),
      ['ui.record.level_of{"name":"Host"}', 'ui.record.level_of{"name":"Guest"}'],
    );
    assert.deepEqual(meterLabels(null, t), []);
  });
  test("a level frame is read per channel; a missing channel reads as silence", () => {
    assert.deepEqual(channelPeaks({ peak_dbfs: [-12, -3], clipped: [false, true] }, 3), [
      { db: -12, clipped: false },
      { db: -3, clipped: true },
      { db: -120, clipped: false },
    ]);
  });
  test("a take that lost a channel says so", () => {
    assert.equal(
      importedMessage(
        { take: "Take 2", clips: 1, gaps: 0, interrupted: false, failed_channels: ["Guest"] },
        t,
      ),
      'ui.record.imported_failed{"take":"Take 2","names":"Guest"}',
    );
  });
});
