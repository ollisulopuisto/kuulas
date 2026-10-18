// The user's remembered settings in the browser (theme, density, animation, gates,
// recent commands, ...): one small helper so every storage access is guarded.
// Storage can be blocked (private window, site data off) or throw on any call;
// the page must work without it, so a failure is "not remembered", never an error.
// Keys live under the "kuulas." prefix (the names older code already wrote).

const PREFIX = "kuulas.";

function defaultStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** `storage` is injectable for tests; null means no storage at all. */
export function createPrefs(storage = defaultStorage()) {
  const guard = (fn, fallback) => {
    try {
      return storage ? fn(storage) : fallback;
    } catch {
      return fallback;
    }
  };
  return {
    /** The stored string, or null when missing or storage is unavailable. */
    get: (key) => guard((s) => s.getItem(PREFIX + key), null),
    /** -> whether it was stored. */
    set: (key, value) =>
      guard((s) => {
        s.setItem(PREFIX + key, String(value));
        return true;
      }, false),
    remove: (key) =>
      guard((s) => {
        s.removeItem(PREFIX + key);
        return true;
      }, false),
    getJson(key, fallback) {
      const text = guard((s) => s.getItem(PREFIX + key), null);
      if (text === null) return fallback;
      try {
        return JSON.parse(text) ?? fallback;
      } catch {
        return fallback;
      }
    },
    setJson(key, value) {
      return this.set(key, JSON.stringify(value));
    },
  };
}
