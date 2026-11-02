// The loudness readout in a track header (WP49): the track's integrated loudness against its
// target, "−21,3 / −19 LUFS", tinted by loudness-tint.js. Pure except for the loader, whose
// environment (timers, the request) is injected. The numbers come from analysis
// (GET /api/loudness-curve), not from the audio that is playing now.
import { loudnessState } from "./loudness-tint.js";

const CACHE_HEADS = 8;
// After a failed measure: the first retry waits this long, each next one twice as long.
const BACKOFF_MS = 5000;
const BACKOFF_MAX_MS = 300000;

/**
 * What a header shows for one track. `loudness` is `{ head, status, tracks }` (store.js):
 * `status` "pending" | "ready" | "failed", `tracks` keyed by id with `{ integrated, target }`.
 * Phases: "none" (draw nothing), "pending" ("…"), "value". A value read while a newer
 * measure is running is `stale`: still shown, dimmed, so an edit does not make it flicker.
 */
export function trackReadout(loudness, trackId) {
  if (!loudness || loudness.status === "failed") return { phase: "none" };
  const pending = loudness.status === "pending";
  const entry = loudness.tracks?.[trackId];
  if (!entry) return { phase: pending ? "pending" : "none" };
  if (entry.integrated == null || !Number.isFinite(entry.integrated)) return { phase: "none" };
  const target = entry.target ?? null;
  return {
    phase: "value",
    integrated: entry.integrated,
    target,
    state: loudnessState(entry.integrated, target),
    stale: pending,
  };
}

/** "−21,3 / −19 LUFS"; the target keeps a decimal only when it has one. */
export function readoutText(readout, formatNumber, t) {
  if (readout.phase === "pending") return "…";
  if (readout.phase !== "value") return "";
  const value = formatNumber(readout.integrated, { digits: 1 });
  if (readout.target == null) return t("ui.loudness.readout_no_target", { value });
  const whole = Number.isInteger(readout.target);
  const target = formatNumber(readout.target, { digits: whole ? 0 : 1 });
  return t("ui.loudness.readout", { value, target });
}

/**
 * Asks for the curve in the background once the project has settled. `settle(head)` is called
 * on every change of the project: it restarts a short wait, cancels a request that is no longer
 * for the current head, serves a head seen before from the cache and otherwise asks once.
 * Never throws and never waits for anything: results arrive through `onChange({ loudness })`.
 */
export function createLoudnessLoader({
  fetchCurve,
  onChange,
  delayMs = 700,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
}) {
  const cache = new Map(); // head -> tracks
  let current = null; // the head last announced (pending or ready)
  let timer = null;
  let controller = null;
  let lastTracks = {}; // shown (stale) while a newer measure runs
  let failures = 0; // in a row
  let backoff = null; // the one retry after a failure

  const cancel = () => {
    if (timer !== null) clearTimer(timer);
    timer = null;
    controller?.abort();
    controller = null;
  };

  const tracksOf = (body) => {
    const out = {};
    for (const track of body?.tracks ?? []) {
      out[track.track_id] = { integrated: track.integrated ?? null, target: track.target_lufs };
    }
    return out;
  };

  async function run(head) {
    timer = null;
    const mine = new AbortController();
    controller = mine;
    try {
      const tracks = tracksOf(await fetchCurve(mine.signal));
      if (mine.signal.aborted) return; // a newer head took over
      failures = 0;
      cache.set(head, tracks);
      if (cache.size > CACHE_HEADS) cache.delete(cache.keys().next().value);
      lastTracks = tracks;
      onChange({ loudness: { head, status: "ready", tracks } });
    } catch {
      if (mine.signal.aborted) return;
      // Not cached, and not asked again at the next settle (every store change
      // settles; each ask used to start an analysis process, owner's ps
      // 2026-10-20): one retry, for whatever head is current then, after a
      // back-off that doubles with every failure in a row.
      failures += 1;
      onChange({ loudness: { head, status: "failed", tracks: {} } });
      const wait = Math.min(BACKOFF_MS * 2 ** (failures - 1), BACKOFF_MAX_MS);
      backoff = setTimer(() => {
        backoff = null;
        if (current !== null && !cache.has(current)) void run(current);
      }, wait);
    } finally {
      if (controller === mine) controller = null;
    }
  }

  return {
    settle(head) {
      if (head === null || head === undefined || head === current) return;
      cancel();
      current = head;
      if (cache.has(head)) {
        lastTracks = cache.get(head);
        onChange({ loudness: { head, status: "ready", tracks: lastTracks } });
        return;
      }
      onChange({ loudness: { head, status: "pending", tracks: lastTracks } });
      // After a failure the back-off's retry asks, for the head current then.
      if (backoff === null) timer = setTimer(() => void run(head), delayMs);
    },
  };
}

/** Contextual integrated measurement: never present a pending old result as live. */
export function contextualReadout(loudness, trackId, formatNumber, t) {
  const value = trackReadout(loudness, trackId);
  if (value.phase === "pending") return t("ui.loudness.pending");
  if (value.phase === "none") return t("ui.loudness.unavailable");
  const text = readoutText(value, formatNumber, t);
  return value.stale ? `${text} · ${t("ui.loudness.updating")}` : text;
}
