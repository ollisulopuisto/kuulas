// The cart (owner, 2026-10-23): up to seven clipboard entries carry a number 1-7, and Alt+n plays
// number n (Shift+Alt+n gives the picked entry that number). Pure: which entry a number means.
import { pasteEntry } from "./edit-plans.js";

// Seven, not nine: Option+8 and Option+9 type [ and ] on a Finnish Mac keyboard, and no default
// key is on a bracket key (docs/KEYS.md; the Finnish-layout rule).
export const CART_SLOTS = 7;

/** The entry holding cart slot `slot`, or null. */
export function cartEntry(state, slot) {
  return (state?.clipboard ?? []).find((entry) => entry.cart === slot) ?? null;
}

/** [{ slot, entry }] for 1..9, `entry` null for a free slot. */
export function cartSlots(state) {
  return Array.from({ length: CART_SLOTS }, (_, i) => ({
    slot: i + 1,
    entry: cartEntry(state, i + 1),
  }));
}

/** The entry a Shift+Alt+n gives its number to: the picked one, else the first shown. */
export function assignTarget(state) {
  return pasteEntry(state);
}

/** Remembered manual cart trim, bounded to +/-12 dB; invalid input means unity. */
export function cartTrim(value) {
  const db = Number(value);
  return Number.isFinite(db) ? Math.max(-12, Math.min(12, db)) : 0;
}

/** Serialize live cart actions so a quick second key waits for the first log ID. */
export function createCartQueue() {
  let queue = Promise.resolve();
  return (action) => {
    const result = queue.then(action);
    queue = result.catch(() => {});
    return result;
  };
}
