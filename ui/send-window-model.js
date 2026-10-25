// Edit > Clipboard > Copy to other window (owner, 2026-10-23): where an entry can go, and what
// the window that gets it says. Pure; the desktop bridge (desktop.py) does the sending.

/**
 * The other project windows as the bridge lists them ({ folder, name }): none, the one
 * (sent to at once), or a list for the menu that asks which.
 */
export function windowChoice(windows) {
  const list = windows ?? [];
  if (list.length === 0) return { kind: "none" };
  if (list.length === 1) return { kind: "one", target: list[0] };
  return {
    kind: "many",
    items: list.map((w) => ({ id: w.folder, label: w.name, enabled: true })),
  };
}

/** The placeholders of "{from} sent {name}: ..." from the note the sending window made. */
export function arrivedValues(note, fallbackName = "") {
  return { from: note?.from ?? "", name: note?.entry?.name || fallbackName };
}
