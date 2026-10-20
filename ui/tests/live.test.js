import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { connectLive, reconnectDelay } from "../live.js";

class FakeSocket extends EventTarget {
  static all = [];
  constructor(url) {
    super();
    this.url = url;
    this.closed = false;
    FakeSocket.all.push(this);
  }
  close() {
    this.closed = true;
    this.dispatchEvent(new Event("close"));
  }
  open() {
    this.dispatchEvent(new Event("open"));
  }
  say(data) {
    this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  drop() {
    this.dispatchEvent(new Event("close"));
  }
  send(text) {
    this.sent = [...(this.sent ?? []), JSON.parse(text)];
  }
}

function harness() {
  FakeSocket.all = [];
  const timers = [];
  const statuses = [];
  const messages = [];
  const stop = connectLive({
    url: "ws://x/api/live",
    onMessage: (m) => messages.push(m),
    onStatus: (s) => statuses.push(s),
    WebSocketImpl: FakeSocket,
    setTimer: (fn, ms) => {
      timers.push({ fn, ms });
      return timers.length;
    },
    clearTimer: () => {},
  });
  return { stop, timers, statuses, messages, socket: () => FakeSocket.all.at(-1) };
}

describe("the live channel", () => {
  test("on open it hands over a sender (the playhead clock's pings)", () => {
    FakeSocket.all = [];
    let send = null;
    connectLive({
      url: "ws://x/api/live",
      onMessage: () => {},
      onStatus: () => {},
      onOpen: (s) => {
        send = s;
      },
      WebSocketImpl: FakeSocket,
    });
    const socket = FakeSocket.all.at(-1);
    socket.open();
    send({ type: "ping", c: 1.5 });
    assert.deepEqual(socket.sent, [{ type: "ping", c: 1.5 }]);
  });

  test("says connecting, then open, and passes messages on", () => {
    const h = harness();
    assert.deepEqual(h.statuses, ["connecting"]);
    h.socket().open();
    h.socket().say({ type: "anchor", position: 5, playing: true });
    assert.deepEqual(h.statuses, ["connecting", "open"]);
    assert.deepEqual(h.messages, [{ type: "anchor", position: 5, playing: true }]);
  });

  test("a dropped connection shows 'reconnecting' and tries again", () => {
    const h = harness();
    h.socket().open();
    h.socket().drop();
    assert.equal(h.statuses.at(-1), "reconnecting");
    assert.equal(h.timers.length, 1);
    h.timers[0].fn();
    assert.equal(FakeSocket.all.length, 2);
    h.socket().open();
    assert.equal(h.statuses.at(-1), "open");
  });

  test("the wait grows while the server stays away, and resets once it is back", () => {
    const h = harness();
    h.socket().drop();
    h.timers.at(-1).fn();
    h.socket().drop();
    h.timers.at(-1).fn();
    h.socket().drop();
    const waits = h.timers.map((t) => t.ms);
    assert.ok(waits[1] > waits[0] && waits[2] > waits[1], waits.join());
    h.timers.at(-1).fn();
    h.socket().open();
    h.socket().drop();
    assert.equal(h.timers.at(-1).ms, waits[0]);
  });

  test("a message that is not JSON is ignored", () => {
    const h = harness();
    h.socket().open();
    h.socket().dispatchEvent(new MessageEvent("message", { data: "{nope" }));
    assert.deepEqual(h.messages, []);
  });

  test("stopping closes the socket and does not reconnect", () => {
    const h = harness();
    h.socket().open();
    h.stop();
    assert.equal(h.timers.length, 0);
  });

  test("reconnectDelay doubles from half a second up to a cap", () => {
    assert.equal(reconnectDelay(0), 500);
    assert.equal(reconnectDelay(1), 1000);
    assert.equal(reconnectDelay(2), 2000);
    assert.equal(reconnectDelay(20), 8000);
  });
});
