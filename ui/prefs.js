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

const FLUSH_MS = 300;

/**
 * The same API, kept on the server (GET/PUT /api/prefs -> ui-prefs.json in the user's
 * config folder) because browser storage is lost on every launch: each window is
 * served on a fresh port, i.e. a new origin. Loaded once, then served from memory;
 * changes are written through after a short delay and when the page is hidden.
 * If the server cannot be read, falls back to plain browser storage, so the page
 * still works. When the server has nothing yet, "kuulas.*" keys found in browser
 * storage are imported (one-time migration).
 */
export async function loadPrefs({
  fetchFn = globalThis.fetch?.bind(globalThis),
  storage = defaultStorage(),
  schedule = (fn, ms) => globalThis.setTimeout(fn, ms),
  target = globalThis,
} = {}) {
  let stored;
  try {
    const res = await fetchFn("/api/prefs");
    if (!res.ok) throw new Error(String(res.status));
    stored = (await res.json()).prefs;
    if (!stored || typeof stored !== "object") throw new Error("bad prefs");
  } catch {
    return createPrefs(storage);
  }
  const map = new Map(Object.entries(stored));
  let pendingSet = {};
  let pendingRemove = new Set();
  let timer = null;

  const flush = () => {
    timer = null;
    const set = pendingSet;
    const remove = [...pendingRemove];
    if (Object.keys(set).length === 0 && remove.length === 0) return;
    pendingSet = {};
    pendingRemove = new Set();
    const requeue = () => {
      // A failed write is retried with the next one, unless something newer replaced it.
      for (const [k, v] of Object.entries(set)) {
        if (!(k in pendingSet) && !pendingRemove.has(k)) pendingSet[k] = v;
      }
      for (const k of remove) {
        if (!(k in pendingSet)) pendingRemove.add(k);
      }
    };
    try {
      Promise.resolve(
        fetchFn("/api/prefs", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ set, remove }),
          keepalive: true,
        }),
      ).then((res) => {
        if (!res.ok) requeue();
      }, requeue);
    } catch {
      requeue();
    }
  };
  const queue = () => {
    if (timer === null) timer = schedule(flush, FLUSH_MS);
  };

  // One-time migration from the browser's own storage.
  if (map.size === 0 && storage) {
    try {
      for (let i = 0; i < storage.length; i++) {
        const k = storage.key(i);
        const v = k?.startsWith(PREFIX) ? storage.getItem(k) : null;
        if (v !== null) {
          map.set(k, v);
          pendingSet[k] = v;
        }
      }
    } catch {
      // Unreadable storage: nothing to import.
    }
    flush();
  }

  try {
    target.addEventListener?.("pagehide", flush);
    target.addEventListener?.("visibilitychange", () => {
      if (target.document?.visibilityState === "hidden") flush();
    });
  } catch {
    // No page to listen to (tests, workers).
  }

  return {
    get: (key) => map.get(PREFIX + key) ?? null,
    set(key, value) {
      map.set(PREFIX + key, String(value));
      pendingSet[PREFIX + key] = String(value);
      pendingRemove.delete(PREFIX + key);
      queue();
      return true;
    },
    remove(key) {
      map.delete(PREFIX + key);
      delete pendingSet[PREFIX + key];
      pendingRemove.add(PREFIX + key);
      queue();
      return true;
    },
    getJson(key, fallback) {
      const text = map.get(PREFIX + key);
      if (text === undefined) return fallback;
      try {
        return JSON.parse(text) ?? fallback;
      } catch {
        return fallback;
      }
    },
    setJson(key, value) {
      return this.set(key, JSON.stringify(value));
    },
    /** Write now (page hide, tests). */
    flush,
  };
}
