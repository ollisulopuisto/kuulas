// The app's side of the Clipboard's series shelf (docs/design/CLIPBOARD-SHELVES.md): loading it,
// the Series toggle of a project entry, and which route adopts an entry of another shelf. Kept
// out of app.js so `node --test` covers it.

/**
 * An entry of another shelf copied into this project's clipboard: { entry, entries }. A series
 * entry is adopted by the series, which links its recordings from where the series saw them
 * (hash-checked, in place); the others by the plain adopt (their source project's paths).
 */
export function adoptRequest(api, entry, from, shelf) {
  return shelf === "series" ? api.seriesShelfAdopt(entry.id) : api.adoptClipboardEntry(entry, from);
}

/** `setState`, `notify(text)` and `showError(error)` are the app's. */
export function createSeriesShelf({ api, t, setState, notify, showError }) {
  return {
    async load() {
      try {
        setState({ clipboardSeries: await api.getSeriesShelf() });
      } catch (error) {
        showError(error);
      }
    },
    /** On: a copy on the series shelf (same id); off: taken off it again. */
    async toggle(id, on) {
      try {
        const shelf = await (on ? api.seriesShelfAdd(id) : api.seriesShelfRemove(id));
        setState({ clipboardSeries: shelf });
        notify(t(on ? "ui.clipboard.series_added" : "ui.clipboard.series_removed"));
      } catch (error) {
        showError(error);
      }
    },
  };
}
