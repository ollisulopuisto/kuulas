// Put text on the system clipboard (WP76). The routes are passed in so the order is testable
// without a DOM: the web API (needs the click's user gesture, so call this inside the handler),
// the desktop window's native clipboard when the web view blocks the API, and last a hidden
// text field selected and copied with the old execCommand.

/** Tries each route in turn; true when one worked. Never throws. */
export async function copyText(text, { write, native, select } = {}) {
  for (const route of [write, native]) {
    if (!route) continue;
    try {
      await route(text);
      return true;
    } catch {
      // Blocked or missing: the next route.
    }
  }
  try {
    return select ? Boolean(select(text)) : false;
  } catch {
    return false;
  }
}

/** The real routes for this window. */
export function browserRoutes() {
  const bridge = globalThis.pywebview?.api;
  return {
    write: globalThis.navigator?.clipboard?.writeText
      ? (text) => globalThis.navigator.clipboard.writeText(text)
      : null,
    native: typeof bridge?.copy_text === "function" ? (text) => bridge.copy_text(text) : null,
    select(text) {
      const field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "");
      field.style.cssText = "position:fixed;top:0;left:0;opacity:0";
      document.body.append(field);
      field.select();
      try {
        return document.execCommand("copy");
      } finally {
        field.remove();
      }
    },
  };
}
