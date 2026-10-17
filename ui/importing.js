// Import by file picker or drag and drop: reading the server's report.

const baseName = (path) => String(path).split(/[\\/]/).pop();

/** { imported, failures: [{name, text}], warnings: [{name, text}] } from `report`. */
export function summariseImport(report) {
  const out = { imported: 0, failures: [], warnings: [] };
  for (const item of report ?? []) {
    const name = baseName(item.path);
    if (item.ok) out.imported += 1;
    else out.failures.push({ name, text: item.error?.text ?? "" });
    for (const warning of item.warnings ?? []) out.warnings.push({ name, text: warning.text });
  }
  return out;
}

/** Does this drag carry files (and not, say, selected text)? */
export function dragHasFiles(dataTransfer) {
  return Array.from(dataTransfer?.types ?? []).includes("Files");
}

/**
 * The native bridge of the desktop window (pywebview's `window.pywebview.api`,
 * src/kuulas/desktop.py), or null in a plain browser. pywebview injects the api
 * after the page loads, so this is asked at click time, never cached.
 */
export function nativeBridge(win = globalThis) {
  const api = win?.pywebview?.api;
  return typeof api?.pick_media === "function" ? api : null;
}
