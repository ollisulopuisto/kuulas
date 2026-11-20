import { initI18n } from "../../i18n.js";
import { createSyncReview } from "../../sync-review.js";

await initI18n({ language: "en" });
const project = {
  rate: 48000,
  media: [],
  tracks: [
    {
      id: "a",
      name: "Anchor",
      clips: [{ id: "a1", media: "m", start: 0, length: 4800000, offset: 0 }],
    },
    {
      id: "b",
      name: "Guest B",
      clips: [{ id: "b1", media: "m", start: 48000, length: 480000, offset: 0 }],
    },
    {
      id: "c",
      name: "Guest C",
      clips: [{ id: "c1", media: "m", start: 48000, length: 480000, offset: 0 }],
    },
  ],
};
const review = {
  id: "r",
  project,
  tracks: ["a", "b", "c"],
  anchor: "a",
  offsets: { a1: 0, b1: 4800, c1: 9600 },
  suggestion: { a1: 0, b1: 4800, c1: 9600 },
};
const calls = [];
let failListen = false;
const nativeFetch = globalThis.fetch;
globalThis.fetch = async (path, options) => {
  if (String(path).startsWith("/api/locales/")) return nativeFetch(path, options);
  if (String(path).startsWith("/api/peaks/")) return new Response(new Float32Array(2048).buffer);
  const body = options?.body ? JSON.parse(options.body) : null;
  calls.push({ path, body });
  if (path === "/api/sync-review/move") {
    if (body.frames < 0)
      return new Response(JSON.stringify({ error: { text: "Cannot move before zero" } }), {
        status: 409,
      });
    const ids = body.clip
      ? [body.clip]
      : project.tracks.find((t) => t.id === body.track).clips.map((c) => c.id);
    for (const id of ids)
      review.offsets[id] = body.clip ? body.frames : review.offsets[id] + body.frames;
  }
  if (path === "/api/transport") return Response.json({ playing: false, position: 0 });
  if (path === "/api/sync-review/listen") {
    if (failListen)
      return Response.json({ error: { text: "Playback device unavailable" } }, { status: 409 });
    return Response.json({ started: true });
  }
  return Response.json(structuredClone(review));
};
const notices = [];
const ui = createSyncReview({
  t: (key) => key.replace("ui.sync_review.", ""),
  getState: () => ({ project }),
  refresh: async () => {},
  notice: (x) => notices.push(x),
});
const pause = () => new Promise((r) => setTimeout(r, 30));
try {
  await ui.open();
  await pause();
  document.querySelector('[data-clip="b1"]').focus();
  const candidate = document.querySelector('[data-clip="c1"]');
  candidate.setPointerCapture = () => {};
  candidate.dispatchEvent(
    new PointerEvent("pointerdown", { bubbles: true, clientX: 220, pointerId: 1 }),
  );
  candidate.dispatchEvent(
    new PointerEvent("pointerup", { bubbles: true, clientX: 220, pointerId: 1 }),
  );
  await pause();
  [...document.querySelectorAll(".sync-review button")]
    .find((x) => x.textContent === "right")
    .click();
  await pause();
  const pointerTarget = calls.filter((x) => x.path === "/api/sync-review/move").at(-1)?.body.track;
  calls.length = 0;
  document.querySelector('[data-clip="c1"]').focus();
  const focused = document.activeElement;
  const label = document.querySelector(".sync-review-controls strong").textContent;
  const field = document.querySelector(".sync-review-controls input");
  const fieldBefore = field.value;
  const focusKept = focused.isConnected && document.activeElement === focused;
  field.value = ".500";
  field.dispatchEvent(new Event("change"));
  await pause();
  const move = calls.find((x) => x.path === "/api/sync-review/move");
  const keyboard = {
    label,
    fieldBefore,
    focusKept,
    movedTrack: move?.body.track,
    frames: review.offsets.c1,
  };
  [...document.querySelectorAll(".sync-review button")]
    .find((x) => x.textContent === "left")
    .click();
  await pause();
  const alert = document.querySelector('.sync-review [role="alert"]');
  const errorVisible = Boolean(alert?.textContent.includes("Cannot move before zero"));
  [...document.querySelectorAll(".sync-review button")]
    .find((x) => x.textContent === "play")
    .click();
  await pause();
  const svg = document.querySelector(".sync-review svg");
  const box = svg.getBoundingClientRect();
  svg.dispatchEvent(
    new PointerEvent("pointerdown", {
      bubbles: true,
      clientX: box.left + 700,
      clientY: box.top + 35,
    }),
  );
  await pause();
  const seeks = calls.filter((x) => x.path === "/api/sync-review/listen" && x.body?.at > 480000);
  const clickButton = (key) =>
    [...document.querySelectorAll(".sync-review button")]
      .find((x) => x.textContent === key)
      .click();
  clickButton("loop");
  await pause();
  clickButton("original");
  await pause();
  const anchor = document.querySelector('[data-clip="a1"]');
  anchor.dispatchEvent(
    new PointerEvent("pointerdown", {
      bubbles: true,
      clientX: box.left + 800,
      clientY: box.top + 60,
    }),
  );
  await pause();
  const lastListen = calls.filter((x) => x.path === "/api/sync-review/listen").at(-1).body;
  const boundedOriginalSeek =
    lastListen.original === true &&
    lastListen.loop === true &&
    lastListen.seconds === 6 &&
    lastListen.at > 480000;
  failListen = true;
  clickButton("audition");
  await pause();
  const playbackErrorVisible = document
    .querySelector('.sync-review [role="alert"]')
    .textContent.includes("Playback device unavailable");
  document.querySelector("#result").textContent = JSON.stringify({
    keyboard,
    pointerTarget,
    boundedOriginalSeek,
    playbackErrorVisible,
    errorVisible,
    seekSent: seeks.length > 0,
  });
} catch (error) {
  document.querySelector("#result").textContent = JSON.stringify({
    error: String(error),
    stack: error.stack,
  });
}
